"""
Runs README.md's three executed examples: the recursive category tree under the "Walk a category tree in SQL,
filter it with the ORM" heading, the leaderboard and its ORM version under "Prefer SQL? Write it as SQL.", and the
django-cte example under "Get a queryset back", which continues the tree example. The code comes from the README text
itself, so editing the README changes what runs. The only test-only differences are the models' Meta (app_label and
table names) and the database alias, which a router sets.
"""

import ast
import dataclasses
import pathlib
import re
from contextlib import contextmanager

from django.db import connections
from django.test import override_settings

README = pathlib.Path(__file__).resolve().parents[2] / 'README.md'
CATEGORY_TABLE = 'sqlcompiler_readme_category'
PRODUCT_TABLE = 'sqlcompiler_readme_product'
CUSTOMER_TABLE = 'sqlcompiler_readme_customer'
ORDER_TABLE = 'sqlcompiler_readme_order'
SECTIONS = {
    'tree': ('## Walk a category tree in SQL, filter it with the ORM', 3),
    'leaderboard': ('## Prefer SQL? Write it as SQL.', 4),
    'cte': ('## Get a queryset back', 1),
}

with open(README, encoding='utf-8') as readme_file:
    README_TEXT = readme_file.read()


def section_blocks(text, name):
    """Returns the python blocks of one README example section."""

    heading, count = SECTIONS[name]
    marker = '\n' + heading + '\n'
    if text.count(marker) != 1:
        raise ValueError(
            'README example section changed: heading {!r} found {} times'.format(heading, text.count(marker))
        )
    section = text.split(marker, 1)[1].split('\n## ', 1)[0]
    blocks = re.findall(r'^```python\n(.*?)^```', section, re.S | re.M)
    if len(blocks) != count:
        raise ValueError(
            'README example section changed: {} expected {} python blocks, found {}'.format(name, count, len(blocks))
        )
    return blocks


def expected_rows(block, prefix, row_count, names=None):
    """Parses the README's commented expected rows that follow the first line starting with prefix."""

    lines = block.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(prefix)), None)
    if start is None:
        raise ValueError('README example section changed: no {} line'.format(prefix))
    first = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('# [')), None)
    if first is None:
        raise ValueError('README example section changed: no expected-rows comment after {}'.format(prefix))
    comment = []
    for line in lines[first:]:
        if not line.startswith('#'):
            break
        comment.append(line[1:].removeprefix(' '))
    text = ''.join(comment)
    if isinstance(names, dict):
        rows = eval(text, {'__builtins__': {}, **names})
        row_types = tuple(names.values())
    else:
        rows = ast.literal_eval(text)
        row_types = (tuple,)
    if not isinstance(rows, list) or len(rows) != row_count or not all(isinstance(row, row_types) for row in rows):
        raise ValueError(
            'README example section changed: expected a list of {} rows after {}'.format(row_count, prefix)
        )
    return rows


def with_meta(tree, tables):
    found = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in tables:
            if any(isinstance(item, ast.ClassDef) and item.name == 'Meta' for item in node.body):
                raise ValueError('README model {} already has a Meta class'.format(node.name))
            meta = ast.parse("class Meta:\n    app_label = 'tests'\n    db_table = {!r}\n".format(tables[node.name]))
            node.body.append(meta.body[0])
            found.add(node.name)
    if found != set(tables):
        raise ValueError('README example section changed: models {} not found'.format(sorted(set(tables) - found)))
    ast.fix_missing_locations(tree)
    return tree


# Executed once at import: running the models block again would register the models twice
TREE_MODELS = {'__name__': __name__}
exec(
    compile(
        with_meta(
            ast.parse(section_blocks(README_TEXT, 'tree')[0]),
            {'Category': CATEGORY_TABLE, 'Product': PRODUCT_TABLE},
        ),
        'README.md',
        'exec',
    ),
    TREE_MODELS,
)
LEADERBOARD_MODELS = {'__name__': __name__}
exec(
    compile(
        with_meta(
            ast.parse(section_blocks(README_TEXT, 'leaderboard')[0]),
            {'Customer': CUSTOMER_TABLE, 'Order': ORDER_TABLE},
        ),
        'README.md',
        'exec',
    ),
    LEADERBOARD_MODELS,
)
Category = TREE_MODELS['Category']
Product = TREE_MODELS['Product']
Branch = TREE_MODELS['Branch']
Customer = LEADERBOARD_MODELS['Customer']
Order = LEADERBOARD_MODELS['Order']
RegionLeader = LEADERBOARD_MODELS['RegionLeader']


