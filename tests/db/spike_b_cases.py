import asyncio
import copy
import dataclasses
import itertools
import pickle
import warnings

import pytest
from django.core.paginator import Paginator
from django.db import connections, transaction
from django.db.models import Case, Count, F, IntegerField, QuerySet, Sum, Value, When
from django.db.models.sql.datastructures import BaseTable
from django.db.models.sql.query import Query
from django.db.utils import DatabaseError
from django.test.utils import CaptureQueriesContext
from django_cte import CTE, with_cte
from django_cte.raw import raw_cte_sql

from sql_compiler import compose, fetch_rows, sql_and_params
from sql_compiler.spike_b import DerivedQuerySet, DerivedTable, derived

from .compose_cases import PAYLOAD
from .models import Thing
from .spike_a_cases import ids, run_rows, things
from .spike_models import SpikeDerivedItem, SpikeDerivedThing, SpikeItem, SpikeLabel, SpikeOverThing

# Thing rows get ids 1..8 in ROWS order; their n values are 1, 2, 3, None, 4, 5, 6, 7


def mismatch_message(result_alias, query_alias):
    return 'DerivedTable was composed for database alias {!r} but the query runs on alias {!r}'.format(
        result_alias, query_alias
    )


def thing_result(alias, lo=2):
    return compose(
        'SELECT x.id, x.name, x.n FROM (%(q)s) x WHERE x.n >= %(lo)s',
        q=things(alias).values('id', 'name', 'n'),
        lo=lo,
    )


def route_b_qs(alias, lo=2):
    return derived(SpikeDerivedThing, thing_result(alias, lo))


def check_q1_params(alias):
    result = thing_result(alias, 2)
    assert result.alias == alias
    assert result.params == (2,)
    qs = (
        derived(SpikeDerivedThing, result)
        .annotate(tag=Value('x'))
        .filter(n__lt=7)
        .exclude(name=PAYLOAD)
        .order_by(Case(When(n=3, then=Value(0)), default=Value(1)), 'id')
    )
    sql, params = sql_and_params(qs)
    # text order: SELECT annotation, derived FROM, outer WHERE, ORDER BY
    assert params == ('x', 2, 7, PAYLOAD, 3, 0, 1)
    assert PAYLOAD not in sql
    rows = list(qs)
    assert [row.id for row in rows] == [3, 2, 5, 6, 7]
    for row in rows:
        assert isinstance(row, SpikeDerivedThing)
        assert row.name
        assert row.n is not None
    # integer-only variant for the placeholder-order check: every other order must change the rows or fail
    int_qs = (
        derived(SpikeDerivedThing, thing_result(alias, 2))
        .filter(n__lt=7)
        .exclude(n=4)
        .order_by(Case(When(n=3, then=Value(0)), default=Value(1)), 'id')
        .values_list('id', flat=True)
    )
    int_sql, int_params = sql_and_params(int_qs)
    assert int_params == (2, 7, 4, 3, 0, 1)
    expected = [(3,), (2,), (6,), (7,)]
    assert run_rows(alias, int_sql, int_params) == expected
    differing = 0
    for perm in sorted(set(itertools.permutations(int_params)) - {int_params}):
        try:
            got = run_rows(alias, int_sql, perm)
        except DatabaseError:
            differing += 1
            continue
        if got != expected:
            differing += 1
    assert differing > 0


def check_q2_pinned_alias(alias):
    qs = route_b_qs(alias)
    assert isinstance(qs, DerivedQuerySet)
    assert qs.db == alias
    assert qs.using(alias).db == alias
    assert ids(qs.using(alias)) == [2, 3, 5, 6, 7, 8]


def check_q2_mismatch(result_alias, query_alias):
    result = thing_result(result_alias)
    assert result.alias == result_alias
    qs = derived(SpikeDerivedThing, result).using(query_alias)
    message = mismatch_message(result_alias, query_alias)
    with pytest.raises(ValueError) as excinfo:
        sql_and_params(qs)
    assert str(excinfo.value) == message
    with pytest.raises(ValueError) as excinfo:
        list(qs)
    assert str(excinfo.value) == message


