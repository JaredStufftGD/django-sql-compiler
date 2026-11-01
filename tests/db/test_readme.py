import pytest

from . import readme_example


@pytest.fixture
def readme_tables_default(db_under_test):
    with readme_example.readme_tables('default'):
        yield


def test_readme_example_on_default(readme_tables_default):
    leaderboard, rows = readme_example.run('default')

    assert leaderboard.alias == 'default'
    assert rows == readme_example.EXPECTED
