import pytest
from django.test import override_settings

from sql_compiler import compose

from tests import dbconfig

from . import compose_cases
from .models import Thing

gro10 = pytest.mark.skipif(not dbconfig.gro10_ready(), reason='GRO-10 pin needs default=PostgreSQL via psycopg2 and MySQL as alias other; run uv run --exact --group pg2 --group mysql pytest')


class ThingReadsToOther:
    def db_for_read(self, model, **hints):
        return 'other' if model._meta.concrete_model is Thing else None


@gro10
@pytest.mark.parametrize('scenario_id', compose_cases.SCENARIO_IDS)
def test_scenario_runs_on_other(things_other, scenario_id):
    compose_cases.check_scenario('other', scenario_id)


@gro10
def test_raw_returns_instances_on_other(things_other):
    compose_cases.check_raw('other')


@gro10
def test_other_alias_compiles_for_mysql(things_other):
    template = 'SELECT x.n FROM (%(q)s) x'
    other = compose(template, q=Thing.objects.using('other').filter(name="it's"))
    default = compose(template, q=Thing.objects.using('default').filter(name="it's"))
    assert other.alias == 'other'
    assert '`' in other.sql
    assert '`' not in default.sql


@gro10
def test_router_selected_other_alias(things_other):
    with override_settings(DATABASE_ROUTERS=[ThingReadsToOther()]):
        qs = Thing.objects.filter(name="it's")
        assert qs.db == 'other'
        result = compose('SELECT x.n FROM (%(q)s) x', q=qs)
    assert result.alias == 'other'
    assert '`' in result.sql


@gro10
def test_mixed_postgres_default_and_mysql_other_raise(things_other):
    with pytest.raises(ValueError) as excinfo:
        compose('%(a)s UNION ALL %(b)s', a=Thing.objects.using('default').all(), b=Thing.objects.using('other').all())
    assert str(excinfo.value) == "compose slots must share one database alias, got 'default': a; 'other': b"
    nested = compose('%(q)s', q=Thing.objects.using('other').all())
    with pytest.raises(ValueError) as excinfo:
        compose('%(a)s UNION ALL %(b)s', a=nested, b=Thing.objects.using('default').all())
    assert "'default'" in str(excinfo.value)
    assert "'other'" in str(excinfo.value)