class Router:
    """The README code has no .using(), so a router points its reads and writes at one alias."""

    def __init__(self, alias):
        self.alias = alias

    def db_for_read(self, model, **hints):
        return self.alias

    def db_for_write(self, model, **hints):
        return self.alias


@contextmanager
def readme_tables(alias):
    connection = connections[alias]
    with connection.schema_editor() as editor:
        existing = connection.introspection.table_names()
        for model in (Order, Customer, Product, Category):
            if model._meta.db_table in existing:
                editor.delete_model(model)
        editor.create_model(Category)
        editor.create_model(Product)
        editor.create_model(Customer)
        editor.create_model(Order)
    try:
        yield
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(Order)
            editor.delete_model(Customer)
            editor.delete_model(Product)
            editor.delete_model(Category)


def mismatch(name, what, actual, expected):
    raise AssertionError('README {} example: {}: got {!r}, expected {!r}'.format(name, what, actual, expected))


def run_blocks(blocks, namespace):
    for block in blocks:
        exec(compile(block, 'README.md', 'exec'), namespace)


def check(name, alias, text=README_TEXT):
    """Runs one README example on alias and raises AssertionError when it disagrees with its documented rows."""

    blocks = section_blocks(text, name)
    with readme_tables(alias), override_settings(DATABASE_ROUTERS=[Router(alias)]):
        if name == 'tree':
            ns = dict(TREE_MODELS)
            expected = expected_rows(blocks[2], 'rows = fetch_rows(tree', 4, {'Branch': Branch})
            run_blocks(blocks[1:3], ns)
            if ns['tree'].alias != alias:
                mismatch(name, 'alias', ns['tree'].alias, alias)
            if ns['rows'] != expected:
                mismatch(name, 'rows', ns['rows'], expected)
        elif name == 'leaderboard':
            ns = dict(LEADERBOARD_MODELS)
            expected = expected_rows(blocks[2], 'rows = fetch_rows(leaderboard', 2, {'RegionLeader': RegionLeader})
            expected_orm = expected_rows(blocks[3], 'orm_rows = ', 2)
            run_blocks(blocks[1:4], ns)
            orm_rows = list(ns['orm_rows'])
            compose_tuples = [dataclasses.astuple(row) for row in ns['rows']]
            if ns['leaderboard'].alias != alias:
                mismatch(name, 'alias', ns['leaderboard'].alias, alias)
            if ns['rows'] != expected:
                mismatch(name, 'compose rows', ns['rows'], expected)
            if compose_tuples != orm_rows:
                mismatch(name, 'compose rows vs ORM rows', compose_tuples, orm_rows)
            if orm_rows != expected_orm:
                mismatch(name, 'ORM rows', orm_rows, expected_orm)
            if [dataclasses.astuple(row) for row in expected] != expected_orm:
                mismatch(name, 'documented rows', [dataclasses.astuple(row) for row in expected], expected_orm)
        elif name == 'cte':
            tree_blocks = section_blocks(text, 'tree')
            cte_block = blocks[0]
            ns = dict(TREE_MODELS)
            expected = expected_rows(cte_block, 'cte_rows = ', 4)
            run_blocks([tree_blocks[1], tree_blocks[2], cte_block], ns)
            if ns['subtree'].alias != alias:
                mismatch(name, 'alias', ns['subtree'].alias, alias)
            if ns['cte_rows'] != expected:
                mismatch(name, 'rows', ns['cte_rows'], expected)
            if ns['cheap'].count() != len(expected):
                mismatch(name, 'count', ns['cheap'].count(), len(expected))
            if type(ns['cheap'].first()) is not Product:
                mismatch(name, 'row type', type(ns['cheap'].first()), Product)
        else:
            raise ValueError('unknown README example {!r}'.format(name))
    return ns
