import pytest
from django.db import connections
from django.db.models import QuerySet
from django.test import override_settings

from sql_compiler import sql_and_params

from tests import dbconfig

from . import shapes
from .cases import ROWS
from .models import PlainThing, Thing

SHAPE_BY_ID = {shape[0]: shape for shape in shapes.SHAPES}
EMPTY_BY_ID = {shape[0]: shape for shape in shapes.EMPTY_SHAPES}


@pytest.mark.parametrize('shape_id', shapes.SHAPE_IDS)
def test_shape_pair_runs_on_default(db_under_test, things, shape_id):
    _, factory, kind, ordered = SHAPE_BY_ID[shape_id]
    shapes.require_features('default', shape_id)
    qs = factory(Thing.objects)
    assert qs.db == 'default'
    pair = sql_and_params(qs)
    assert qs.sql_and_params() == pair
    shapes.assert_pair_matches_queryset(qs, 'default', pair, kind, ordered)


@pytest.mark.parametrize('shape_id', shapes.RAW_SHAPE_IDS)
def test_raw_returns_the_querysets_instances(db_under_test, things, shape_id):
    _, factory, _, ordered = SHAPE_BY_ID[shape_id]
    qs = factory(Thing.objects)
    sql, params = sql_and_params(qs)
    raw = qs.raw(sql, params)
    assert raw.db == 'default'
    objs = list(raw)
    assert objs
    assert all(isinstance(o, Thing) for o in objs)
    got = [o.pk for o in objs]
    want = [o.pk for o in qs]
    if ordered:
        assert got == want
    else:
        assert set(got) == set(want)


@pytest.mark.parametrize('shape_id', shapes.EMPTY_IDS)
def test_empty_pair_returns_zero_rows(db_under_test, things, shape_id):
    _, empty_factory, counterpart_factory = EMPTY_BY_ID[shape_id]
    empty_qs = empty_factory(Thing.objects)
    assert list(empty_qs) == []
    shapes.assert_empty_pair(
        'default', sql_and_params(empty_qs), sql_and_params(counterpart_factory(Thing.objects))
    )


def test_plain_manager_queryset_runs_on_default(db_under_test, things):
    qs = PlainThing.objects.filter(n__lte=3)
    assert type(qs) is QuerySet
    shapes.assert_pair_matches_queryset(qs, 'default', sql_and_params(qs), 'instances', False)


gro10 = pytest.mark.skipif(not dbconfig.gro10_ready(), reason='GRO-10 pin needs default=PostgreSQL via psycopg2 and MySQL as alias other; run uv run --exact --group pg2 --group mysql pytest')


class ThingReadsToOther:
    def db_for_read(self, model, **hints):
        return 'other' if model._meta.concrete_model is Thing else None


def assert_pair_runs_on_other(qs, pair):
    rows, _ = shapes.run_pair('other', *pair)
    got = {row[0] for row in rows}
    assert got == set(qs.values_list('pk', flat=True))
    assert 0 < len(got) < len(ROWS)
    assert {o.pk for o in qs.raw(*pair)} == got


def assert_other_pair(qs):
    pair = sql_and_params(qs)
    default_sql = sql_and_params(Thing.objects.using('default').filter(name="it's"))[0]
    assert '`' in pair[0]
    assert '`' not in default_sql
    assert pair[0] != default_sql
    assert type(pair[1]) is tuple
    assert qs.sql_and_params() == pair
    assert_pair_runs_on_other(qs, pair)


@gro10
def test_other_alias_pair_compiles_for_its_own_backend(things_other):
    assert_other_pair(Thing.objects.using('other').filter(name="it's"))


@gro10
def test_router_selected_other_pair_compiles_for_its_own_backend(things_other):
    with override_settings(DATABASE_ROUTERS=[ThingReadsToOther()]):
        qs = Thing.objects.filter(name="it's")
        assert qs.db == 'other'
        assert_other_pair(qs)
