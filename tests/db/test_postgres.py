import pytest

from tests import dbconfig

from .cases import CASE_IDS, run_case

_gro14 = dbconfig.gro14_xfail()
pytestmark = [_gro14] if _gro14 is not None else []


@pytest.mark.parametrize('case_id', CASE_IDS)
def test_postgres_case(postgres_db, things, case_id):
    run_case('postgres', case_id)
