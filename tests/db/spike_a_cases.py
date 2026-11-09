import copy
import itertools
import pickle

import pytest
from django.db import connections
from django.db.models import Exists, OuterRef, Value
from django.db.models.expressions import RawSQL
from django.db.utils import DatabaseError
from django.test.utils import CaptureQueriesContext

from sql_compiler import compose, fetch_rows, sql_and_params
from sql_compiler.spike_a import ResultExists, ResultIn

from .compose_cases import PAYLOAD
from .models import Thing
from .spike_models import SpikeLabel

# Thing rows get ids 1..8 in ROWS order; their n values are 1, 2, 3, None, 4, 5, 6, 7


def things(alias):
    return Thing.objects.using(alias)


def mismatch_message(what, result_alias, query_alias):
    return '{} was composed for database alias {!r} but the query runs on alias {!r}'.format(
        what, result_alias, query_alias
    )


def exists_extra(alias):
    # Django compiles a conditional expression that is not an Exists as `<expr> = %s` (True) on backends
    # without a native boolean type (SQLite, MySQL), so ResultExists adds one trailing param there
    return () if connections[alias].features.has_native_boolean_field else (True,)


def ids(qs):
    return list(qs.order_by('id').values_list('id', flat=True))


def run_rows(alias, sql, params):
    with connections[alias].cursor() as cursor:
        cursor.execute(sql, params)
        return [tuple(row) for row in cursor.fetchall()]


def composed_keys(alias, lo):
    # a result composed for alias through a queryset of that alias
    return compose('SELECT x.id FROM (%(q)s) x WHERE x.n > %(lo)s', q=things(alias).values('id', 'n'), lo=lo)


def route_a_qs(alias, lo=4):
    result = composed_keys(alias, lo)
    return things(alias).filter(pk__in=ResultIn(result, 'id'))


def check_q1_params(alias):
    result = compose(
        'SELECT x.id FROM (%(q)s) x WHERE x.n > %(lo)s AND x.name <> %(bad)s',
        q=things(alias).values('id', 'n', 'name'),
        lo=2,
        bad=PAYLOAD,
    )
    assert result.alias == alias
    assert result.params == (2, PAYLOAD)
    qs = (
        things(alias)
        .annotate(tag=Value('x'))
        .filter(n__lt=7)
        .filter(pk__in=ResultIn(result, 'id'))
        .exclude(name='plain')
        .annotate(has_more=Exists(things(alias).filter(n__gt=OuterRef('n'))))
    )
    sql, params = sql_and_params(qs)
    # Django's own Exists annotation may carry params (Django 6.1 binds its LIMIT), so take them from Django
    exists_params = sql_and_params(things(alias).annotate(has_more=Exists(things(alias).filter(n__gt=OuterRef('n')))))[
        1
    ]
    assert params == ('x',) + exists_params + (7, 2, PAYLOAD, 'plain')
    assert PAYLOAD not in sql
    assert ids(qs) == [3, 6, 7]

    # integer-only variant for the placeholder-order permutation check
    int_result = compose(
        'SELECT x.id FROM (%(q)s) x WHERE x.n > %(lo)s AND x.n < %(hi)s', q=things(alias).values('id', 'n'), lo=2, hi=6
    )
    int_qs = things(alias).filter(n__lt=7).filter(pk__in=ResultIn(int_result, 'id')).exclude(n=4)
    int_sql, int_params = sql_and_params(int_qs.order_by('id').values_list('id', flat=True))
    assert int_params == (7, 2, 6, 4)
    expected = [(3,), (6,)]
    assert run_rows(alias, int_sql, int_params) == expected
    differing = 0
    for perm in sorted(set(itertools.permutations(int_params)) - {int_params}):
        try:
            rows = run_rows(alias, int_sql, perm)
        except DatabaseError:
            differing += 1
            continue
        if rows != expected:
            differing += 1
    assert differing > 0


def check_q2_same_alias(alias):
    result = composed_keys(alias, 2)
    explicit = things(alias).filter(pk__in=ResultIn(result, 'id'))
    assert ids(explicit) == [3, 5, 6, 7, 8]
    assert sql_and_params(explicit)[1] == (2,)
    manager = Thing.objects.all() if alias == 'default' else Thing.objects.db_manager(alias).all()
    assert manager.db == alias
    implicit = manager.filter(pk__in=ResultIn(result, 'id'))
    assert ids(implicit) == [3, 5, 6, 7, 8]
    exists = things(alias).filter(ResultExists(result, id='pk'))
    assert ids(exists) == [3, 5, 6, 7, 8]
    assert sql_and_params(exists)[1] == (2,) + exists_extra(alias)


def check_q2_mismatch(result_alias, query_alias):
    result = composed_keys(result_alias, 2)
    assert result.alias == result_alias
    in_qs = things(query_alias).filter(pk__in=ResultIn(result, 'id'))
    message = mismatch_message('ResultIn', result_alias, query_alias)
    with pytest.raises(ValueError) as excinfo:
        sql_and_params(in_qs)
    assert str(excinfo.value) == message
    with pytest.raises(ValueError) as excinfo:
        list(in_qs)
    assert str(excinfo.value) == message
    exists_qs = things(query_alias).filter(ResultExists(result, id='pk'))
    message = mismatch_message('ResultExists', result_alias, query_alias)
    with pytest.raises(ValueError) as excinfo:
        sql_and_params(exists_qs)
    assert str(excinfo.value) == message
    with pytest.raises(ValueError) as excinfo:
        list(exists_qs)
    assert str(excinfo.value) == message


