import copy
import inspect
import pickle
from collections import namedtuple

import django.db.models.sql.query
import pytest
from django.db import connections
from django.db.models import Exists, F, Q, Subquery, Value
from django.test import override_settings

import sql_compiler
from sql_compiler import ComposeResult, compose, composition, sql_and_params
from sql_compiler import utils

from tests import dbconfig
from tests.db import compose_cases
from tests.db.models import PlainThing, Thing

Pair = namedtuple('Pair', ['sql', 'params'])

REJECTED = {
    'manager': (lambda: Thing.objects, 'SQLCompilerManager'),
    'plain_manager': (lambda: PlainThing.objects, 'Manager'),
    'raw_queryset': (lambda: Thing.objects.raw('select 1'), 'RawQuerySet'),
    'query': (lambda: Thing.objects.all().query, 'Query'),
    'subquery': (lambda: Subquery(Thing.objects.values('id')), 'Subquery'),
    'exists': (lambda: Exists(Thing.objects.all()), 'Exists'),
    'f': (lambda: F('n'), 'F'),
    'value': (lambda: Value(1), 'Value'),
    'q': (lambda: Q(n=1), 'Q'),
}

POSITIONAL = (
    'compose template has a positional %s or a lone % at position {}; write a literal % as %%'
)
PAREN = 'compose template has a %(...) form other than %(name)s at position {}'
TUPLE_MESSAGE = (
    "compose slot 'p' holds a tuple; pass the QuerySet or a compose() result itself, "
    "not a (sql, params) pair"
)


@pytest.fixture(autouse=True)
def default_never_connects():
    yield
    if dbconfig.STATE['default'] == 'sqlite':
        assert connections['default'].connection is None


def spy_on_get_compiler(monkeypatch):
    original = django.db.models.sql.query.Query.get_compiler
    seen = []

    def spy(self, *args, **kwargs):
        seen.append(kwargs.get('using', args[0] if args else None))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(django.db.models.sql.query.Query, 'get_compiler', spy)
    return seen


def test_compose_is_exported():
    assert 'compose' in sql_compiler.__all__
    assert 'ComposeResult' in sql_compiler.__all__
    assert sql_compiler.compose is composition.compose
    assert sql_compiler.ComposeResult is composition.ComposeResult
    assert inspect.ismodule(sql_compiler.composition)


def test_queryset_and_value_slots_compose_exactly():
    qs = Thing.objects.filter(n__lte=6).values('id', 'n')
    sq, pq = sql_and_params(qs)
    result = compose('SELECT x.n FROM (%(q)s) x WHERE x.n > %(lo)s', q=qs, lo=2)
    assert result == ('SELECT x.n FROM ({}) x WHERE x.n > %s'.format(sq), pq + (2,))
    assert result.params == (6, 2)


def test_slots_follow_placeholder_order_not_keyword_order():
    a = Thing.objects.filter(n__gte=3).values('id', 'n')
    b = Thing.objects.filter(n__lte=5).values('id', 'n')
    sa, pa = sql_and_params(a)
    sb, pb = sql_and_params(b)
    template = 'WITH b AS (%(b)s), a AS (%(a)s) SELECT a.n FROM a JOIN b ON a.id = b.id'
    result = compose(template, a=a, b=b)
    assert result.params == (5, 3)
    assert result.sql == 'WITH b AS ({}), a AS ({}) SELECT a.n FROM a JOIN b ON a.id = b.id'.format(sb, sa)


def test_reused_slots_repeat_their_params():
    a = Thing.objects.filter(n__gte=3, n__lte=6).values('id', 'n')
    sa, pa = sql_and_params(a)
    assert pa == (3, 6)
    template = (
        'SELECT x.n FROM (%(a)s) x WHERE x.n <> %(v)s '
        'AND x.id IN (SELECT y.id FROM (%(a)s) y WHERE y.n <> %(v)s)'
    )
    result = compose(template, a=a, v=7)
    assert result.params == (3, 6, 7, 3, 6, 7)
    assert result.sql == (
        'SELECT x.n FROM ({0}) x WHERE x.n <> %s '
        'AND x.id IN (SELECT y.id FROM ({0}) y WHERE y.n <> %s)'
    ).format(sa)