def label_result(template, alias, **slots):
    return compose(template, q=SpikeLabel.objects.using(alias).values('id', 'label'), **slots)


def check_q3_percent(alias):
    templates = [
        ("SELECT x.id, x.label AS name, x.id AS n FROM (%(q)s) x WHERE x.label = 'a%%'", {}, ()),
        (
            'SELECT x.id, x.label AS name, x.id AS n FROM (%(q)s) x '
            "WHERE x.id >= %(lo)s AND x.label = 'a%%' AND x.id <= %(hi)s",
            {'lo': 1, 'hi': 3},
            (1, 3),
        ),
    ]
    for template, slots, expected_params in templates:
        result = label_result(template, alias, **slots)
        assert result.params == expected_params
        qs = derived(SpikeDerivedThing, result)
        assert ids(qs) == [1]
        if not expected_params:
            assert sql_and_params(qs)[1] == ()
    # outer params before and after the embedded SQL
    result = label_result("SELECT x.id, x.label AS name, x.id AS n FROM (%(q)s) x WHERE x.label = 'a%%'", alias)
    qs = derived(SpikeDerivedThing, result).annotate(tag=Value('x')).filter(id__gte=1).exclude(name='zz')
    assert sql_and_params(qs)[1] == ('x', 1, 'zz')
    assert ids(qs) == [1]


def check_q4_lazy(alias):
    qs = route_b_qs(alias)
    with CaptureQueriesContext(connections[alias]) as captured:
        assert len(list(qs.filter(n__lt=7))) == 5
    assert len(captured) == 1
    assert 'sqlcompiler_thing' in captured[0]['sql']
    with CaptureQueriesContext(connections[alias]) as captured:
        assert qs.count() == 6
    assert len(captured) == 1
    assert 'sqlcompiler_thing' in captured[0]['sql']


def check_q6_roundtrip(alias):
    qs = route_b_qs(alias)
    assert ids(qs) == [2, 3, 5, 6, 7, 8]
    outer = compose('SELECT x.id FROM (%(q)s) x WHERE x.id > %(lo)s ORDER BY x.id', q=qs.values('id'), lo=3)
    assert outer.alias == alias
    assert outer.params == sql_and_params(qs.values('id'))[1] + (3,)
    assert fetch_rows(outer, dict) == [{'id': 5}, {'id': 6}, {'id': 7}, {'id': 8}]
    params = sql_and_params(qs)[1]
    assert type(params) is tuple
    assert params == (2,)
    for empty in (qs.none(), qs.filter(pk__in=[])):
        sql, empty_params = sql_and_params(empty)
        assert type(empty_params) is tuple
        assert run_rows(alias, sql, empty_params) == []
        assert list(empty) == []


def check_q6_executable_query(alias):
    qs = route_b_qs(alias)
    vendor = connections[alias].vendor
    if vendor not in ('postgresql', 'mysql'):
        with pytest.raises(NotImplementedError):
            qs.executable_query
        return
    sql = qs.executable_query
    assert '%s' not in sql
    with connections[alias].cursor() as cursor:
        cursor.execute(sql)
        assert sorted(row[0] for row in cursor.fetchall()) == [2, 3, 5, 6, 7, 8]
    none_sql = qs.none().executable_query
    with connections[alias].cursor() as cursor:
        cursor.execute(none_sql)
        assert list(cursor.fetchall()) == []


