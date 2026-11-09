import copy
import itertools
import pickle
import warnings

import pytest
from django.db import connections
from django.db.models import Case, Value, When
from django.db.utils import DatabaseError
from django.test.utils import CaptureQueriesContext

from sql_compiler import compose, fetch_rows, sql_and_params
from sql_compiler.spike_b import DerivedQuerySet, derived

from .compose_cases import PAYLOAD
from .models import Thing
from .spike_a_cases import ids, run_rows, things
from .spike_models import SpikeDerivedThing, SpikeLabel

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
