import pytest
from django.test import override_settings

from sql_compiler import compose
from sql_compiler.spike_b import derived

from tests import dbconfig

from . import spike_b_cases as cases
from .models import Thing
from .spike_models import SpikeDerivedThing

gro10 = pytest.mark.skipif(
    not dbconfig.gro10_ready(),
    reason='GRO-10 pin needs default=PostgreSQL via psycopg2 and MySQL as alias other; run uv run --exact --group pg2 --group mysql pytest',
)


class ThingReadsToOther:
    def db_for_read(self, model, **hints):
        return 'other' if model._meta.concrete_model in (Thing, SpikeDerivedThing) else None


@gro10
def test_route_b_q2_router_ignored_pinned_alias(things_other):
    result = cases.thing_result('default', 2)
    assert result.alias == 'default'
    with override_settings(DATABASE_ROUTERS=[ThingReadsToOther()]):
        assert SpikeDerivedThing._default_manager.all().db == 'other'
        qs = derived(SpikeDerivedThing, result)
        assert qs.db == 'default'
        assert cases.ids(qs) == [2, 3, 5, 6, 7, 8]


@gro10
def test_route_b_q2_using_other_mismatch(things_other):
    result = cases.thing_result('default', 2)
    qs = derived(SpikeDerivedThing, result).using('other')
    with pytest.raises(ValueError) as excinfo:
        list(qs)
    assert str(excinfo.value) == cases.mismatch_message('default', 'other')


@gro10
def test_route_b_q2_other_result(things_other):
    with override_settings(DATABASE_ROUTERS=[ThingReadsToOther()]):
        result = compose(
            'SELECT x.id, x.name, x.n FROM (%(q)s) x WHERE x.n >= %(lo)s',
            q=Thing.objects.values('id', 'name', 'n'),
            lo=2,
        )
        assert result.alias == 'other'
        qs = derived(SpikeDerivedThing, result)
        assert qs.db == 'other'
        assert cases.ids(qs) == [2, 3, 5, 6, 7, 8]


@gro10
def test_route_b_q1_params_other(things_other):
    cases.check_q1_params('other')
