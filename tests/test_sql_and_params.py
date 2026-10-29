import inspect

import django.db.models.sql.query
import pytest
from django.db import connections
from django.db.models import QuerySet
from django.test import override_settings

import sql_compiler
from sql_compiler import sql_and_params
from sql_compiler.queryset import SQLCompilerQuerySet
from sql_compiler import utils

from tests import dbconfig
from tests.db import shapes
from tests.db.models import PlainThing, Thing

REJECTED = {
    'manager': (lambda: Thing.objects, 'SQLCompilerManager'),
    'plain_manager': (lambda: PlainThing.objects, 'Manager'),
    'raw_queryset': (lambda: Thing.objects.raw('select 1'), 'RawQuerySet'),
    'str': (lambda: 'x', 'str'),
    'none': (lambda: None, 'NoneType'),
}

QUERYSETS = {
    'filtered': lambda: Thing.objects.filter(n__lte=3),
    'none': lambda: Thing.objects.none(),
    'values': lambda: Thing.objects.values('name'),
    'union': lambda: Thing.objects.filter(n__lte=3).union(Thing.objects.filter(n__gte=2)),
}


@pytest.fixture(autouse=True)
def default_never_connects():
    yield
    if dbconfig.STATE['default'] == 'sqlite':
        assert connections['default'].connection is None


def test_sql_and_params_is_exported():
    assert 'sql_and_params' in sql_compiler.__all__
    assert sql_compiler.sql_and_params is utils.sql_and_params
    assert sql_and_params is utils.sql_and_params


@pytest.mark.parametrize('case_id', list(REJECTED))
def test_rejects_non_querysets(case_id):
    factory, name = REJECTED[case_id]
    with pytest.raises(TypeError) as excinfo:
        sql_and_params(factory())
    assert str(excinfo.value) == 'sql_and_params needs a QuerySet, got {}'.format(name)


def test_accepts_plain_manager_queryset():
    qs = PlainThing.objects.filter(n__lte=3)
    assert type(qs) is QuerySet
    sql, params = qs.query.get_compiler(using=qs.db).as_sql()
    assert sql_and_params(qs) == (sql, tuple(params))


@pytest.mark.parametrize('case_id', list(QUERYSETS))
def test_method_equals_module_function(case_id):
    qs = QUERYSETS[case_id]()
    assert qs.sql_and_params() == sql_and_params(qs)


def test_pair_is_str_with_placeholders_and_tuple_params():
    sql, params = sql_and_params(Thing.objects.filter(name="it's"))
    assert isinstance(sql, str)
    assert '%s' in sql
    assert type(params) is tuple
    assert params == ("it's",)
    assert "it's" not in sql


@pytest.mark.parametrize('case_id', ['filtered', 'none'])
def test_pair_matches_the_shared_compile_path(case_id):
    qs = QUERYSETS[case_id]()
    sql, params = utils.query_sql_and_params(qs.query, qs.db)
    assert sql_and_params(qs) == (sql, tuple(params))


def test_no_backend_gate():
    sql, params = sql_and_params(Thing.objects.all())
    assert isinstance(sql, str)
    if dbconfig.STATE['default'] == 'sqlite':
        assert connections['default'].connection is None


def test_managers_get_no_sql_and_params():
    assert not hasattr(Thing.objects, 'sql_and_params')
    assert not hasattr(PlainThing.objects, 'sql_and_params')


def test_method_is_not_cached():
    assert inspect.isfunction(SQLCompilerQuerySet.__dict__['sql_and_params'])
    qs = Thing.objects.filter(n__lte=3)
    qs.sql_and_params()
    assert 'sql_and_params' not in qs.__dict__


SHAPE_BY_ID = {shape[0]: shape for shape in shapes.SHAPES}
EMPTY_BY_ID = {shape[0]: shape for shape in shapes.EMPTY_SHAPES}


class ThingReadsTo:
    def __init__(self, alias):
        self.alias = alias

    def db_for_read(self, model, **hints):
        return self.alias if model._meta.concrete_model is Thing else None


@pytest.mark.parametrize('shape_id', shapes.SHAPE_IDS)
def test_shape_pair_runs_on_sqlite(things_sqlite, shape_id):
    _, factory, kind, ordered = SHAPE_BY_ID[shape_id]
    shapes.require_features(things_sqlite, shape_id)
    qs = factory(Thing.objects.using(things_sqlite))
    assert qs.db == things_sqlite
    pair = sql_and_params(qs)
    assert qs.sql_and_params() == pair
    shapes.assert_pair_matches_queryset(qs, things_sqlite, pair, kind, ordered)


