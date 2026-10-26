from types import SimpleNamespace

import django.db.models.sql.query
import pytest
from django.conf import settings
from django.core.exceptions import EmptyResultSet
from django.db import connections, models
from django.db.models import Count, Exists, Q, Subquery, Window
from django.db.models.functions import RowNumber
from django.db.utils import ConnectionHandler
from django.test import override_settings

import sql_compiler.compilers
import sql_compiler.queryset
import sql_compiler.utils
from sql_compiler import SQLCompilerManager
from sql_compiler.compilers import MySQLCompiler


class Widget(models.Model):
    name = models.CharField(max_length=10)

    objects = SQLCompilerManager()

    class Meta:
        app_label = 'tests'


def test_unsupported_backend_raises_without_connecting():
    with pytest.raises(NotImplementedError):
        Widget.objects.all().executable_query
    assert connections['default'].connection is None


def test_unsupported_backend_message_names_engine():
    engine = connections['default'].settings_dict['ENGINE']
    with pytest.raises(NotImplementedError) as excinfo:
        Widget.objects.all().executable_query
    assert str(excinfo.value) == '{} backend is not supported.'.format(engine)


def stub_executable_query(monkeypatch, compiled, encoding='utf8', has_connection=True):
    class StubCompiler(MySQLCompiler):
        def compile_sql(self, connection, query, params):
            return compiled

    stub = SimpleNamespace(settings_dict={'ENGINE': MySQLCompiler.backend_name})
    if has_connection:
        stub.connection = SimpleNamespace(encoding=encoding)
    monkeypatch.setitem(sql_compiler.compilers.compiler_map, MySQLCompiler.backend_name, StubCompiler)
    monkeypatch.setattr(sql_compiler.utils, 'validate_connection', lambda connection: stub)
    seen = []

    def get_compiler(self, using=None, connection=None, elide_empty=True):
        seen.append(using)
        return SimpleNamespace(as_sql=lambda: ('SELECT %s', ('x',)))

    monkeypatch.setattr(django.db.models.sql.query.Query, 'get_compiler', get_compiler)
    return stub, seen


def test_executable_query_decodes_with_connection_encoding(monkeypatch):
    stub_executable_query(monkeypatch, "SELECT 'café €'".encode('cp1252'), 'cp1252')
    assert Widget.objects.all().executable_query == "SELECT 'café €'"


def test_executable_query_unknown_encoding_raises_lookup_error(monkeypatch):
    stub_executable_query(monkeypatch, b'SELECT 1', 'binary')
    with pytest.raises(LookupError):
        Widget.objects.all().executable_query


def test_executable_query_invalid_bytes_raise_unicode_decode_error(monkeypatch):
    stub_executable_query(monkeypatch, b"SELECT '\xff\xfe'", 'utf8')
    with pytest.raises(UnicodeDecodeError):
        Widget.objects.all().executable_query


def test_executable_query_rejects_non_bytes_before_encoding_lookup(monkeypatch):
    stub_executable_query(monkeypatch, 'SELECT 1', has_connection=False)
    with pytest.raises(TypeError):
        Widget.objects.all().executable_query


class ReadRouter:
    def db_for_read(self, model, **hints):
        return 'other'


def test_executable_query_compiles_for_the_querysets_alias(monkeypatch):
    stub, seen = stub_executable_query(monkeypatch, b'SELECT 1')
    monkeypatch.setattr(sql_compiler.queryset, 'connections', {'other': stub})
    Widget.objects.using('other').executable_query
    assert seen == ['other']


def test_executable_query_compiles_for_the_router_alias(monkeypatch):
    stub, seen = stub_executable_query(monkeypatch, b'SELECT 1')
    monkeypatch.setattr(sql_compiler.queryset, 'connections', {'other': stub})
    with override_settings(DATABASE_ROUTERS=[ReadRouter()]):
        Widget.objects.all().executable_query
    assert seen == ['other']


UNSUPPORTED_OTHER_ENGINE = 'django.db.backends.dummy'


@pytest.fixture
def unsupported_other(monkeypatch):
    handler = ConnectionHandler({
        'default': settings.DATABASES['default'],
        'other': {'ENGINE': UNSUPPORTED_OTHER_ENGINE},
    })
    monkeypatch.setattr(sql_compiler.queryset, 'connections', handler)
    yield handler
    handler.close_all()


