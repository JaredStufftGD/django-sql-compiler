import copy
import itertools
import pickle
from decimal import Decimal

import pytest
from django.db import connections
from django.db.models import BooleanField, CharField, Exists, IntegerField, OuterRef, UUIDField, Value
from django.db.models.expressions import Expression, RawSQL
from django.db.utils import DatabaseError, NotSupportedError
from django.test.utils import CaptureQueriesContext

from sql_compiler import compose, fetch_rows, sql_and_params
from sql_compiler.spike_a import ResultExists, ResultIn

from .compose_cases import PAYLOAD
from .models import Thing
from .spike_models import UUID_1, SpikeLabel, SpikePair, SpikeUuid

# Thing rows get ids 1..8 in ROWS order; their n values are 1, 2, 3, None, 4, 5, 6, 7


def things(alias):
    return Thing.objects.using(alias)


def mismatch_message(what, result_alias, query_alias):
    return '{} was composed for database alias {!r} but the query runs on alias {!r}'.format(
        what, result_alias, query_alias
    )


class BoolProbe(Expression):
    def as_sql(self, compiler, connection):
        return '1 = 1', []


def exists_extra(alias):
    # Django compiles a conditional expression that is not an Exists as `<expr> = %s` (True) on backends
    # without a native boolean type (SQLite, MySQL), so ResultExists adds one trailing param there. Which
    # Django versions and backends do this differs, so the expectation is read from Django itself by
    # filtering on a plain boolean RawSQL expression and taking its params
    probe = things(alias).filter(BoolProbe(output_field=BooleanField()))
    return tuple(sql_and_params(probe)[1])


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


def driver(alias):
    vendor = connections[alias].vendor
    if vendor == 'postgresql':
        connections[alias].ensure_connection()
        module = type(connections[alias].connection).__module__.split('.')[0]
        return 'psycopg2' if module == 'psycopg2' else 'psycopg'
    return {'sqlite': 'sqlite3', 'mysql': 'mysqlclient'}[vendor]


def key_filter_result(alias, lo, hi):
    return compose(
        'SELECT x.id FROM (%(q)s) x WHERE x.n BETWEEN %(lo)s AND %(hi)s',
        q=things(alias).values('id', 'n'),
        lo=lo,
        hi=hi,
    )


def check_a_in_exists_join(alias):
    """Question a_in_exists_join: IN, EXISTS and a django-cte join select the same rows on every backend."""
    from django_cte import CTE, with_cte
    from django_cte.raw import raw_cte_sql

    result = key_filter_result(alias, 2, 5)
    in_qs = things(alias).filter(pk__in=ResultIn(result, 'id'))
    exists_qs = things(alias).filter(ResultExists(result, id='pk'))
    cte = CTE(raw_cte_sql(result.sql, list(result.params), {'id': IntegerField()}))
    join_qs = with_cte(cte, select=cte.join(Thing, id=cte.col.id)).using(alias)
    assert ids(in_qs) == [2, 3, 5, 6]
    assert ids(exists_qs) == [2, 3, 5, 6]
    assert ids(join_qs) == [2, 3, 5, 6]
    assert ' IN (SELECT k.' in sql_and_params(in_qs)[0]
    assert 'EXISTS (SELECT 1 FROM (' in sql_and_params(exists_qs)[0]
    assert sql_and_params(join_qs)[0].startswith('WITH')


def null_result(alias):
    # a NULL key next to the real ones: x.n > 2 selects ids 3, 5, 6, 7, 8
    return compose(
        'SELECT x.id FROM (%(q)s) x WHERE x.n > %(lo)s UNION ALL SELECT NULL',
        q=things(alias).values('id', 'n'),
        lo=2,
    )


def check_a_null(alias):
    """Question a_null: IN ignores a NULL key; the complement forms that stay correct (skip_null, NOT EXISTS)."""
    result = null_result(alias)
    assert ids(things(alias).filter(pk__in=ResultIn(result, 'id'))) == [3, 5, 6, 7, 8]
    assert ids(things(alias).exclude(pk__in=ResultIn(result, 'id', skip_null=True))) == [1, 2, 4]
    assert ids(things(alias).exclude(ResultExists(result, id='pk'))) == [1, 2, 4]


def check_a_null_hazard_not_in(alias):
    """Question a_null: NOT IN against a NULL key returns no rows at all (pinned hazard)."""
    result = null_result(alias)
    assert ids(things(alias).exclude(pk__in=ResultIn(result, 'id'))) == []


def pair_result(alias):
    return compose(
        'SELECT x.a AS a, x.b AS b FROM (%(q)s) x WHERE x.a = %(a)s AND x.b = %(b)s UNION ALL SELECT 2, 1',
        q=SpikePair.objects.using(alias).values('a', 'b'),
        a=1,
        b=2,
    )


def check_a_composite(alias):
    """Question a_composite: composite (a, b) keys through ResultExists and a non-pk key through ResultIn."""
    pairs = SpikePair.objects.using(alias)
    assert ids(pairs.filter(ResultExists(pair_result(alias), a='a', b='b'))) == [2, 3]
    labels = compose('SELECT x.label FROM (%(q)s) x WHERE x.a = %(a)s', q=pairs.values('a', 'label'), a=1)
    assert ids(pairs.filter(label__in=ResultIn(labels, 'label', output_field=CharField()))) == [1, 2]


