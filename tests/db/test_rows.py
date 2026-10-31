import pytest

from . import rows_cases


@pytest.mark.parametrize('check_id', rows_cases.CHECK_IDS)
def test_check_runs_on_default(db_under_test, things, check_id):
    rows_cases.run_check('default', check_id)