def check_q7_clone(alias):
    qs = route_b_qs(alias)
    expected_sql = sql_and_params(qs)
    expected_ids = ids(qs)
    assert expected_ids == [2, 3, 5, 6, 7, 8]
    assert sql_and_params(qs.all()) == expected_sql
    copied = copy.deepcopy(qs)
    assert sql_and_params(copied) == expected_sql
    assert ids(copied) == expected_ids
    fresh = DerivedQuerySet(model=SpikeDerivedThing, using=alias)
    fresh.query = pickle.loads(pickle.dumps(qs.query))
    assert sql_and_params(fresh) == expected_sql
    assert ids(fresh) == expected_ids
    tables = [t for t in fresh.query.alias_map.values() if hasattr(t, 'result')]
    assert len(tables) == 1
    assert tables[0].result.alias == alias
    assert tables[0].result.params == (2,)
    other_alias = 'sqlite_live' if alias != 'sqlite_live' else 'default'
    with pytest.raises(ValueError) as excinfo:
        sql_and_params(fresh.using(other_alias))
    assert str(excinfo.value) == mismatch_message(alias, other_alias)


def check_q5_no_deprecation(alias):
    with warnings.catch_warnings():
        warnings.simplefilter('error', DeprecationWarning)
        warnings.simplefilter('error', PendingDeprecationWarning)
        qs = route_b_qs(alias)
        assert ids(qs) == [2, 3, 5, 6, 7, 8]
        sub = route_b_qs(alias, 5).values('pk')
        nested = qs.filter(pk__in=sub)
        assert ids(nested) == [6, 7, 8]
        assert len(sql_and_params(nested)[1]) == 2


def check_thing_is_real(alias):
    assert Thing.objects.using(alias).count() == 8


def thing_snapshot(alias):
    return list(Thing.objects.using(alias).order_by('id').values_list('id', 'name', 'other', 'n'))


def item_snapshot(alias):
    return list(SpikeItem.objects.using(alias).order_by('id').values_list('id', 'thing_id', 'flag', 'label'))


def check_b_writes(alias):
    """
    Every write method on a derived queryset or row raises TypeError and the real tables stay as they were.
    refresh_from_db() is not refused: it builds a plain query on the placeholder table and fails as a DatabaseError.
    """

    things_before = thing_snapshot(alias)
    items_before = item_snapshot(alias)
    qs = route_b_qs(alias)
    obj = qs.order_by('id')[0]
    calls = [
        ('update', lambda: qs.update(n=1)),
        ('delete', lambda: qs.delete()),
        ('create', lambda: qs.create(id=99, name='x', n=1)),
        ('get_or_create', lambda: qs.get_or_create(id=99)),
        ('update_or_create', lambda: qs.update_or_create(id=99)),
        ('bulk_create', lambda: qs.bulk_create([SpikeDerivedThing(id=99, name='x')])),
        ('bulk_update', lambda: qs.bulk_update(list(qs[:1]), ['n'])),
        ('select_for_update', lambda: qs.select_for_update()),
        ('save', lambda: obj.save()),
        ('delete', lambda: obj.delete()),
    ]
    assert len(calls) == 10
    for name, call in calls:
        with pytest.raises(TypeError) as excinfo:
            call()
        assert name in str(excinfo.value)
        assert 'read-only' in str(excinfo.value)
    for coroutine in (lambda: qs.aupdate(n=1), lambda: qs.acreate(id=99, name='x')):
        with pytest.raises(TypeError) as excinfo:
            asyncio.run(coroutine())
        assert 'read-only' in str(excinfo.value)
    # refresh_from_db is not guarded: pinned as a DatabaseError (placeholder table) on every vendor
    with pytest.raises(DatabaseError):
        obj.refresh_from_db()
    assert thing_snapshot(alias) == things_before
    assert item_snapshot(alias) == items_before


def check_b_writes_hazard_unguarded_update(alias):
    """
    A plain QuerySet over an unmanaged model on the real table, given a DerivedTable like derived() does, is not
    guarded: update() compiles UPDATE <db_table> and ignores the derived FROM, so it changes every row.
    """

    before = thing_snapshot(alias)
    result = thing_result(alias, 2)
    selected = len(ids(derived(SpikeDerivedThing, result)))
    assert selected == 6
    with transaction.atomic(using=alias):
        qs = QuerySet(model=SpikeOverThing, using=alias)
        table_alias = qs.query.get_initial_alias()
        qs.query.alias_map[table_alias] = DerivedTable(SpikeOverThing._meta.db_table, table_alias, result)
        assert [row[0] for row in qs.order_by('id').values_list('id')] == [2, 3, 5, 6, 7, 8]
        changed = QuerySet.update(qs, n=100)
        assert changed == len(before)
        assert changed > selected
        transaction.set_rollback(True, using=alias)
    assert thing_snapshot(alias) == before