def test_reused_queryset_is_compiled_once(monkeypatch):
    seen = spy_on_get_compiler(monkeypatch)
    qs = Thing.objects.filter(n__gte=3).values('id')
    compose('%(q)s UNION ALL %(q)s UNION ALL %(q)s', q=qs)
    assert len(seen) == 1


def test_template_percent_stays_doubled_including_nested():
    inner = compose("SELECT '%%' AS p, x.n FROM (%(q)s) x", q=Thing.objects.values('id', 'n'))
    assert "'%%'" in inner.sql
    assert inner.params == ()
    outer = compose('WITH i AS (%(i)s) SELECT i.p FROM i', i=inner)
    assert outer.sql == 'WITH i AS ({}) SELECT i.p FROM i'.format(inner.sql)
    assert "'%%'" in outer.sql
    assert outer.params == ()
    assert outer.alias == 'default'


def test_embedded_double_percent_is_not_reparsed():
    c = Thing.objects.filter(name__contains=F('other'), n__gt=0).values('id', 'n')
    sc, pc = sql_and_params(c)
    assert '%%' in sc
    result = compose('SELECT x.n FROM (%(c)s) x WHERE x.n < %(hi)s', c=c, hi=3)
    assert result.sql == 'SELECT x.n FROM ({}) x WHERE x.n < %s'.format(sc)
    assert result.params == pc + (3,)


def test_value_is_bound_not_interpolated():
    payload = "x'); DROP TABLE sqlcompiler_thing; -- 100% %(x)s %s %%"
    qs = Thing.objects.filter(n__lte=6).values('id', 'n')
    sq, pq = sql_and_params(qs)
    result = compose('SELECT x.n FROM (%(q)s) x WHERE x.name = %(v)s', q=qs, v=payload)
    assert result.sql == 'SELECT x.n FROM ({}) x WHERE x.name = %s'.format(sq)
    assert payload not in result.sql
    assert 'DROP' not in result.sql
    assert result.params == pq + (payload,)


def test_list_value_passes_unchanged():
    qs = Thing.objects.values('id')
    values = [1, 2]
    result = compose('SELECT * FROM (%(q)s) x WHERE x.id = ANY(%(v)s)', q=qs, v=values)
    assert result.params[-1] is values
    result = compose('SELECT * FROM (%(q)s) x WHERE %(v)s IS NULL', q=qs, v=None)
    assert result.sql.endswith('WHERE %s IS NULL')
    assert result.params == (None,)


def test_slot_named_template():
    qs = Thing.objects.filter(n__lte=6).values('id', 'n')
    sq, pq = sql_and_params(qs)
    result = compose('SELECT x.n FROM (%(template)s) x', template=qs)
    assert result == ('SELECT x.n FROM ({}) x'.format(sq), pq)
    result = compose('SELECT x.n FROM (%(é)s) x', **{'é': qs})
    assert result == ('SELECT x.n FROM ({}) x'.format(sq), pq)


IDENTIFIER_NAMES = [
    pytest.param('नाम', id='devanagari'),
    pytest.param('x́', id='combining_acute'),
    pytest.param('a·b', id='middle_dot'),
    pytest.param('a‿b', id='undertie'),
]


@pytest.mark.parametrize('name', IDENTIFIER_NAMES)
def test_slot_names_accept_every_identifier(name):
    assert name.isidentifier()
    qs = Thing.objects.filter(n__lte=6).values('id', 'n')
    sq, pq = sql_and_params(qs)
    result = compose('SELECT x.n FROM (%(' + name + ')s) x', **{name: qs})
    assert result == ('SELECT x.n FROM ({}) x'.format(sq), pq)
    result = compose('%(' + name + ')s UNION ALL %(' + name + ')s', **{name: qs})
    assert result == ('{} UNION ALL {}'.format(sq, sq), pq + pq)
    result = compose('SELECT %(' + name + ')s FROM (%(q)s) x', q=qs, **{name: 7})
    assert result == ('SELECT %s FROM ({}) x'.format(sq), (7,) + pq)


