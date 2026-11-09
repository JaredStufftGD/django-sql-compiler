import pytest
from django.db import connections

from tests import dbconfig
from tests.db import spike_b_cases as cases


@pytest.fixture(autouse=True)
def default_never_connects():
    yield
    if dbconfig.STATE['default'] == 'sqlite':
        assert connections['default'].connection is None


def test_route_b_q1_params_sqlite(spike_sqlite):
    cases.check_q1_params(spike_sqlite)


def test_route_b_q2_pinned_alias_sqlite(spike_sqlite):
    cases.check_q2_pinned_alias(spike_sqlite)


def test_route_b_q3_percent_sqlite(spike_sqlite):
    cases.check_q3_percent(spike_sqlite)


def test_route_b_q4_lazy_sqlite(spike_sqlite):
    cases.check_q4_lazy(spike_sqlite)


def test_route_b_q5_no_deprecation_sqlite(spike_sqlite):
    cases.check_q5_no_deprecation(spike_sqlite)


def test_route_b_q6_roundtrip_sqlite(spike_sqlite):
    cases.check_q6_roundtrip(spike_sqlite)


def test_route_b_q6_hazard_executable_query_gate_sqlite(spike_sqlite):
    cases.check_q6_executable_query(spike_sqlite)


def test_route_b_q7_clone_sqlite(spike_sqlite):
    cases.check_q7_clone(spike_sqlite)


def test_route_b_q2_mismatch_sqlite_result_on_default_query():
    cases.check_q2_mismatch('sqlite_live', 'default')


def test_route_b_q2_mismatch_default_result_on_sqlite_live_query():
    cases.check_q2_mismatch('default', 'sqlite_live')