def assert_names_other_engine(handler, excinfo):
    engine = handler['other'].settings_dict['ENGINE']
    default_engine = handler['default'].settings_dict['ENGINE']
    assert str(excinfo.value) == '{} backend is not supported.'.format(engine)
    assert default_engine not in str(excinfo.value)
    assert handler['other'].connection is None
    assert handler['default'].connection is None


def test_unsupported_backend_message_names_the_using_alias_engine(unsupported_other):
    with pytest.raises(NotImplementedError) as excinfo:
        Widget.objects.using('other').executable_query
    assert_names_other_engine(unsupported_other, excinfo)


def test_unsupported_backend_message_names_the_router_alias_engine(unsupported_other):
    with override_settings(DATABASE_ROUTERS=[ReadRouter()]):
        with pytest.raises(NotImplementedError) as excinfo:
            Widget.objects.all().executable_query
    assert_names_other_engine(unsupported_other, excinfo)


EMPTY_SHAPES = [
    ('none', lambda: Widget.objects.none(), lambda: Widget.objects.all()),
    ('in_empty', lambda: Widget.objects.filter(id__in=[]), lambda: Widget.objects.all()),
    ('values', lambda: Widget.objects.filter(id__in=[]).values('name'), lambda: Widget.objects.values('name')),
    ('values_list', lambda: Widget.objects.filter(id__in=[]).values_list('pk', 'name'), lambda: Widget.objects.values_list('pk', 'name')),
    ('union_all_empty', lambda: Widget.objects.filter(id__in=[]).union(Widget.objects.filter(name__in=[])), lambda: Widget.objects.all().union(Widget.objects.all())),
    ('subquery_none', lambda: Widget.objects.filter(pk__in=Widget.objects.none()), lambda: Widget.objects.filter(pk__in=Widget.objects.all())),
    ('empty_having', lambda: Widget.objects.annotate(c=Count('id')).filter(c__in=[]), lambda: Widget.objects.annotate(c=Count('id'))),
    ('order_by_empty_subquery', lambda: Widget.objects.order_by(Subquery(Widget.objects.none().values('name')[:1])), lambda: Widget.objects.all()),
]
EMPTY_SHAPE_IDS = [shape[0] for shape in EMPTY_SHAPES]
# union columns are compared on live DBs in tests/db/test_empty.py
SELECT_LIST_SHAPE_IDS = [shape_id for shape_id in EMPTY_SHAPE_IDS if shape_id != 'union_all_empty']

# Shapes whose compilation differs between Django lines (sliced unions and elide_empty, combinator
# parts, QUALIFY); only checked for not letting EmptyResultSet escape.
CROSS_VERSION_SHAPES = [
    ('union_all_empty_sliced', lambda: Widget.objects.filter(id__in=[]).union(Widget.objects.filter(id__in=[]))[:5]),
    ('union_all_empty_ordered_sliced', lambda: Widget.objects.filter(id__in=[]).union(Widget.objects.filter(id__in=[])).order_by('name')[:3]),
    ('intersection_empty_part', lambda: Widget.objects.all().intersection(Widget.objects.filter(id__in=[]))),
    ('difference_empty_first', lambda: Widget.objects.filter(id__in=[]).difference(Widget.objects.all())),
    ('window_qualify_empty', lambda: Widget.objects.annotate(rn=Window(RowNumber())).filter(rn__in=[])),
    ('window_qualify_and_empty_where', lambda: Widget.objects.annotate(rn=Window(RowNumber())).filter(rn=1, id__in=[])),
    ('empty_sliced', lambda: Widget.objects.filter(id__in=[])[:5]),
    ('empty_offset', lambda: Widget.objects.filter(id__in=[])[2:5]),
    ('zero_slice', lambda: Widget.objects.all()[0:0]),
    ('distinct', lambda: Widget.objects.filter(id__in=[]).distinct()),
    ('extra', lambda: Widget.objects.filter(id__in=[]).extra(select={'x': '%s'}, select_params=("o'k",), where=['name = %s'], params=['a'])),
]
COMPILE_SHAPES = [shape[:2] for shape in EMPTY_SHAPES] + CROSS_VERSION_SHAPES