def check_a_composite_row_value(alias):
    """Question a_composite: row-value IN through a boolean RawSQL."""
    pairs = SpikePair.objects.using(alias)
    r = pair_result(alias)
    raw = RawSQL('(a, b) IN (SELECT k.a, k.b FROM (' + r.sql + ') k)', r.params, output_field=BooleanField())
    assert ids(pairs.filter(raw)) == [2, 3]


def check_a_keytypes(alias):
    """Question a_keytypes: UUID keys selected in the database, and MySQL Decimal sums as keys."""
    spike = SpikeUuid.objects.using(alias)
    r = compose('SELECT x.id FROM (%(q)s) x WHERE x.name = %(n)s', q=spike.values('id', 'name'), n='u1')
    got = list(spike.filter(pk__in=ResultIn(r, 'id', output_field=UUIDField())).values_list('id', flat=True))
    assert got == [UUID_1]

    sums = compose('SELECT SUM(x.n) AS s FROM (%(q)s) x WHERE x.n <= %(k)s', q=things(alias).values('n'), k=3)
    rows = fetch_rows(sums, dict)
    expected_type = Decimal if connections[alias].vendor == 'mysql' else int
    assert type(rows[0]['s']) is expected_type
    assert rows[0]['s'] == 6
    via_route = ids(things(alias).filter(n__in=ResultIn(sums, 's')))
    via_list = ids(things(alias).filter(n__in=[row['s'] for row in rows]))
    assert via_route == via_list == [7]


UUID_TEXT = '00000000-0000-4000-8000-000000000001'


def uuid_param_outcome(alias, value):
    spike = SpikeUuid.objects.using(alias)
    r = compose('SELECT %(u)s AS id FROM (%(q)s) x LIMIT 1', q=spike.values('id'), u=value)
    try:
        qs = spike.filter(pk__in=ResultIn(r, 'id', output_field=UUIDField()))
        return ('rows', list(qs.values_list('id', flat=True)))
    except Exception as exc:
        return ('error', type(exc).__name__)


# (dashed text param, uuid.UUID param) outcomes observed on every driver setup, locked Django 6.1.2
UUID_PINS = {
    ('sqlite', 'sqlite3'): (('rows', []), ('error', 'ProgrammingError')),
    ('mysql', 'mysqlclient'): (('rows', []), ('rows', [])),
    ('postgresql', 'psycopg2'): (('error', 'ProgrammingError'), ('rows', [UUID_1])),
    ('postgresql', 'psycopg'): (('error', 'ProgrammingError'), ('rows', [UUID_1])),
}


def check_a_keytypes_hazard_uuid_params(alias):
    """Question a_keytypes: a UUID value as a bound param key, as dashed text and as a uuid.UUID (pinned per driver)."""
    outcome = (uuid_param_outcome(alias, UUID_TEXT), uuid_param_outcome(alias, UUID_1))
    assert outcome == UUID_PINS[(connections[alias].vendor, driver(alias))]


def duplicate_result(alias):
    return compose(
        'SELECT x.id FROM (%(q)s) x WHERE x.id = %(i)s UNION ALL SELECT y.id FROM (%(q)s) y WHERE y.id = %(i)s',
        q=things(alias).values('id'),
        i=1,
    )


def check_a_duplicates(alias):
    """Question a_duplicates: a key repeated in the result is returned once by IN and EXISTS."""
    result = duplicate_result(alias)
    assert ids(things(alias).filter(pk__in=ResultIn(result, 'id'))) == [1]
    assert ids(things(alias).filter(ResultExists(result, id='pk'))) == [1]


def check_a_duplicates_hazard_join(alias):
    """Question a_duplicates: the django-cte join returns a repeated key's row once per repetition (hazard)."""
    from django_cte import CTE, with_cte
    from django_cte.raw import raw_cte_sql

    result = duplicate_result(alias)
    cte = CTE(raw_cte_sql(result.sql, list(result.params), {'id': IntegerField()}))
    join_qs = with_cte(cte, select=cte.join(Thing, id=cte.col.id)).using(alias)
    assert ids(join_qs) == [1, 1]


def limit_result(alias):
    return compose('SELECT x.id FROM (%(q)s) x ORDER BY x.id LIMIT %(k)s', q=things(alias).values('id'), k=2)


def check_a_mysql_limit(alias):
    """Question a_mysql_limit: a LIMIT inside the composed SQL works through ResultIn on every backend."""
    r = limit_result(alias)
    assert ids(things(alias).filter(pk__in=ResultIn(r, 'id'))) == [1, 2]


def check_a_mysql_limit_hazard_rawsql(alias):
    """Question a_mysql_limit: a bare RawSQL IN (... LIMIT) is rejected by MySQL only (error 1235, hazard)."""
    r = limit_result(alias)
    qs = things(alias).filter(pk__in=RawSQL(r.sql, r.params))
    if connections[alias].vendor == 'mysql':
        with pytest.raises(NotSupportedError):
            list(qs)
    else:
        assert ids(qs) == [1, 2]