def check_b_rowshape(alias):
    """
    Row shape mismatches surface as driver errors at evaluation, not as fetch_rows()'s up-front sorted ValueError:
    a missing or renamed column is a DatabaseError, an extra column is silently ignored, order does not matter.
    A double-quoted upper-case alias fails only on PostgreSQL (case-folded names). On MySQL the quoted alias is
    accepted as a column name and matches case-insensitively.
    """

    vendor = connections[alias].vendor

    def shaped(select):
        return compose('SELECT {} FROM (%(q)s) x'.format(select), q=things(alias).values('id', 'name', 'n', 'other'))

    missing = shaped('x.id, x.name')
    with pytest.raises(DatabaseError):
        list(derived(SpikeDerivedThing, missing))
    assert sorted(derived(SpikeDerivedThing, missing).only('id', 'name').values_list('id', flat=True)) == list(
        range(1, 9)
    )
    assert sorted(derived(SpikeDerivedThing, missing).values_list('name', flat=True)) == sorted(
        Thing.objects.using(alias).values_list('name', flat=True)
    )

    renamed = shaped('x.id, x.name, x.n AS m')
    with pytest.raises(DatabaseError):
        list(derived(SpikeDerivedThing, renamed))

    extra = shaped('x.id, x.name, x.n, x.other')
    assert ids(derived(SpikeDerivedThing, extra)) == list(range(1, 9))

    reordered = shaped('x.n, x.name, x.id')
    got = derived(SpikeDerivedThing, reordered).order_by('id')
    assert [(row.id, row.n) for row in got] == list(Thing.objects.using(alias).order_by('id').values_list('id', 'n'))

    upper = shaped('x.id AS "ID", x.name, x.n')
    if vendor == 'postgresql':
        with pytest.raises(DatabaseError):
            list(derived(SpikeDerivedThing, upper))
    else:
        assert ids(derived(SpikeDerivedThing, upper)) == list(range(1, 9))

    dup = compose(
        'SELECT x.id, x.name, x.n FROM (%(q)s) x WHERE x.id = 1 UNION ALL '
        'SELECT y.id, y.name, y.n FROM (%(q)s) y WHERE y.id = 1',
        q=things(alias).values('id', 'name', 'n'),
    )
    assert [row.id for row in derived(SpikeDerivedThing, dup)] == [1, 1]

    # fetch_rows() rejects the same shapes up front, with one sorted ValueError, before any row is built
    @dataclasses.dataclass
    class Row:
        id: int
        name: str
        n: object

    for bad in (missing, renamed, extra):
        with pytest.raises(ValueError):
            fetch_rows(bad, Row)


def check_b_joins(alias):
    """Derived -> real FK joins work in both directions; a real model joining to the derived one cannot."""

    thing_one = Thing.objects.using(alias).get(pk=1).name
    items = compose(
        'SELECT x.id, x.thing_id, x.flag FROM (%(q)s) x WHERE x.id <= %(k)s',
        q=SpikeItem.objects.using(alias).values('id', 'thing_id', 'flag'),
        k=3,
    )
    item_qs = derived(SpikeDerivedItem, items)
    names = dict(Thing.objects.using(alias).values_list('id', 'name'))
    with CaptureQueriesContext(connections[alias]) as captured:
        rows = list(item_qs.select_related('thing').order_by('id'))
    assert len(captured) == 1
    assert [(row.id, row.thing.name) for row in rows] == [(1, names[1]), (2, names[1]), (3, names[2])]
    assert ids(item_qs.filter(thing__name=thing_one)) == [1, 2]

    qs = route_b_qs(alias)
    counts = list(qs.annotate(c=Count('items')).order_by('id').values_list('id', 'c'))
    assert counts == [(2, 1), (3, 1), (5, 0), (6, 0), (7, 0), (8, 0)]
    with CaptureQueriesContext(connections[alias]) as captured:
        prefetched = {row.id: sorted(i.id for i in row.items.all()) for row in qs.prefetch_related('items')}
    assert len(captured) == 2
    assert prefetched == {2: [3], 3: [4], 5: [], 6: [], 7: [], 8: []}
    excluded = qs.exclude(items__flag=True)
    sql = sql_and_params(excluded)[0]
    assert 'NOT EXISTS' in sql or 'NOT (' in sql
    assert ids(excluded) == [3, 5, 6, 7, 8]
    assert ids(Thing.objects.using(alias).filter(pk__in=qs.values('pk'))) == [2, 3, 5, 6, 7, 8]


