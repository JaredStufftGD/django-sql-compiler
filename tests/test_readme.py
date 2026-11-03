import ast
import re

import pytest
from django.db import connections

from tests import dbconfig
from tests.db import readme_example


@pytest.fixture(autouse=True)
def default_never_connects():
    yield
    if dbconfig.STATE['default'] == 'sqlite':
        assert connections['default'].connection is None


@pytest.mark.parametrize('name', ['tree', 'leaderboard', 'cte'])
def test_readme_example_on_sqlite_live(name):
    readme_example.check(name, dbconfig.SQLITE_LIVE_ALIAS)


def replace_in_section(text, name, old, new):
    heading = readme_example.SECTIONS[name][0]
    marker = '\n' + heading + '\n'
    head, rest = text.split(marker, 1)
    section, separator, tail = rest.partition('\n## ')
    assert section.count(old) == 1, 'README changed: update the drift literal {!r} in tests/test_readme.py'.format(old)
    altered = head + marker + section.replace(old, new) + separator + tail
    assert altered != text
    return altered


DRIFT = [
    pytest.param('tree', 'tree', "'Pixel', 79900", "'Pixel', 7990", id='tree-data'),
    pytest.param('tree', 'tree', 'total_cents=149800', 'total_cents=149801', id='tree-rows'),
    pytest.param(
        'leaderboard',
        'leaderboard',
        'datetime.date(2026, 3, 10), 9000',
        'datetime.date(2026, 3, 10), 900',
        id='leaderboard-data',
    ),
    pytest.param(
        'leaderboard',
        'leaderboard',
        "RegionLeader(name='Bo', orders=1, total_cents=9000, place=1)",
        "RegionLeader(name='Bo', orders=1, total_cents=9000, place=3)",
        id='leaderboard-rows',
    ),
    pytest.param('leaderboard', 'leaderboard', "('Bo', 1, 9000, 1)", "('Bo', 1, 9000, 2)", id='leaderboard-orm-rows'),
    pytest.param(
        'leaderboard',
        'leaderboard',
        "F('total_cents').desc()",
        "F('total_cents').asc()",
        id='leaderboard-orm-code',
    ),
    pytest.param('cte', 'cte', 'budget_cents = 70000', 'budget_cents = 50000', id='cte-data'),
    pytest.param('cte', 'cte', "('Galaxy', 1, 69900)", "('Galaxy', 1, 69901)", id='cte-rows'),
]


@pytest.mark.parametrize('name, section, old, new', DRIFT)
def test_readme_drift_is_detected(name, section, old, new):
    altered = replace_in_section(readme_example.README_TEXT, section, old, new)

    with pytest.raises(AssertionError):
        readme_example.check(name, dbconfig.SQLITE_LIVE_ALIAS, altered)


def test_readme_parse_guards():
    tree_heading = readme_example.SECTIONS['tree'][0]
    leaderboard_heading = readme_example.SECTIONS['leaderboard'][0]
    block = '```python\nx = 1\n```\n'
    branch = {'Branch': readme_example.Branch}

    with pytest.raises(ValueError):
        readme_example.section_blocks('no example section here', 'tree')
    with pytest.raises(ValueError):
        readme_example.section_blocks('\n{}\n\n{}\n{}\n\n{}'.format(tree_heading, block, block, block) * 2, 'tree')
    with pytest.raises(ValueError):
        readme_example.section_blocks(
            '\n{}\n\n{}{}{}\n## Next\n'.format(leaderboard_heading, block, block, block), 'leaderboard'
        )
    with pytest.raises(ValueError):
        readme_example.expected_rows('rows = fetch_rows(tree, Branch)\n', 'rows = fetch_rows(tree', 4, branch)
    with pytest.raises(ValueError):
        readme_example.expected_rows(
            "rows = fetch_rows(tree, Branch)\n# [Branch(name='a', depth=0, products=0, total_cents=0)]\n",
            'rows = fetch_rows(tree',
            4,
            branch,
        )
    with pytest.raises(ValueError):
        readme_example.expected_rows('x = 1\n', 'cte_rows = ', 4)
    with pytest.raises(ValueError):
        readme_example.expected_rows("cte_rows = []\n# [('a', 0, 1)]\n", 'cte_rows = ', 4)
    with pytest.raises(ValueError):
        readme_example.with_meta(
            ast.parse('class Category(models.Model):\n    class Meta:\n        pass\n'), {'Category': 'x'}
        )


