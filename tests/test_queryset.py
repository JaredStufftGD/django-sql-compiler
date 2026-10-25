from types import SimpleNamespace

import django.db.models.sql.query
import pytest
from django.db import connections, models
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


@pytest.mark.xfail(strict=True, raises=AssertionError, reason='queryset.py formats the message with the None returned by validate_connection, so it always reads "None backend is not supported."')
def test_unsupported_backend_message_names_engine():
    engine = connections['default'].settings_dict['ENGINE']
    with pytest.raises(NotImplementedError) as excinfo:
        Widget.objects.all().executable_query
    assert engine in str(excinfo.value)


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