def test_slot_names_are_nfkc_normalized():
    qs = Thing.objects.filter(n__lte=6).values('id', 'n')
    sq, pq = sql_and_params(qs)
    expected = ('SELECT x.n FROM ({}) x'.format(sq), pq)
    # Python passes the keyword written with U+FB01 as 'fi'
    assert compose('SELECT x.n FROM (%(ﬁ)s) x', ﬁ=qs) == expected
    assert compose('SELECT x.n FROM (%(ﬁ)s) x', **{'ﬁ': qs}) == expected
    assert compose('SELECT x.n FROM (%(fi)s) x', **{'ﬁ': qs}) == expected
    with pytest.raises(ValueError) as excinfo:
        compose('%(fi)s', **{'fi': qs, 'ﬁ': qs})
    assert str(excinfo.value) == (
        "compose got keyword arguments that name the same slot after NFKC normalization: 'fi', 'ﬁ'"
    )
    with pytest.raises(ValueError) as excinfo:
        compose('%(q)s %(ﬁ)s', q=qs)
    assert str(excinfo.value) == "compose template names slots that were not passed: 'fi'"
    with pytest.raises(ValueError) as excinfo:
        compose('SELECT %(ﬁ)d', q=qs)
    assert str(excinfo.value) == PAREN.format(7)
    with pytest.raises(ValueError) as excinfo:
        compose('%(ﬁ)s %', **{'ﬁ': qs})
    assert str(excinfo.value) == POSITIONAL.format(6)


def test_compose_result_cannot_be_built_by_hand():
    qs = Thing.objects.values('id')
    message = 'ComposeResult is created by compose(); call compose() instead of building one'
    with pytest.raises(TypeError) as excinfo:
        ComposeResult('SELECT 1', (), 'default')
    assert str(excinfo.value) == message
    with pytest.raises(TypeError) as excinfo:
        ComposeResult(*sql_and_params(qs), qs.db)
    assert str(excinfo.value) == message


@pytest.mark.parametrize(
    'sql, params, alias, message',
    [
        pytest.param(b'SELECT 1', (), 'default', 'ComposeResult sql must be a str, got bytes', id='bytes_sql'),
        pytest.param('SELECT 1', None, 'default', 'ComposeResult params must be a tuple, got NoneType', id='none_params'),
        pytest.param('SELECT 1', [], 'default', 'ComposeResult params must be a tuple, got list', id='list_params'),
        pytest.param(
            'SELECT 1', Pair('a', ()), 'default', 'ComposeResult params must be a tuple, got Pair',
            id='namedtuple_params',
        ),
        pytest.param('SELECT 1', (), None, 'ComposeResult alias must be a str, got NoneType', id='none_alias'),
        pytest.param('SELECT 1', (), 5, 'ComposeResult alias must be a str, got int', id='int_alias'),
    ],
)
def test_make_result_validates_its_fields(sql, params, alias, message):
    with pytest.raises(TypeError) as excinfo:
        composition.make_result(sql, params, alias)
    assert str(excinfo.value) == message


def test_make_result_builds_a_result():
    result = composition.make_result('SELECT 1', (1,), 'default')
    assert isinstance(result, ComposeResult)
    assert result == ('SELECT 1', (1,))
    assert result.alias == 'default'


def test_double_percent_then_slot_parses():
    qs = Thing.objects.values('id')
    sq, pq = sql_and_params(qs)
    result = compose("SELECT '%%%(v)s' FROM (%(q)s) x", v=1, q=qs)
    assert result.sql == "SELECT '%%%s' FROM ({}) x".format(sq)
    assert result.params == (1,) + pq


def test_result_unpacks_as_str_and_tuple():
    result = compose('SELECT x.id FROM (%(q)s) x', q=Thing.objects.values('id'))
    sql, params = result
    assert type(sql) is str
    assert type(params) is tuple
    assert len(result) == 2
    assert result.sql is result[0]
    assert result.params is result[1]
    assert isinstance(result, ComposeResult)
    assert isinstance(result, tuple)
    assert params == ()