def empty_shape(shape_id):
    return next(shape for shape in EMPTY_SHAPES if shape[0] == shape_id)


@pytest.mark.parametrize('shape_id', [shape[0] for shape in COMPILE_SHAPES])
def test_empty_shapes_compile_without_empty_result_set(shape_id):
    qs = dict(COMPILE_SHAPES)[shape_id]()
    with pytest.raises(EmptyResultSet):
        qs.query.get_compiler(using='default').as_sql()
    sql, params = sql_compiler.utils.query_sql_and_params(qs.query, 'default')
    assert '0 = 1' in sql
    assert connections['default'].connection is None
    with pytest.raises(EmptyResultSet):
        qs.query.get_compiler(using='default').as_sql()


def group_by_clause(sql):
    if ' GROUP BY ' not in sql:
        return None
    return sql.split(' GROUP BY ', 1)[1].split(' HAVING ')[0].split(' ORDER BY ')[0]


@pytest.mark.parametrize('shape_id', SELECT_LIST_SHAPE_IDS)
def test_empty_shapes_keep_the_counterpart_select_list(shape_id):
    _, empty_factory, counterpart_factory = empty_shape(shape_id)
    sql, params = sql_compiler.utils.query_sql_and_params(empty_factory().query, 'default')
    counterpart_sql = counterpart_factory().query.get_compiler(using='default').as_sql()[0]
    assert sql.split(' FROM ')[0] == counterpart_sql.split(' FROM ')[0]
    # GROUP BY is what keeps an aggregate query (empty_having) at zero rows
    assert group_by_clause(sql) == group_by_clause(counterpart_sql)


@pytest.mark.parametrize('factory', [
    pytest.param(lambda: Widget.objects.order_by(Subquery(Widget.objects.none().values('name')[:1])), id='subquery'),
    pytest.param(lambda: Widget.objects.order_by(Exists(Widget.objects.none())), id='exists'),
])
def test_ordering_by_an_empty_subquery_compiles(factory):
    # Ordering by Exists(<empty>) raises EmptyResultSet only on Django 4.2; later lines compile it as is,
    # so it must then stay byte-identical.
    q = factory().query
    try:
        unchanged = q.get_compiler(using='default').as_sql()
    except EmptyResultSet:
        unchanged = None
    sql, params = sql_compiler.utils.query_sql_and_params(q, 'default')
    if unchanged is None:
        assert '0 = 1' in sql
        assert 'ORDER BY' not in sql
    else:
        assert (sql, params) == unchanged


@pytest.mark.parametrize('factory', [
    pytest.param(lambda: Widget.objects.filter(name='a'), id='plain'),
    pytest.param(lambda: Widget.objects.filter(id__in=[]).union(Widget.objects.filter(name='a')), id='union_one_empty'),
    pytest.param(lambda: Widget.objects.filter(id__in=[]).union(Widget.objects.filter(name='a'))[:5], id='union_one_empty_sliced'),
    pytest.param(lambda: Widget.objects.filter(Q(pk__in=Widget.objects.none()) | Q(name='a')), id='or_empty_subquery'),
])
def test_working_querysets_compile_byte_identically(factory):
    q = factory().query
    assert sql_compiler.utils.query_sql_and_params(q, 'default') == q.get_compiler(using='default').as_sql()


def test_executable_query_retries_empty_queryset_on_its_alias(monkeypatch):
    stub, _ = stub_executable_query(monkeypatch, b'SELECT 1')
    monkeypatch.setattr(sql_compiler.queryset, 'connections', {'other': stub})
    calls = []

    def get_compiler(self, using=None, connection=None, elide_empty=True):
        calls.append((using, elide_empty))

        def as_sql():
            if elide_empty:
                raise EmptyResultSet()
            return ('SELECT 1 WHERE 0 = 1', ())

        return SimpleNamespace(as_sql=as_sql)

    monkeypatch.setattr(django.db.models.sql.query.Query, 'get_compiler', get_compiler)
    assert Widget.objects.using('other').none().executable_query == 'SELECT 1'
    assert calls == [('other', True), ('other', False)]