def check_q2_hazard_rawsql_no_alias_check(result_alias, query_alias):
    result = composed_keys(result_alias, 2)
    qs = things(query_alias).filter(pk__in=RawSQL(result.sql, result.params))
    sql, params = sql_and_params(qs)
    assert params == (2,)
    assert result.sql in sql


def check_q3_percent(alias):
    label = SpikeLabel.objects.using(alias)
    src = label.values('id', 'label')
    templates = [
        ("SELECT x.id FROM (%(q)s) x WHERE x.label = 'a%%'", {}, ()),
        (
            "SELECT x.id FROM (%(q)s) x WHERE x.id >= %(lo)s AND x.label = 'a%%' AND x.id <= %(hi)s",
            {'lo': 1, 'hi': 3},
            (1, 3),
        ),
    ]
    for template, slots, expected_params in templates:
        result = compose(template, q=src, **slots)
        assert result.params == expected_params
        in_qs = label.filter(pk__in=ResultIn(result, 'id'))
        assert ids(in_qs) == [1]
        exists_qs = label.filter(ResultExists(result, id='pk'))
        assert ids(exists_qs) == [1]
        if not expected_params:
            assert sql_and_params(in_qs)[1] == ()
            assert sql_and_params(exists_qs)[1] == exists_extra(alias)
    # outer params before and after the embedded SQL
    result = compose("SELECT x.id FROM (%(q)s) x WHERE x.label = 'a%%'", q=src)
    in_qs = label.filter(id__gte=1).filter(pk__in=ResultIn(result, 'id')).exclude(label='zz')
    assert sql_and_params(in_qs)[1] == (1, 'zz')
    assert ids(in_qs) == [1]
    exists_qs = label.filter(id__gte=1).filter(ResultExists(result, id='pk')).exclude(label='zz')
    assert sql_and_params(exists_qs)[1] == (1,) + exists_extra(alias) + ('zz',)
    assert ids(exists_qs) == [1]


def check_q4_lazy(alias):
    result = composed_keys(alias, 2)
    for qs in (
        things(alias).filter(pk__in=ResultIn(result, 'id')),
        things(alias).filter(ResultExists(result, id='pk')),
    ):
        with CaptureQueriesContext(connections[alias]) as captured:
            assert len(list(qs)) == 5
        assert len(captured) == 1
        assert 'sqlcompiler_thing' in captured[0]['sql']
        assert captured[0]['sql'].count('SELECT') >= 3


def check_q6_roundtrip(alias):
    qs = route_a_qs(alias)
    assert ids(qs) == [6, 7, 8]
    outer = compose('SELECT x.id FROM (%(q)s) x WHERE x.id > %(lo)s ORDER BY x.id', q=qs.values('id'), lo=0)
    assert outer.alias == alias
    assert outer.params == sql_and_params(qs.values('id'))[1] + (0,)
    assert fetch_rows(outer, dict) == [{'id': 6}, {'id': 7}, {'id': 8}]
    params = sql_and_params(qs)[1]
    assert type(params) is tuple
    assert params == (4,)
    for empty in (qs.none(), qs.filter(pk__in=[])):
        sql, empty_params = sql_and_params(empty)
        assert type(empty_params) is tuple
        assert run_rows(alias, sql, empty_params) == []
        assert list(empty) == []


def check_q6_executable_query(alias):
    qs = route_a_qs(alias)
    vendor = connections[alias].vendor
    if vendor not in ('postgresql', 'mysql'):
        with pytest.raises(NotImplementedError):
            qs.executable_query
        return
    sql = qs.executable_query
    assert '%s' not in sql
    with connections[alias].cursor() as cursor:
        cursor.execute(sql)
        assert sorted(row[0] for row in cursor.fetchall()) == [6, 7, 8]
    none_sql = qs.none().executable_query
    with connections[alias].cursor() as cursor:
        cursor.execute(none_sql)
        assert list(cursor.fetchall()) == []


def check_q7_clone(alias):
    qs = route_a_qs(alias)
    expected_sql = sql_and_params(qs)
    expected_ids = ids(qs)
    assert expected_ids == [6, 7, 8]
    assert sql_and_params(qs.all()) == expected_sql
    copied = copy.deepcopy(qs)
    assert sql_and_params(copied) == expected_sql
    assert ids(copied) == expected_ids
    fresh = Thing.objects.db_manager(alias).all()
    fresh.query = pickle.loads(pickle.dumps(qs.query))
    assert sql_and_params(fresh) == expected_sql
    assert ids(fresh) == expected_ids
    other_alias = 'sqlite_live' if alias != 'sqlite_live' else 'default'
    with pytest.raises(ValueError) as excinfo:
        sql_and_params(fresh.using(other_alias))
    assert str(excinfo.value) == mismatch_message('ResultIn', alias, other_alias)
