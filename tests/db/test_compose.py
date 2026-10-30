import pytest

from sql_compiler import compose

from . import compose_cases
from .models import Thing


@pytest.mark.parametrize('scenario_id', compose_cases.SCENARIO_IDS)
def test_scenario_runs_on_default(db_under_test, things, scenario_id):
    compose_cases.check_scenario('default', scenario_id)


def test_raw_returns_instances_on_default(db_under_test, things):
    compose_cases.check_raw('default')


def test_default_alias_matches_qs_db(db_under_test, things):
    qs = Thing.objects.filter(n__lte=3)
    assert compose('%(q)s', q=qs).alias == qs.db == 'default'