def test_alias_is_the_querysets_alias():
    result = compose('%(q)s', q=Thing.objects.all())
    assert result.alias == 'default' == Thing.objects.all().db
    q = Thing.objects.using(dbconfig.SQLITE_LIVE_ALIAS).all()
    result = compose('%(q)s', q=q)
    assert result.alias == dbconfig.SQLITE_LIVE_ALIAS
    assert result.sql == sql_and_params(q)[0]


def test_result_survives_copy_and_pickle():
    result = compose('SELECT x.n FROM (%(q)s) x WHERE x.n > %(v)s', q=Thing.objects.filter(n__lte=6), v=2)
    for clone in (copy.copy(result), copy.deepcopy(result), pickle.loads(pickle.dumps(result))):
        assert clone == result
        assert isinstance(clone, ComposeResult)
        assert clone.alias == result.alias


@pytest.mark.parametrize(
    'pair',
    [
        pytest.param(lambda: sql_and_params(Thing.objects.all()), id='pair'),
        pytest.param(lambda: ('SELECT 1', ()), id='plain'),
        pytest.param(lambda: Pair('SELECT 1', ()), id='namedtuple'),
    ],
)
def test_nested_result_is_accepted_but_plain_tuples_are_rejected(pair):
    qs = Thing.objects.values('id')
    inner = compose('SELECT x.id FROM (%(q)s) x', q=qs)
    nested = compose('%(p)s UNION ALL %(q)s', p=inner, q=qs)
    assert nested.params == inner.params + sql_and_params(qs)[1]
    with pytest.raises(TypeError) as excinfo:
        compose('%(p)s %(q)s', p=pair(), q=qs)
    assert str(excinfo.value) == TUPLE_MESSAGE


@pytest.mark.parametrize('case_id', list(REJECTED))
def test_rejects_non_value_types(case_id):
    factory, name = REJECTED[case_id]
    with pytest.raises(TypeError) as excinfo:
        compose('%(q)s %(x)s', q=Thing.objects.values('id'), x=factory())
    assert str(excinfo.value) == "compose slot 'x' cannot hold a {}".format(name)


@pytest.mark.parametrize('template, name', [(b'SELECT 1', 'bytes'), (None, 'NoneType'), (5, 'int')])
def test_rejects_non_str_template(template, name):
    with pytest.raises(TypeError) as excinfo:
        compose(template, q=Thing.objects.all())
    assert str(excinfo.value) == 'compose needs a str template, got {}'.format(name)


@pytest.mark.parametrize(
    'template, position',
    [
        ('SELECT %s FROM (%(q)s) x', 7),
        ('SELECT 50% FROM (%(q)s) x', 9),
        ('SELECT 1 FROM (%(q)s) x %', 24),
        ("SELECT '%%%' FROM (%(q)s) x", 10),
        ('%(q)s%', 5),
    ],
)
def test_rejects_positional_or_lone_percent(template, position):
    assert template[position] == '%'
    with pytest.raises(ValueError) as excinfo:
        compose(template, q=Thing.objects.all())
    assert str(excinfo.value) == POSITIONAL.format(position)


@pytest.mark.parametrize(
    'template, position',
    [
        pytest.param('SELECT %(n)d FROM (%(q)s) x', 7, id='d'),
        pytest.param('%(n)r FROM (%(q)s) x', 0, id='r'),
        pytest.param('%(n) FROM (%(q)s) x', 0, id='no_conversion'),
        pytest.param('%()s FROM (%(q)s) x', 0, id='empty'),
        pytest.param('%(1a)s FROM (%(q)s) x', 0, id='digit_start'),
        pytest.param('%(a b)s FROM (%(q)s) x', 0, id='space'),
        pytest.param('%(a-b)s FROM (%(q)s) x', 0, id='hyphen'),
        pytest.param('%(a%b)s FROM (%(q)s) x', 0, id='inner_percent'),
        pytest.param('SELECT %(n', 7, id='unclosed'),
    ],
)
def test_rejects_other_percent_paren_forms(template, position):
    assert template[position] == '%'
    with pytest.raises(ValueError) as excinfo:
        compose(template, q=Thing.objects.all())
    assert str(excinfo.value) == PAREN.format(position)


