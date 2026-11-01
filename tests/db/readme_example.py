"""
Runs README.md's headline example (the three python blocks under the "Filter with the ORM" heading).
The code comes from the README text itself, so editing the README changes what runs. The only test-only
differences are the models' Meta (app_label and table names) and the database alias.
"""

import ast
import pathlib
import re
from contextlib import contextmanager

from django.db import connections
from django.test import override_settings

README = pathlib.Path(__file__).resolve().parents[2] / 'README.md'
HEADING = '## Filter with the ORM, finish in SQL.'
CUSTOMER_TABLE = 'sqlcompiler_readme_customer'
ORDER_TABLE = 'sqlcompiler_readme_order'

with open(README, encoding='utf-8') as readme_file:
    README_TEXT = readme_file.read()


def readme_blocks(text):
    """Returns the (models, data, query) python blocks of the README example section."""

    if HEADING not in text:
        raise ValueError('README example section changed: heading {!r} not found'.format(HEADING))
    section = text.split(HEADING, 1)[1].split('\n## ', 1)[0]
    blocks = re.findall(r'^```python\n(.*?)^```', section, re.S | re.M)
    if len(blocks) != 3:
        raise ValueError('README example section changed: expected 3 python blocks, found {}'.format(len(blocks)))
    return blocks


def expected_rows(query_block, row_type):
    """Parses the README's commented expected rows that follow the fetch_rows call."""

    lines = query_block.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith('rows = fetch_rows(')), None)
    if start is None:
        raise ValueError('README example section changed: no rows = fetch_rows( line')
    comment = []
    for line in lines[start + 1 :]:
        if not line.startswith('#'):
            break
        comment.append(line[1:].removeprefix(' '))
    if not comment:
        raise ValueError('README example section changed: no expected-rows comment after fetch_rows')
    rows = eval(''.join(comment), {'__builtins__': {}, 'RegionLeader': row_type})
    if not isinstance(rows, list) or len(rows) != 2 or not all(isinstance(row, row_type) for row in rows):
        raise ValueError('README example section changed: expected a list of 2 {} rows'.format(row_type.__name__))
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
MODELS_BLOCK, DATA_BLOCK, QUERY_BLOCK = readme_blocks(README_TEXT)
MODELS = {'__name__': __name__}
exec(
    compile(
        with_meta(ast.parse(MODELS_BLOCK), {'Customer': CUSTOMER_TABLE, 'Order': ORDER_TABLE}),
        'README.md',
        'exec',
    ),
    MODELS,
)
Customer = MODELS['Customer']
Order = MODELS['Order']
RegionLeader = MODELS['RegionLeader']
EXPECTED = expected_rows(QUERY_BLOCK, RegionLeader)


class Router:
    """The README code has no .using(), so a router points its reads and writes at one alias."""

    def __init__(self, alias):
        self.alias = alias

    def db_for_read(self, model, **hints):
        return self.alias

    def db_for_write(self, model, **hints):
        return self.alias


def run(alias, data_block=DATA_BLOCK, query_block=QUERY_BLOCK):
    """Runs the README data and query blocks on alias. Returns (leaderboard, rows)."""

    namespace = dict(MODELS)
    with override_settings(DATABASE_ROUTERS=[Router(alias)]):
        exec(compile(data_block, 'README.md', 'exec'), namespace)
        exec(compile(query_block, 'README.md', 'exec'), namespace)
    return namespace['leaderboard'], namespace['rows']


@contextmanager
def readme_tables(alias):
    connection = connections[alias]
    with connection.schema_editor() as editor:
        existing = connection.introspection.table_names()
        for model in (Order, Customer):
            if model._meta.db_table in existing:
                editor.delete_model(model)
        editor.create_model(Customer)
        editor.create_model(Order)
    try:
        yield
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(Order)
            editor.delete_model(Customer)