def check_b_joins_hazard_real_to_derived(alias):
    """A real model with an FK *to* the derived model joins the placeholder table: a DatabaseError."""

    with pytest.raises(DatabaseError):
        list(SpikeItem.objects.using(alias).select_related('thing'))


def check_b_reads(alias):
    """The read API a derived queryset supports; select_related and prefetch_related are in check_b_joins."""

    qs = route_b_qs(alias)
    expected = [2, 3, 5, 6, 7, 8]
    assert qs.count() == len(expected)
    assert qs.exists()
    assert qs.filter(id=-1).exists() is False
    assert list(qs.none()) == []
    assert list(qs.order_by('id').values('id', 'name')) == [
        {'id': i, 'name': n}
        for i, n in Thing.objects.using(alias).filter(id__in=expected).order_by('id').values_list('id', 'name')
    ]
    assert list(qs.order_by('id').values_list('id', flat=True)) == expected
    assert qs.aggregate(total=Sum('n')) == {'total': 27}
    assert list(qs.annotate(double=F('n') * 2).order_by('id').values_list('id', 'double')) == [
        (2, 4),
        (3, 6),
        (5, 8),
        (6, 10),
        (7, 12),
        (8, 14),
    ]
    assert [row.id for row in qs.order_by('id').iterator()] == expected
    assert [row.id for row in qs.order_by('id')[1:3]] == [3, 5]
    paginator = Paginator(qs.order_by('id'), 2)
    assert paginator.count == 6
    assert [row.id for row in paginator.page(2).object_list] == [5, 6]
    low, high = qs.filter(n__lte=3), qs.filter(n__gte=6)
    union = low.values_list('id', flat=True).union(high.values_list('id', flat=True))
    assert sorted(union) == [2, 3, 7, 8]
    assert ids(low | high) == [2, 3, 7, 8]


def recipe(alias, result, refs=None, params=None):
    """The README 'Get a queryset back' recipe on a result selecting only id."""

    refs = refs or {'id': IntegerField()}
    cte = CTE(raw_cte_sql(result.sql, list(result.params) if params is None else params, refs))
    return cte, with_cte(cte, select=cte.join(Thing, id=cte.col.id))