def test_missing_slot_is_named():
    qs = Thing.objects.all()
    with pytest.raises(ValueError) as excinfo:
        compose('SELECT * FROM (%(q)s) x JOIN (%(b)s) y ON 1=1', q=qs)
    assert str(excinfo.value) == "compose template names slots that were not passed: 'b'"
    with pytest.raises(ValueError) as excinfo:
        compose('%(q)s %(z)s %(b)s', q=qs)
    assert str(excinfo.value) == "compose template names slots that were not passed: 'z', 'b'"


def test_unused_keyword_is_named():
    with pytest.raises(ValueError) as excinfo:
        compose('%(q)s', q=Thing.objects.all(), extra=1, another=2)
    assert str(excinfo.value) == "compose got keyword arguments the template does not use: 'another', 'extra'"


def test_no_queryset_slot_raises_value_error():
    with pytest.raises(ValueError):
        compose('SELECT %(v)s', v=1)
    with pytest.raises(ValueError):
        compose('SELECT 1')


def test_mixed_aliases_are_named(monkeypatch):
    seen = spy_on_get_compiler(monkeypatch)
    default_qs = Thing.objects.all()
    live_qs = Thing.objects.using(dbconfig.SQLITE_LIVE_ALIAS).all()
    with pytest.raises(ValueError) as excinfo:
        compose('%(a)s UNION ALL %(b)s', a=default_qs, b=live_qs)
    assert str(excinfo.value) == (
        "compose slots must share one database alias, got 'default': a; 'sqlite_live': b"
    )
    assert seen == []
    monkeypatch.undo()
    nested = compose('%(q)s', q=live_qs)
    with pytest.raises(ValueError) as excinfo:
        compose('%(n)s UNION ALL %(d)s', n=nested, d=default_qs)
    assert "'default': d" in str(excinfo.value)
    assert "'sqlite_live': n" in str(excinfo.value)


def test_error_precedence():
    qs = Thing.objects.all()
    live_qs = Thing.objects.using(dbconfig.SQLITE_LIVE_ALIAS).all()
    with pytest.raises(TypeError, match='compose needs a str template'):
        compose(5, q=qs, extra=1)
    with pytest.raises(ValueError, match='positional %s or a lone %'):
        compose('%s %(b)s', q=qs)
    with pytest.raises(ValueError, match='not passed'):
        compose('%(q)s %(b)s', q=qs, extra=1)
    with pytest.raises(ValueError, match='does not use'):
        compose('%(q)s %(p)s', q=qs, p=Q(n=1), extra=1)
    with pytest.raises(TypeError, match='cannot hold a Q'):
        compose('%(a)s %(b)s %(x)s', a=qs, b=live_qs, x=Q(n=1))


def test_alias_read_once_under_a_flipping_router(monkeypatch):
    class FlippingRouter:
        def __init__(self):
            self.calls = 0

        def db_for_read(self, model, **hints):
            if model._meta.concrete_model is not Thing:
                return None
            self.calls += 1
            return dbconfig.SQLITE_LIVE_ALIAS if self.calls == 1 else 'default'

    seen = spy_on_get_compiler(monkeypatch)
    with override_settings(DATABASE_ROUTERS=[FlippingRouter()]):
        result = compose('%(q)s', q=Thing.objects.filter(n__lte=3))
    assert seen == [result.alias]


@pytest.mark.parametrize('scenario_id', compose_cases.SCENARIO_IDS)
def test_scenario_runs_on_sqlite(things_sqlite, scenario_id):
    compose_cases.check_scenario(things_sqlite, scenario_id)


def test_raw_returns_instances_on_sqlite(things_sqlite):
    compose_cases.check_raw(things_sqlite)


def test_mixed_default_and_sqlite_live_rows_alias_error(things_sqlite):
    inner = compose('%(q)s', q=Thing.objects.using(things_sqlite).all())
    assert inner.alias == things_sqlite
    with pytest.raises(ValueError) as excinfo:
        compose('%(a)s UNION ALL %(b)s', a=inner, b=Thing.objects.using('default').all())
    assert "'default'" in str(excinfo.value)
    assert "'sqlite_live'" in str(excinfo.value)
