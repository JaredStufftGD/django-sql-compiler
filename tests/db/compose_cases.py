import itertools

from django.db.models import F

from sql_compiler import ComposeResult, compose, sql_and_params

from . import shapes
from .cases import ROWS
from .models import Thing

PAYLOAD = "x'); DROP TABLE sqlcompiler_thing; -- 100% %(x)s %s %%"


def things(alias):
    return Thing.objects.using(alias)


def cte_join(alias):
    t = things(alias)
    a = t.filter(n__gte=3).values('id', 'n')
    b = t.filter(n__lte=5).values('id', 'n')
    a_sql, a_params = sql_and_params(a)
    b_sql, b_params = sql_and_params(b)
    result = compose(
        'WITH a AS (%(a)s), b AS (%(b)s) SELECT a.n FROM a JOIN b ON a.id = b.id ORDER BY a.n', a=a, b=b
    )
    ref_sql = 'WITH a AS ({}), b AS ({}) SELECT a.n FROM a JOIN b ON a.id = b.id ORDER BY a.n'.format(a_sql, b_sql)
    return {
        'result': result,
        'ref_sql': ref_sql,
        'ref_params': a_params + b_params,
        'params': (3, 5),
        'rows': [(3,), (4,), (5,)],
    }


def reordered_slots(alias):
    t = things(alias)
    a = t.filter(n__gte=3).values('id', 'n')
    b = t.filter(n__lte=5).values('id', 'n')
    a_sql, a_params = sql_and_params(a)
    b_sql, b_params = sql_and_params(b)
    result = compose(
        'WITH b AS (%(b)s), a AS (%(a)s) SELECT a.n FROM a JOIN b ON a.id = b.id ORDER BY a.n', a=a, b=b
    )
    ref_sql = 'WITH b AS ({}), a AS ({}) SELECT a.n FROM a JOIN b ON a.id = b.id ORDER BY a.n'.format(b_sql, a_sql)
    return {
        'result': result,
        'ref_sql': ref_sql,
        'ref_params': b_params + a_params,
        'params': (5, 3),
        'rows': [(3,), (4,), (5,)],
    }


def reused_queryset(alias):
    t = things(alias)
    a = t.filter(n__gte=3, n__lte=6).values('id', 'n')
    b = t.filter(n__lte=5).values('id', 'n')
    a_sql, a_params = sql_and_params(a)
    b_sql, b_params = sql_and_params(b)
    result = compose(
        'SELECT (SELECT COUNT(*) FROM (%(a)s) x), (SELECT COUNT(*) FROM (%(b)s) y), '
        '(SELECT MAX(z.n) FROM (%(a)s) z)',
        a=a,
        b=b,
    )
    ref_sql = (
        'SELECT (SELECT COUNT(*) FROM ({}) x), (SELECT COUNT(*) FROM ({}) y), (SELECT MAX(z.n) FROM ({}) z)'
    ).format(a_sql, b_sql, a_sql)
    return {
        'result': result,
        'ref_sql': ref_sql,
        'ref_params': a_params + b_params + a_params,
        'params': (3, 6, 5, 3, 6),
        'rows': [(4, 5, 6)],
    }


def reused_value(alias):
    t = things(alias)
    a = t.filter(n__lte=6).values('id', 'n')
    b = t.filter(n__gte=4).values('id', 'n')
    a_sql, a_params = sql_and_params(a)
    b_sql, b_params = sql_and_params(b)
    result = compose(
        'SELECT x.n FROM (%(a)s) x WHERE x.n > %(lo)s '
        'AND x.id IN (SELECT y.id FROM (%(b)s) y WHERE y.n <> %(lo)s) ORDER BY x.n',
        a=a,
        b=b,
        lo=2,
    )
    ref_sql = (
        'SELECT x.n FROM ({}) x WHERE x.n > %s '
        'AND x.id IN (SELECT y.id FROM ({}) y WHERE y.n <> %s) ORDER BY x.n'
    ).format(a_sql, b_sql)
    return {
        'result': result,
        'ref_sql': ref_sql,
        'ref_params': a_params + (2,) + b_params + (2,),
        'params': (6, 2, 4, 2),
        'rows': [(4,), (5,), (6,)],
    }


