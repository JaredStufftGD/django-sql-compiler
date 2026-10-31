import collections
import dataclasses
import inspect
import typing

import pytest
from django.db import connections
from django.db.backends.base.base import BaseDatabaseWrapper

import sql_compiler
from sql_compiler import compose, fetch_rows, sql_and_params

from tests import dbconfig
from tests.db import rows_cases
from tests.db.models import Thing

RESULT_MESSAGE = 'fetch_rows needs a ComposeResult from compose(), got {}'
ROW_MESSAGE = 'fetch_rows row must be dict or a dataclass type, got {}'
NO_RESULT_SET = 'fetch_rows: the statement returned no result set; it has already run'
NO_COLUMNS = 'fetch_rows: the result has no columns'

Pair = collections.namedtuple('Pair', ['sql', 'params'])


@dataclasses.dataclass
class Point:
    x: int


class PointTuple(typing.NamedTuple):
    x: int


class Plain:
    pass


@dataclasses.dataclass
class Mixed:
    a: int
    b: dataclasses.InitVar[int]
    c: int = dataclasses.field(default=0)
    d: int = dataclasses.field(init=False, default=0)
    e: typing.ClassVar[int] = 1
    f: dataclasses.InitVar[int] = 2


@dataclasses.dataclass
class QuotedMixed:
    a: 'int'
    b: 'dataclasses.InitVar[int]'
    c: 'int' = dataclasses.field(default=0)
    d: 'int' = dataclasses.field(init=False, default=0)
    e: 'typing.ClassVar[int]' = 1
    f: 'dataclasses.InitVar[int]' = 2
    g: 'Unresolvable' = None

    def __post_init__(self, b, f):
        self.b_seen = b


class RowBuildError(Exception):
    pass


@dataclasses.dataclass
class Exploding:
    x: int

    def __post_init__(self):
        raise RowBuildError('boom')


@dataclasses.dataclass(init=False)
class NoInit:
    x: int


@dataclasses.dataclass(init=False)
class KeywordInit:
    x: int

    def __init__(self, *, x):
        self.x = x * 10


def describe(*names):
    return tuple((name, None, None, None, None, None, None) for name in names)


@pytest.fixture(autouse=True)
def default_never_connects():
    yield
    if dbconfig.STATE['default'] == 'sqlite':
        assert connections['default'].connection is None


def spy_on_cursor(monkeypatch):
    seen = []

    def spy(self, *args, **kwargs):
        seen.append(self.alias)
        raise AssertionError('cursor opened')

    monkeypatch.setattr(BaseDatabaseWrapper, 'cursor', spy)
    return seen


class FakeCursor:

    def __init__(self, description, rows=()):
        self.description = description
        self.rows = rows
        self.executed = []
        self.fetched = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, sql, params):
        self.executed.append((sql, params))

    def fetchall(self):
        self.fetched.append(True)
        return list(self.rows)


def install_fake(monkeypatch, alias, fake):
    monkeypatch.setattr(connections[alias], 'cursor', lambda: fake)


def make_result():
    return compose(
        'SELECT x.id AS x FROM (%(q)s) x',
        q=Thing.objects.using(dbconfig.SQLITE_LIVE_ALIAS).all(),
    )


def test_fetch_rows_is_exported():
    assert 'fetch_rows' in sql_compiler.__all__
    assert sql_compiler.fetch_rows is sql_compiler.rows.fetch_rows
    assert inspect.ismodule(sql_compiler.rows)


NOT_RESULTS = {
    'tuple': (lambda: sql_and_params(Thing.objects.using(dbconfig.SQLITE_LIVE_ALIAS).all()), 'tuple'),
    'namedtuple': (
        lambda: Pair(*sql_and_params(Thing.objects.using(dbconfig.SQLITE_LIVE_ALIAS).all())),
        'Pair',
    ),
    'queryset': (lambda: Thing.objects.using(dbconfig.SQLITE_LIVE_ALIAS).all(), 'SQLCompilerQuerySet'),
    'str': (lambda: 'SELECT 1', 'str'),
}


@pytest.mark.parametrize('name', list(NOT_RESULTS))
def test_non_compose_result_raises_without_sql(monkeypatch, name):
    build, type_name = NOT_RESULTS[name]
    value = build()
    seen = spy_on_cursor(monkeypatch)
    with pytest.raises(TypeError) as excinfo:
        fetch_rows(value, dict)
    assert str(excinfo.value) == RESULT_MESSAGE.format(type_name)
    assert seen == []


BAD_ROWS = {
    'dataclass_instance': (lambda: Point(1), 'Point instance'),
    'namedtuple_class': (lambda: PointTuple, 'PointTuple'),
    'plain_class': (lambda: Plain, 'Plain'),
    'ordered_dict': (lambda: collections.OrderedDict, 'OrderedDict'),
    'dict_instance': (lambda: {}, 'dict instance'),
    'none': (lambda: None, 'NoneType instance'),
}


@pytest.mark.parametrize('name', list(BAD_ROWS))
def test_invalid_row_kind_raises_without_sql(monkeypatch, name):
    build, kind_name = BAD_ROWS[name]
    result = make_result()
    row = build()
    seen = spy_on_cursor(monkeypatch)
    with pytest.raises(TypeError) as excinfo:
        fetch_rows(result, row)
    assert str(excinfo.value) == ROW_MESSAGE.format(kind_name)
    assert seen == []


