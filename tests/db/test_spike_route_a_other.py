import pytest
from django.test import override_settings

from sql_compiler import compose
from sql_compiler.spike_a import ResultIn

from tests import dbconfig

from . import spike_a_cases as cases
from .models import Thing

gro10 = pytest.mark.skipif(
    not dbconfig.gro10_ready(),
    reason='GRO-10 pin needs default=PostgreSQL via psycopg2 and MySQL as alias other; run uv run --exact --group pg2 --group mysql pytest',
)


class ThingReadsToOther:
    def db_for_read(self, model, **hints):
        return 'other' if model._meta.concrete_model is Thing else None


@gro10
def test_route_a_q2_router_mismatch(things_other):
    result = cases.composed_keys('default', 2)
    assert result.alias == 'default'
    with override_settings(DATABASE_ROUTERS=[ThingReadsToOther()]):
        qs = Thing.objects.filter(pk__in=ResultIn(result, 'id'))
        assert qs.db == 'other'
        with pytest.raises(ValueError) as excinfo:
            list(qs)
    assert str(excinfo.value) == cases.mismatch_message('ResultIn', 'default', 'other')


@gro10
def test_route_a_q2_router_same_alias(things_other):
    with override_settings(DATABASE_ROUTERS=[ThingReadsToOther()]):
        result = compose('SELECT x.id FROM (%(q)s) x WHERE x.n > %(lo)s', q=Thing.objects.values('id', 'n'), lo=2)
        assert result.alias == 'other'
        qs = Thing.objects.filter(pk__in=ResultIn(result, 'id'))
        assert qs.db == 'other'
        assert cases.ids(qs) == [3, 5, 6, 7, 8]


@gro10
def test_route_a_q2_using_other_explicit(things_other):
    result = cases.composed_keys('other', 2)
    assert result.alias == 'other'
    qs = Thing.objects.using('other').filter(pk__in=ResultIn(result, 'id'))
    assert cases.ids(qs) == [3, 5, 6, 7, 8]


@gro10
def test_route_a_q1_params_other(things_other):
    cases.check_q1_params('other')