def nested(alias):
    t = things(alias)
    q = t.filter(n__gte=1).values('id', 'n')
    q_sql, q_params = sql_and_params(q)
    inner = compose("SELECT x.id, x.n, '%%' AS pct FROM (%(q)s) x WHERE x.n > %(lo)s", q=q, lo=2)
    result = compose(
        'WITH i AS (%(inner)s) SELECT i.n, i.pct FROM i WHERE i.n < %(hi)s ORDER BY i.n', inner=inner, hi=6
    )
    inner_ref = "SELECT x.id, x.n, '%%' AS pct FROM ({}) x WHERE x.n > %s".format(q_sql)
    ref_sql = 'WITH i AS ({}) SELECT i.n, i.pct FROM i WHERE i.n < %s ORDER BY i.n'.format(inner_ref)
    return {
        'result': result,
        'inner': inner,
        'ref_sql': ref_sql,
        'ref_params': q_params + (2,) + (6,),
        'params': (1, 2, 6),
        'rows': [(3, '%'), (4, '%'), (5, '%')],
    }


def bound_value(alias):
    q = things(alias).filter(n__isnull=False).values('id', 'n', 'name')
    q_sql, q_params = sql_and_params(q)
    result = compose(
        'SELECT x.n FROM (%(q)s) x WHERE (x.name = %(name)s AND x.n < 3 OR x.name = %(pct)s AND x.n > 2) '
        'AND x.name <> %(v)s ORDER BY x.n',
        q=q,
        name="it's",
        pct='plain %',
        v=PAYLOAD,
    )
    ref_sql = (
        'SELECT x.n FROM ({}) x WHERE (x.name = %s AND x.n < 3 OR x.name = %s AND x.n > 2) '
        'AND x.name <> %s ORDER BY x.n'
    ).format(q_sql)
    return {
        'result': result,
        'ref_sql': ref_sql,
        'ref_params': q_params + ("it's", 'plain %', PAYLOAD),
        'params': ("it's", 'plain %', PAYLOAD),
        'rows': [(1,), (3,)],
    }


def template_percent(alias):
    q = things(alias).filter(n__lte=6).values('id', 'n', 'name')
    q_sql, q_params = sql_and_params(q)
    result = compose("SELECT x.n FROM (%(q)s) x WHERE x.name LIKE 'plain%%' ORDER BY x.n", q=q)
    ref_sql = "SELECT x.n FROM ({}) x WHERE x.name LIKE 'plain%%' ORDER BY x.n".format(q_sql)
    return {
        'result': result,
        'ref_sql': ref_sql,
        'ref_params': q_params,
        'params': (6,),
        'rows': [(3,), (4,)],
    }


def template_percent_no_params(alias):
    q = things(alias).values('id', 'n')
    q_sql, q_params = sql_and_params(q)
    result = compose("SELECT '%%' AS p, x.n FROM (%(q)s) x WHERE x.n = 3", q=q)
    ref_sql = "SELECT '%%' AS p, x.n FROM ({}) x WHERE x.n = 3".format(q_sql)
    return {
        'result': result,
        'ref_sql': ref_sql,
        'ref_params': q_params,
        'params': (),
        'rows': [('%', 3)],
    }


def embedded_percent(alias):
    c = things(alias).filter(name__contains=F('other'), n__gt=0).values('id', 'n')
    c_sql, c_params = sql_and_params(c)
    result = compose('SELECT x.n FROM (%(c)s) x WHERE x.n < %(hi)s ORDER BY x.n', c=c, hi=3)
    ref_sql = 'SELECT x.n FROM ({}) x WHERE x.n < %s ORDER BY x.n'.format(c_sql)
    return {
        'result': result,
        'ref_sql': ref_sql,
        'ref_params': c_params + (3,),
        'params': (0, 3),
        'rows': [(2,)],
    }