@pytest.mark.parametrize('row', [dict, Point], ids=['dict', 'dataclass'])
def test_no_result_set_from_fake_cursor(monkeypatch, row):
    result = make_result()
    fake = FakeCursor(None)
    install_fake(monkeypatch, result.alias, fake)
    with pytest.raises(ValueError) as excinfo:
        fetch_rows(result, row)
    assert str(excinfo.value) == NO_RESULT_SET
    assert fake.executed == [(result.sql, result.params)]
    assert fake.fetched == []


@pytest.mark.parametrize('description', [(), []], ids=['tuple', 'list'])
@pytest.mark.parametrize('row', [dict, Point], ids=['dict', 'dataclass'])
def test_no_columns_from_fake_cursor(monkeypatch, row, description):
    result = make_result()
    fake = FakeCursor(description)
    install_fake(monkeypatch, result.alias, fake)
    with pytest.raises(ValueError) as excinfo:
        fetch_rows(result, row)
    assert str(excinfo.value) == NO_COLUMNS
    assert fake.executed == [(result.sql, result.params)]
    assert fake.fetched == []


def test_fake_cursor_rows_are_built_from_description(monkeypatch):
    result = make_result()
    fake = FakeCursor((('x', None, None, None, None, None, None),), [(1,), (2,)])
    install_fake(monkeypatch, result.alias, fake)
    as_dicts = fetch_rows(result, dict)
    as_points = fetch_rows(result, Point)
    assert as_dicts == [{'x': 1}, {'x': 2}]
    assert as_points == [Point(1), Point(2)]
    assert type(as_dicts) is list
    assert type(as_points) is list
    for sql, params in fake.executed:
        assert sql == result.sql
        assert params == ()
        assert type(params) is tuple


@pytest.mark.parametrize('check_id', rows_cases.CHECK_IDS)
def test_check_runs_on_sqlite(things_sqlite, check_id):
    rows_cases.run_check(things_sqlite, check_id)


def test_private_dataclasses_names_still_exist():
    message = 'dataclasses private names changed; update sql_compiler.rows.constructor_fields'
    assert hasattr(dataclasses, '_FIELD_CLASSVAR'), message
    for cls in (Mixed, QuotedMixed):
        for field in cls.__dataclass_fields__.values():
            assert hasattr(field, '_field_type'), message


@pytest.mark.parametrize('cls', [Mixed, QuotedMixed], ids=['eager', 'quoted'])
def test_dataclasses_classvar_classification(cls):
    classvars = {
        name for name, field in cls.__dataclass_fields__.items()
        if field._field_type is dataclasses._FIELD_CLASSVAR
    }
    assert classvars == {'e'}


@pytest.mark.parametrize(
    'cls, expected',
    [
        (Mixed, {'a': False, 'b': False, 'c': True, 'f': True}),
        (QuotedMixed, {'a': False, 'b': False, 'c': True, 'f': True, 'g': True}),
    ],
    ids=['eager', 'quoted'],
)
def test_constructor_fields_counts_initvar_and_skips_init_false_and_classvar(cls, expected):
    assert sql_compiler.rows.constructor_fields(cls) == expected


def test_quoted_annotations_build_rows_and_report_classvar_column(monkeypatch):
    result = make_result()
    fake = FakeCursor(describe('a', 'b'), [(1, 5)])
    install_fake(monkeypatch, result.alias, fake)
    rows = fetch_rows(result, QuotedMixed)
    assert len(rows) == 1
    assert rows[0].a == 1
    assert rows[0].c == 0
    assert rows[0].b_seen == 5

    fake = FakeCursor(describe('a', 'b', 'e'), [(1, 5, 7)])
    install_fake(monkeypatch, result.alias, fake)
    with pytest.raises(ValueError) as excinfo:
        fetch_rows(result, QuotedMixed)
    assert "'e'" in str(excinfo.value)
    assert 'columns with no field' in str(excinfo.value)
    assert fake.fetched == []


def test_post_init_exception_propagates_after_statement_ran(monkeypatch):
    result = make_result()
    fake = FakeCursor(describe('x'), [(1,)])
    install_fake(monkeypatch, result.alias, fake)
    with pytest.raises(RowBuildError) as excinfo:
        fetch_rows(result, Exploding)
    assert excinfo.type is RowBuildError
    assert str(excinfo.value) == 'boom'
    assert fake.executed == [(result.sql, result.params)]
    assert fake.fetched == [True]


def test_init_false_without_init_raises_type_error_after_statement_ran(monkeypatch):
    result = make_result()
    fake = FakeCursor(describe('x'), [(1,)])
    install_fake(monkeypatch, result.alias, fake)
    with pytest.raises(TypeError) as excinfo:
        fetch_rows(result, NoInit)
    assert excinfo.type is TypeError
    assert fake.executed == [(result.sql, result.params)]
    assert fake.fetched == [True]


def test_init_false_with_custom_init_is_called_by_keyword(monkeypatch):
    result = make_result()
    fake = FakeCursor(describe('x'), [(2,)])
    install_fake(monkeypatch, result.alias, fake)
    rows = fetch_rows(result, KeywordInit)
    assert len(rows) == 1
    assert type(rows[0]) is KeywordInit
    assert rows[0].x == 20