@pytest.mark.parametrize('shape_id', shapes.RAW_SHAPE_IDS)
def test_raw_returns_the_querysets_instances_on_sqlite(things_sqlite, shape_id):
    _, factory, _, ordered = SHAPE_BY_ID[shape_id]
    qs = factory(Thing.objects.using(things_sqlite))
    sql, params = sql_and_params(qs)
    raw = qs.raw(sql, params)
    assert raw.db == things_sqlite
    objs = list(raw)
    assert objs
    assert all(isinstance(o, Thing) for o in objs)
    got = [o.pk for o in objs]
    want = [o.pk for o in qs]
    if ordered:
        assert got == want
    else:
        assert set(got) == set(want)
    using_got = [o.pk for o in Thing.objects.raw(sql, params, using=things_sqlite)]
    if ordered:
        assert using_got == want
    else:
        assert set(using_got) == set(want)


@pytest.mark.parametrize('shape_id', shapes.EMPTY_IDS)
def test_empty_pair_returns_zero_rows_on_sqlite(things_sqlite, shape_id):
    _, empty_factory, counterpart_factory = EMPTY_BY_ID[shape_id]
    base = Thing.objects.using(things_sqlite)
    empty_qs = empty_factory(base)
    assert list(empty_qs) == []
    shapes.assert_empty_pair(
        things_sqlite, sql_and_params(empty_qs), sql_and_params(counterpart_factory(base))
    )


def test_empty_slice_drops_its_limits_on_sqlite(things_sqlite):
    base = Thing.objects.using(things_sqlite)
    sliced = sql_and_params(base.all()[5:5])
    assert 'OFFSET' not in sliced[0]
    assert 'LIMIT' not in sliced[0]
    assert '0 = 1' in sliced[0]
    kept = sql_and_params(base.filter(id__in=[])[2:5])
    assert kept[0].endswith('LIMIT 3 OFFSET 2')
    assert shapes.run_pair(things_sqlite, *sliced)[0] == []
    assert shapes.run_pair(things_sqlite, *kept)[0] == []


def test_plain_manager_queryset_runs_on_sqlite(things_sqlite):
    qs = PlainThing.objects.using(things_sqlite).filter(n__lte=3)
    assert type(qs) is QuerySet
    shapes.assert_pair_matches_queryset(qs, things_sqlite, sql_and_params(qs), 'instances', False)


def test_router_selected_alias_runs_on_sqlite(things_sqlite):
    with override_settings(DATABASE_ROUTERS=[ThingReadsTo(things_sqlite)]):
        qs = Thing.objects.filter(n__lte=3)
        assert qs.db == things_sqlite
        pair = sql_and_params(qs)
        assert qs.sql_and_params() == pair
        shapes.assert_pair_matches_queryset(qs, things_sqlite, pair, 'instances', False)


def test_router_change_between_calls_recompiles(things_sqlite, monkeypatch):
    qs = Thing.objects.filter(name__contains='%')
    original = django.db.models.sql.query.Query.get_compiler
    seen = []

    def spy(self, *args, **kwargs):
        seen.append(kwargs.get('using', args[0] if args else None))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(django.db.models.sql.query.Query, 'get_compiler', spy)
    with override_settings(DATABASE_ROUTERS=[ThingReadsTo(things_sqlite)]):
        routed = sql_and_params(qs)
        routed_method = qs.sql_and_params()
    with override_settings(DATABASE_ROUTERS=[]):
        unrouted = sql_and_params(qs)
        unrouted_method = qs.sql_and_params()
    monkeypatch.undo()
    assert seen == [things_sqlite, things_sqlite, 'default', 'default']
    assert routed == routed_method
    assert unrouted == unrouted_method
    assert routed[0] == qs.query.get_compiler(using=things_sqlite).as_sql()[0]
    assert unrouted[0] == qs.query.get_compiler(using='default').as_sql()[0]
    # the no-DB run proves the alias through the get_compiler spy; the DB jobs supply the observable SQL difference
    if dbconfig.STATE['default'] != 'sqlite':
        assert routed[0] != unrouted[0]