def empty_queryset(alias):
    t = things(alias)
    e = t.none().values('id', 'n')
    a = t.filter(n__gte=3).values('id', 'n')
    e_sql, e_params = sql_and_params(e)
    a_sql, a_params = sql_and_params(a)
    result = compose(
        'SELECT (SELECT COUNT(*) FROM (%(e)s) x), '
        '(SELECT COUNT(*) FROM (%(a)s) y WHERE y.n > %(lo)s)',
        e=e,
        a=a,
        lo=4,
    )
    ref_sql = 'SELECT (SELECT COUNT(*) FROM ({}) x), (SELECT COUNT(*) FROM ({}) y WHERE y.n > %s)'.format(
        e_sql, a_sql
    )
    return {
        'result': result,
        'ref_sql': ref_sql,
        'ref_params': e_params + a_params + (4,),
        'params': e_params + (3, 4),
        'rows': [(0, 3)],
    }


SCENARIOS = {
    'cte_join': cte_join,
    'reordered_slots': reordered_slots,
    'reused_queryset': reused_queryset,
    'reused_value': reused_value,
    'nested': nested,
    'bound_value': bound_value,
    'template_percent': template_percent,
    'template_percent_no_params': template_percent_no_params,
    'embedded_percent': embedded_percent,
    'empty_queryset': empty_queryset,
}
SCENARIO_IDS = list(SCENARIOS)


def fetch(alias, sql, params):
    rows, _ = shapes.run_pair(alias, sql, params)
    return [tuple(row) for row in rows]


def check_scenario(alias, scenario_id):
    case = SCENARIOS[scenario_id](alias)
    result = case['result']
    ref_sql = case['ref_sql']
    ref_params = case['ref_params']
    rows = case['rows']
    assert type(result) is ComposeResult
    assert result.alias == alias
    assert type(result.sql) is str
    assert type(result.params) is tuple
    assert result.sql == ref_sql
    assert result.params == ref_params == case['params']
    composed_rows = fetch(alias, *result)
    assert composed_rows == fetch(alias, ref_sql, ref_params)
    assert composed_rows == rows
    # template_percent and template_percent_no_params have fewer than two params, so no other order exists.
    if len(ref_params) >= 2:
        # a str bound against an integer column is a type error on PostgreSQL and a backend-specific
        # coercion on SQLite and MySQL, so its rows say nothing about the fixture
        assert len({type(p) for p in ref_params}) == 1, '{} binds params of mixed types'.format(scenario_id)
        for perm in sorted(set(itertools.permutations(ref_params)) - {ref_params}, key=repr):
            assert fetch(alias, ref_sql, perm) != rows, '{} returns the expected rows with params {!r}'.format(
                scenario_id, perm
            )
    if scenario_id == 'nested':
        assert "'%%'" in result.sql
        assert case['inner'].alias == alias
    if scenario_id == 'bound_value':
        assert PAYLOAD not in result.sql
        assert 'DROP' not in result.sql
        assert result.params[-1] == PAYLOAD
        assert Thing.objects.using(alias).count() == len(ROWS)
    if scenario_id == 'template_percent_no_params':
        assert result.params == ()
    if scenario_id == 'embedded_percent':
        assert '%%' in result.sql


def check_raw(alias):
    result = compose(
        'SELECT * FROM (%(q)s) x WHERE x.n > %(lo)s', q=Thing.objects.using(alias).filter(n__lte=6), lo=2
    )
    objs = list(Thing.objects.raw(*result, using=result.alias))
    expected = set(Thing.objects.using(alias).filter(n__lte=6, n__gt=2).values_list('pk', flat=True))
    assert len(expected) == 4
    assert {o.pk for o in objs} == expected
    assert all(o._state.db == alias for o in objs)