HEADLINE = '## Walk a category tree in SQL, filter it with the ORM'
SECTION_ORDER = [
    'Installation',
    'Walk a category tree in SQL, filter it with the ORM',
    'Prefer SQL? Write it as SQL.',
    'Why not `as_sql()`?',
    'Compared to',
    'Get a queryset back',
    'Reference',
]
COMPARED_FIRST_CELLS = [
    'django-sql-compiler',
    'Plain Django (cursor, raw())',
    'django-cte',
    'View + unmanaged model',
    'SQLAlchemy Core / aldjemy',
    'aiosql',
]
COMPARED_COLUMNS = ['Reuses querysets', 'Outer query in SQL', 'Multi-database', 'Queryset back', 'Literal SQL']


def prose_lines(text):
    lines = []
    in_fence = False
    for line in text.split('\n'):
        if line.startswith('```'):
            in_fence = not in_fence
        elif not in_fence:
            lines.append(line)
    return lines


def headings(text):
    found = []
    for line in prose_lines(text):
        match = re.match(r'^(#+) (.+)$', line)
        if match:
            found.append((len(match.group(1)), match.group(2)))
    return found


def section_text(text, heading):
    head, rest = text.split('\n' + heading + '\n', 1)
    return rest.split('\n#', 1)[0]


def bullet_lines(lines):
    return [line for line in lines if re.match(r'^(- |\* |\d+\. )', line)]


def test_readme_front_page():
    front = readme_example.README_TEXT.split('\n' + HEADLINE + '\n', 1)[0]
    prose = prose_lines(front)

    assert headings(front) == [(1, 'Django SQL Compiler'), (2, 'Installation')]
    assert 'pip install django-sql-compiler' in front
    assert 'INSTALLED_APPS' in front
    assert 'django.db.models.sql.compiler.SQLCompiler' in front
    assert bullet_lines(prose) == []
    assert 'SQLCompilerManager' not in front
    assert "can't express" not in front.lower()
    assert 'cannot express' not in front.lower()


def test_readme_section_order():
    assert [title for level, title in headings(readme_example.README_TEXT) if level == 2] == SECTION_ORDER


def test_readme_no_bullets_above_reference():
    text = readme_example.README_TEXT
    above = text.split('\n' + HEADLINE + '\n', 1)[1].split('\n## Reference\n', 1)[0]

    assert bullet_lines(prose_lines(above)) == []


def test_readme_cross_references_exist():
    prose = '\n'.join(prose_lines(readme_example.README_TEXT))
    titles = {title for level, title in headings(readme_example.README_TEXT)}
    references = re.findall(r'(?:see|under) "([^"]+)"', prose)

    assert references
    assert [reference for reference in references if reference not in titles] == []


def test_readme_compared_to_table():
    section = section_text(readme_example.README_TEXT, '## Compared to')
    rows = [
        [cell.strip() for cell in line.strip().strip('|').split('|')]
        for line in section.split('\n')
        if line.startswith('|')
    ]
    header, data = rows[0], rows[2:]

    assert header[1:] == COMPARED_COLUMNS
    assert [row[0] for row in data] == COMPARED_FIRST_CELLS
    for row in data:
        assert len(row) == 6
        for cell in row[1:5]:
            assert re.match(r'^(Yes|No)\b', cell), cell
        literal = row[5]
        assert any(word in literal for word in ('driver', 'display only', 'literal_binds')) or literal == 'None', (
            literal
        )
    assert not re.search(r'\d+\.\d+', section)
    assert 'download' not in section.lower()


def test_readme_why_not_as_sql():
    section = section_text(readme_example.README_TEXT, '## Why not `as_sql()`?')

    for phrase in ('EmptyResultSet', '%%', 'sql_with_params', 'dictfetchall'):
        assert phrase in section


def test_readme_executable_query_keeps_phrase():
    section = section_text(readme_example.README_TEXT, '### Finished literal SQL: executable_query')

    assert 'usable SQL from a QuerySet' in section
