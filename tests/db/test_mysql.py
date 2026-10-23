import pytest

from .cases import CASE_IDS, run_case


@pytest.mark.parametrize('case_id', CASE_IDS)
def test_mysql_case(mysql_db, things, case_id):
    run_case('mysql', case_id)
