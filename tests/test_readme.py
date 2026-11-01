import pytest
from django.db import connections

from tests import dbconfig
from tests.db import readme_example


@pytest.fixture(autouse=True)
def default_never_connects():
    yield
    if dbconfig.STATE['default'] == 'sqlite':
        assert connections['default'].connection is None


@pytest.fixture
def readme_tables_sqlite():
    with readme_example.readme_tables(dbconfig.SQLITE_LIVE_ALIAS):
        yield


def test_readme_example_on_sqlite_live(readme_tables_sqlite):
    leaderboard, rows = readme_example.run(dbconfig.SQLITE_LIVE_ALIAS)

    assert leaderboard.alias == dbconfig.SQLITE_LIVE_ALIAS
    assert rows == readme_example.EXPECTED


def test_readme_drift_is_detected():
    text = readme_example.README_TEXT
    # The README's expected-rows comment disagrees with the code
    altered = text.replace('place=1', 'place=3', 1)
    assert altered != text
    _, _, query_block = readme_example.readme_blocks(altered)
    drifted_expected = readme_example.expected_rows(query_block, readme_example.RegionLeader)
    assert drifted_expected != readme_example.EXPECTED
    with readme_example.readme_tables(dbconfig.SQLITE_LIVE_ALIAS):
        _, rows = readme_example.run(dbconfig.SQLITE_LIVE_ALIAS)
    assert rows == readme_example.EXPECTED
    assert rows != drifted_expected

    # The README's data disagrees with its expected rows
    altered = text.replace('datetime.date(2026, 3, 10), 9000', 'datetime.date(2026, 3, 10), 900', 1)
    assert altered != text
    _, data_block, _ = readme_example.readme_blocks(altered)
    with readme_example.readme_tables(dbconfig.SQLITE_LIVE_ALIAS):
        _, rows = readme_example.run(dbconfig.SQLITE_LIVE_ALIAS, data_block=data_block)
    assert rows != readme_example.EXPECTED


def test_readme_parse_guards():
    heading = readme_example.HEADING
    block = '```python\nx = 1\n```\n'

    with pytest.raises(ValueError):
        readme_example.readme_blocks('no example section here')
    with pytest.raises(ValueError):
        readme_example.readme_blocks('{}\n\n{}{}\n## Next\n'.format(heading, block, block))
    with pytest.raises(ValueError):
        readme_example.expected_rows('rows = fetch_rows(leaderboard, RegionLeader)\n', readme_example.RegionLeader)
