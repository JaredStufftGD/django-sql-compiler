import pytest
from django.db import connection, connections
from django.test import override_settings

from tests import dbconfig

from .cases import ROWS
from .expected import EXPECTED
from .models import Thing

_gro14 = dbconfig.gro14_xfail()


def gro14_only(func):
    if _gro14 is None:
        return func
    return _gro14(func)


@gro14_only
def test_non_ascii_param_is_not_garbled(db_under_test, things):
    qs = Thing.objects.filter(name='café')
    assert qs.executable_query == EXPECTED[db_under_test]['non_ascii']

    with connection.cursor() as cursor:
        cursor.execute(qs.executable_query)
        got = {row[0] for row in cursor.fetchall()}
    assert got == set(qs.values_list('pk', flat=True))
    assert 0 < len(got) < len(ROWS)


gro10 = pytest.mark.skipif(not dbconfig.gro10_ready(), reason='GRO-10 pin needs default=PostgreSQL via psycopg2 and MySQL as alias other; run uv run --exact --group pg2 --group mysql pytest')


class ThingReadsToOther:
    def db_for_read(self, model, **hints):
        return 'other' if model is Thing else None


def assert_runs_on_other(qs, compiled):
    with connections['other'].cursor() as cursor:
        cursor.execute(compiled)
        got = {row[0] for row in cursor.fetchall()}
    assert got == set(qs.values_list('pk', flat=True))
    assert 0 < len(got) < len(ROWS)


@gro10
def test_non_default_alias_compiles_for_its_own_backend(things_other):
    qs = Thing.objects.using('other').filter(name="it's")
    assert qs.executable_query == EXPECTED['mysql']['single_quote']
    assert_runs_on_other(qs, qs.executable_query)


@gro10
def test_router_selected_alias_compiles_for_its_own_backend(things_other):
    with override_settings(DATABASE_ROUTERS=[ThingReadsToOther()]):
        qs = Thing.objects.filter(name="it's")
        assert qs.db == 'other'
        assert qs.executable_query == EXPECTED['mysql']['single_quote']
        assert_runs_on_other(qs, qs.executable_query)

