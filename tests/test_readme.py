import ast

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
