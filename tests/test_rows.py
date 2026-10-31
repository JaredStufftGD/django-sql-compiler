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