def check_b_cte_compare(alias):
    """
    The three README django-cte limits against the native route.
    1. The CTE must be joined to a model: cte.queryset() fails with raw_cte_sql (AttributeError); the native route
       needs no join but needs a declared DerivedModel per row shape (its own requirement).
    2. No alias check: the recipe compiles for any alias; the native route raises the spike ValueError.
    3. Params documented as a list: a tuple works the same here.
    Pickling: the recipe's query cannot be pickled (local class), a deep copy works; the native route pickles.
    """

    result = compose('SELECT x.id FROM (%(q)s) x WHERE x.n >= %(lo)s', q=things(alias).values('id', 'n'), lo=2)
    cte, qs = recipe(alias, result)
    got = list(qs.using(alias).order_by('id'))
    assert [row.id for row in got] == [2, 3, 5, 6, 7, 8]
    assert all(type(row) is Thing for row in got)
    native = route_b_qs(alias)
    assert all(type(row) is SpikeDerivedThing for row in native)
    assert ids(native) == [2, 3, 5, 6, 7, 8]
    with pytest.raises(AttributeError):
        cte.queryset()

    other = 'sqlite_live' if alias == 'default' else 'default'
    sql, params = sql_and_params(qs.using(other))
    assert params == (2,)
    assert str(qs.using(other).query).startswith('WITH')
    with pytest.raises(ValueError) as excinfo:
        sql_and_params(native.using(other))
    assert str(excinfo.value) == mismatch_message(alias, other)

    _, tuple_qs = recipe(alias, result, params=result.params)
    assert ids(tuple_qs.using(alias).filter(n__lte=6)) == [2, 3, 5, 6, 7]
    _, list_qs = recipe(alias, result, params=list(result.params))
    assert ids(list_qs.using(alias).filter(n__lte=6)) == [2, 3, 5, 6, 7]
    assert sql_and_params(tuple_qs.using(alias).filter(n__lte=6)) == sql_and_params(
        list_qs.using(alias).filter(n__lte=6)
    )
    assert sql_and_params(tuple_qs.using(alias).filter(n__lte=6))[1] == (2, 6)

    assert ids(copy.deepcopy(qs).using(alias)) == [2, 3, 5, 6, 7, 8]
    with pytest.raises((pickle.PicklingError, AttributeError)):
        pickle.dumps(qs.query)
    assert ids(pickle.loads(pickle.dumps(native)).using(alias)) == [2, 3, 5, 6, 7, 8]

    label = compose(
        "SELECT x.id FROM (%(q)s) x WHERE x.label = 'a%%'", q=SpikeLabel.objects.using(alias).values('id', 'label')
    )
    assert label.params == ()
    _, label_qs = recipe(alias, label)
    assert [row.id for row in label_qs.using(alias)] == [1]


def check_b_mechanisms(alias):
    """Rejected mechanisms, pinned: SQL passed as a table name is quoted as an identifier and cannot carry params."""

    with pytest.raises(DatabaseError):
        list(Thing.objects.using(alias).extra(tables=['(SELECT 1 AS id) h']))
    qs = QuerySet(model=SpikeDerivedThing, using=alias)
    table_alias = qs.query.get_initial_alias()
    qs.query.alias_map[table_alias] = BaseTable('(SELECT id, name, n FROM sqlcompiler_thing) h', table_alias)
    with pytest.raises(DatabaseError):
        list(qs)


def check_b_trim_start(alias):
    """
    trim_start (called by split_exclude for multi-valued excludes) is probed with a spy on four shapes. Observed on
    Django 6.1.2: reached twice (the two multi-valued excludes), never on a query that holds a DerivedTable: the
    exclusion subquery is built over the related model and trims the join to the derived table away, so the
    derived SQL is never trimmed and all four results are correct. Shapes 2 and 3 do not reach trim_start.
    """

    seen = []
    original = Query.trim_start

    def spy(self, names_with_path):
        seen.append(any(isinstance(table, DerivedTable) for table in self.alias_map.values()))
        return original(self, names_with_path)

    items = compose(
        'SELECT x.id, x.thing_id, x.flag FROM (%(q)s) x WHERE x.id <= %(k)s',
        q=SpikeItem.objects.using(alias).values('id', 'thing_id', 'flag'),
        k=3,
    )
    Query.trim_start = spy
    try:
        shape1 = ids(route_b_qs(alias).exclude(items__flag=True))
        shape2 = ids(derived(SpikeDerivedItem, items).exclude(thing__name='x'))
        sub = route_b_qs(alias).values('pk')
        shape3 = ids(Thing.objects.using(alias).exclude(pk__in=sub))
        shape4 = ids(route_b_qs(alias).filter(items__flag=True).exclude(items__label='i1'))
    finally:
        Query.trim_start = original
    assert shape1 == [3, 5, 6, 7, 8]
    assert shape2 == [1, 2, 3]
    assert shape3 == [1, 4]
    assert shape4 == [2]
    assert seen
    assert not any(seen)
