import pytest

from . import readme_example


@pytest.mark.parametrize('name', ['tree', 'leaderboard', 'cte'])
def test_readme_example_on_default(name, db_under_test):
    readme_example.check(name, 'default')
