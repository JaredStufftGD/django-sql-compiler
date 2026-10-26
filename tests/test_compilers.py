import subprocess
import sys
import types
from types import SimpleNamespace

import pytest
from django.db.utils import ProgrammingError

from sql_compiler import utils
from sql_compiler.compilers import compilers, compiler_map, SUPPORTED_BACKENDS, MySQLCompiler, PostgresCompiler, PostgresTenantsCompiler, Psycopg2Compiler
from sql_compiler.compilers.base import BaseSQLCompiler

EXPECTED_BACKENDS = {
    'django.db.backends.mysql',
    'django.db.backends.postgresql',
    'django.db.backends.postgresql_psycopg2',
    'django_tenants.postgresql_backend',
}


class StubConnection:
    encoding = 'utf8'

    def __init__(self):
        self.seen = []

    def literal(self, value):
        # Must return bytes, like the real MySQLdb connection
        self.seen.append(value)
        return '<{}>'.format(value).encode(self.encoding)


class StubCursor:
    def __init__(self):
        self.connection = StubConnection()


def test_registry_compiler_map_is_expected_set():
    assert set(compiler_map) == EXPECTED_BACKENDS


def test_registry_supported_backends_is_expected_set():
    assert set(SUPPORTED_BACKENDS) == EXPECTED_BACKENDS


def test_registry_no_duplicate_backend_names():
    names = [c.backend_name for c in compilers]
    assert len(set(names)) == len(names), 'duplicate backend_name in compilers: {}'.format(names)


def test_registry_maps_each_compiler_to_its_backend_name():
    for c in compilers:
        assert compiler_map[c.backend_name] is c


def test_registry_maps_every_postgres_engine():
    # postgresql_psycopg2 stays mapped even though Django 4.2+ can't load that backend
    assert compiler_map['django.db.backends.postgresql'] is PostgresCompiler
    assert compiler_map['django_tenants.postgresql_backend'] is PostgresTenantsCompiler
    assert compiler_map['django.db.backends.postgresql_psycopg2'] is Psycopg2Compiler


def test_mogrify_tuple():
    cursor = StubCursor()
    result = MySQLCompiler().mogrify(cursor, 'SELECT %s, %s', ('a', 1))
    assert result == b'SELECT <a>, <1>'
    assert cursor.connection.seen == ['a', 1]


def test_mogrify_dict():
    cursor = StubCursor()
    result = MySQLCompiler().mogrify(cursor, 'SELECT %(x)s', {'x': 'é'})
    assert result == 'SELECT <é>'.encode('utf8')
    assert cursor.connection.seen == ['é']


def test_mogrify_none_args():
    cursor = StubCursor()
    result = MySQLCompiler().mogrify(cursor, 'SELECT 100%', None)
    assert result == b'SELECT 100%'
    assert cursor.connection.seen == []


def test_mogrify_empty_tuple_unescapes_percent():
    # Django passes () when a query has no params, and its SQL can still contain %%
    cursor = StubCursor()
    result = MySQLCompiler().mogrify(cursor, "SELECT '100%%'", ())
    assert result == b"SELECT '100%'"
    assert cursor.connection.seen == []


def test_mogrify_tuple_unescapes_percent():
    cursor = StubCursor()
    result = MySQLCompiler().mogrify(cursor, "SELECT %s LIKE '%%'", ('a',))
    assert result == b"SELECT <a> LIKE '%'"


PG_ENCODINGS = {'WIN1252': 'cp1252', 'LATIN1': 'latin1', 'UTF8': 'utf_8'}


def raw_connection(encoding):
    return SimpleNamespace(connection=SimpleNamespace(encoding=encoding))


class FakeNotSupportedError(Exception):
    """Stands in for psycopg.NotSupportedError, a DB-API error and not a LookupError."""


# PostgreSQL client encodings with no Python codec, commented out of psycopg 3's _encodings.py table
NO_PYTHON_CODEC = {'EUC_TW', 'MULE_INTERNAL'}


class FakePsycopg3Info:
    """
    Like psycopg 3's ConnectionInfo: .encoding is a Python codec name, and for a client encoding Python has no
    codec for it raises NotSupportedError (pg2pyenc), so it never returns an unknown name.
    """

    def __init__(self, encoding):
        self.client_encoding = encoding

    @property
    def encoding(self):
        if self.client_encoding in NO_PYTHON_CODEC:
            raise FakeNotSupportedError('codec not available in Python: {!r}'.format(self.client_encoding))
        return self.client_encoding


class FakePsycopg3Connection:
    def __init__(self, encoding):
        self.info = FakePsycopg3Info(encoding)


class FakeClientCursor:
    built_on = []

    def __init__(self, connection):
        self.connection = connection
        FakeClientCursor.built_on.append(connection)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def mogrify(self, query, params):
        # Like psycopg 3's Transformer, mogrify reads the connection encoding, so EUC_TW raises here too
        self.connection.info.encoding
        return query % tuple("'{}'".format(p) for p in params)


class FakePsycopg2Connection:
    def __init__(self, encoding):
        self.encoding = encoding


@pytest.fixture
def fake_psycopg(monkeypatch):
    module = types.ModuleType('psycopg')
    module.Connection = FakePsycopg3Connection
    module.ClientCursor = FakeClientCursor
    module.NotSupportedError = FakeNotSupportedError
    FakeClientCursor.built_on = []
    monkeypatch.setitem(sys.modules, 'psycopg', module)
    return module


@pytest.fixture
def fake_psycopg2(monkeypatch):
    module = types.ModuleType('psycopg2.extensions')
    module.connection = FakePsycopg2Connection
    monkeypatch.setitem(sys.modules, 'psycopg2.extensions', module)
    monkeypatch.setattr(PostgresCompiler, 'encoding_map', lambda self: PG_ENCODINGS)
    return module


class FakeDjangoConnection:
    """Stands in for Django's DatabaseWrapper: .connection is the raw driver connection."""

    def __init__(self, raw, cursor_mogrify=None, ensure_connection=None):
        self.connection = raw
        self.cursor_mogrify = cursor_mogrify
        self.ensure_connection_to = ensure_connection

    def ensure_connection(self):
        self.connection = self.ensure_connection_to

    def cursor(self):
        outer = self

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def mogrify(self, query, params):
                if outer.cursor_mogrify is None:
                    raise AssertionError('psycopg 3 must not use the Django cursor mogrify')
                return outer.cursor_mogrify(query, params)

        return Cursor()


def test_postgres_psycopg3_compile_sql_returns_bytes_in_connection_encoding(fake_psycopg):
    raw = FakePsycopg3Connection('cp1252')
    compiled = PostgresCompiler().compile_sql(FakeDjangoConnection(raw), 'SELECT %s', ('café €',))
    assert compiled == b"SELECT 'caf\xe9 \x80'"
    assert FakeClientCursor.built_on == [raw]


def test_postgres_psycopg3_compile_sql_does_not_use_the_django_cursor_mogrify(fake_psycopg):
    connection = FakeDjangoConnection(FakePsycopg3Connection('utf-8'))
    assert PostgresCompiler().compile_sql(connection, 'SELECT %s', ('a',)) == b"SELECT 'a'"


@pytest.mark.parametrize('encoding', ['utf-8', 'cp1252'])
def test_postgres_and_tenants_compilers_give_the_same_psycopg3_output(fake_psycopg, encoding):
    raw = FakePsycopg3Connection(encoding)
    connection = FakeDjangoConnection(raw)
    postgres = PostgresCompiler().compile_sql(connection, 'SELECT %s', ('café',))
    tenants = PostgresTenantsCompiler().compile_sql(connection, 'SELECT %s', ('café',))
    assert postgres == tenants == "SELECT 'café'".encode(encoding)
    assert PostgresCompiler().python_encoding(connection) == PostgresTenantsCompiler().python_encoding(connection)


def test_postgres_psycopg2_compile_sql_uses_the_django_cursor_mogrify(fake_psycopg2):
    connection = FakeDjangoConnection(
        FakePsycopg2Connection('UTF8'),
        cursor_mogrify=lambda query, params: b'mogrified:' + query.encode(),
    )
    assert PostgresCompiler().compile_sql(connection, 'SELECT 1', ()) == b'mogrified:SELECT 1'


def test_postgres_python_encoding_win1252_decodes_euro(fake_psycopg2):
    encoding = PostgresCompiler().python_encoding(FakeDjangoConnection(FakePsycopg2Connection('WIN1252')))
    assert utils.bytes_to_string(b"SELECT 'caf\xe9 \x80'", encoding) == "SELECT 'café €'"


def test_postgres_python_encoding_latin1_decodes_cafe(fake_psycopg2):
    encoding = PostgresCompiler().python_encoding(FakeDjangoConnection(FakePsycopg2Connection('LATIN1')))
    assert utils.bytes_to_string(b"SELECT 'caf\xe9'", encoding) == "SELECT 'café'"


def test_postgres_python_encoding_unknown_name_raises_lookup_error(fake_psycopg2):
    with pytest.raises(LookupError):
        PostgresCompiler().python_encoding(FakeDjangoConnection(FakePsycopg2Connection('NOT_A_PG_ENCODING')))


def no_psycopg2_map(self):
    raise AssertionError('psycopg 3 connections must not use the psycopg2 encoding map')


def test_postgres_python_encoding_psycopg3_utf8(monkeypatch, fake_psycopg):
    monkeypatch.setattr(PostgresCompiler, 'encoding_map', no_psycopg2_map)
    assert PostgresCompiler().python_encoding(FakeDjangoConnection(FakePsycopg3Connection('utf-8'))) == 'utf-8'


def test_postgres_python_encoding_psycopg3_cp1252_decodes_euro(monkeypatch, fake_psycopg):
    monkeypatch.setattr(PostgresCompiler, 'encoding_map', no_psycopg2_map)
    encoding = PostgresCompiler().python_encoding(FakeDjangoConnection(FakePsycopg3Connection('cp1252')))
    assert utils.bytes_to_string(b"SELECT 'caf\xe9 \x80'", encoding) == "SELECT 'café €'"


@pytest.mark.parametrize('client_encoding', sorted(NO_PYTHON_CODEC))
def test_postgres_python_encoding_psycopg3_no_python_codec_raises_lookup_error(
        monkeypatch, fake_psycopg, client_encoding):
    monkeypatch.setattr(PostgresCompiler, 'encoding_map', no_psycopg2_map)
    connection = FakeDjangoConnection(FakePsycopg3Connection(client_encoding))
    with pytest.raises(LookupError) as excinfo:
        PostgresCompiler().python_encoding(connection)
    assert client_encoding in str(excinfo.value)
    assert excinfo.value.__suppress_context__


@pytest.mark.parametrize('client_encoding', sorted(NO_PYTHON_CODEC))
def test_postgres_psycopg3_compile_sql_no_python_codec_raises_lookup_error(fake_psycopg, client_encoding):
    # compile_sql runs before python_encoding in executable_query, so it must raise LookupError too
    connection = FakeDjangoConnection(FakePsycopg3Connection(client_encoding))
    with pytest.raises(LookupError) as excinfo:
        PostgresCompiler().compile_sql(connection, 'SELECT %s', ('a',))
    assert client_encoding in str(excinfo.value)
    assert FakeClientCursor.built_on == []


def test_postgres_python_encoding_unknown_name_has_no_chained_key_error(fake_psycopg2):
    with pytest.raises(LookupError) as excinfo:
        PostgresCompiler().python_encoding(FakeDjangoConnection(FakePsycopg2Connection('NOT_A_PG_ENCODING')))
    assert excinfo.value.__suppress_context__


LOOKALIKES = [
    lambda: SimpleNamespace(info=SimpleNamespace(encoding='utf-8')),
    lambda: SimpleNamespace(encoding='UTF8'),
    lambda: object(),
]


@pytest.mark.parametrize('drivers_installed', [True, False])
@pytest.mark.parametrize('make_raw', LOOKALIKES, ids=['info_encoding', 'encoding', 'object'])
def test_postgres_lookalike_connection_is_unsupported(monkeypatch, make_raw, drivers_installed):
    if drivers_installed:
        psycopg = types.ModuleType('psycopg')
        psycopg.Connection = FakePsycopg3Connection
        extensions = types.ModuleType('psycopg2.extensions')
        extensions.connection = FakePsycopg2Connection
        monkeypatch.setitem(sys.modules, 'psycopg', psycopg)
        monkeypatch.setitem(sys.modules, 'psycopg2.extensions', extensions)
    else:
        # None, not a deleted key: an accidental import raises ImportError instead of half-reloading a real driver
        monkeypatch.setitem(sys.modules, 'psycopg', None)
        monkeypatch.setitem(sys.modules, 'psycopg2.extensions', None)
    raw = make_raw()
    connection = FakeDjangoConnection(raw, cursor_mogrify=lambda query, params: b'would succeed')
    with pytest.raises(NotImplementedError) as compile_error:
        PostgresCompiler().compile_sql(connection, 'SELECT 1', ())
    with pytest.raises(NotImplementedError) as encoding_error:
        PostgresCompiler().python_encoding(connection)
    assert type(raw).__qualname__ in str(compile_error.value)
    assert type(raw).__qualname__ in str(encoding_error.value)


def test_postgres_unsupported_message_never_names_nonetype():
    lookalike = SimpleNamespace(info=SimpleNamespace(encoding='utf-8'))
    connection = FakeDjangoConnection(None, ensure_connection=lookalike)
    with pytest.raises(NotImplementedError) as excinfo:
        PostgresCompiler().python_encoding(connection)
    assert 'SimpleNamespace' in str(excinfo.value)
    assert 'NoneType' not in str(excinfo.value)


def test_postgres_python_encoding_ensures_the_connection(fake_psycopg):
    connection = FakeDjangoConnection(None, ensure_connection=FakePsycopg3Connection('utf-8'))
    assert PostgresCompiler().python_encoding(connection) == 'utf-8'


def test_postgres_subclasses_share_python_encoding():
    assert PostgresTenantsCompiler.python_encoding is PostgresCompiler.python_encoding
    assert Psycopg2Compiler.python_encoding is PostgresCompiler.python_encoding


def test_mysql_python_encoding_reports_driver_codec():
    assert MySQLCompiler().python_encoding(raw_connection('cp1252')) == 'cp1252'
    assert MySQLCompiler().python_encoding(raw_connection('utf8')) == 'utf-8'


def test_mysql_python_encoding_unknown_charset_raises_lookup_error():
    with pytest.raises(LookupError):
        MySQLCompiler().python_encoding(raw_connection('binary'))


def test_base_python_encoding_not_implemented():
    with pytest.raises(NotImplementedError):
        BaseSQLCompiler().python_encoding(object())


def test_importing_package_does_not_import_db_drivers():
    # Fresh interpreter, so the result does not depend on what other tests imported
    code = (
        'import sys; import sql_compiler; '
        'sys.exit(1 if {"MySQLdb", "psycopg", "psycopg2"} & set(sys.modules) else 0)'
    )
    assert subprocess.run([sys.executable, '-c', code]).returncode == 0


def test_mogrify_param_mismatch_raises_programming_error():
    with pytest.raises(ProgrammingError):
        MySQLCompiler().mogrify(StubCursor(), 'SELECT %s, %s', ('a',))


@pytest.mark.parametrize('query, args, cause_type', [
    ('SELECT %s, %s', ('a',), TypeError),
    ('SELECT %s', ('a', 'b'), TypeError),
    ('SELECT %(x)s', ('a',), TypeError),
    ('SELECT %s', {'x': 1}, TypeError),
    ('SELECT %s %(x)s', {'x': 1}, TypeError),
    ('SELECT %(missing_key)s', {'other': 1}, KeyError),
    ('SELECT 100%', (), ValueError),
    ("SELECT 'a%z'", ('a',), ValueError),
    ('SELECT %(x', {'x': 1}, ValueError),
], ids=[
    'too_few',
    'too_many',
    'named_placeholder_sequence_params',
    'positional_placeholder_dict_params',
    'mixed_placeholders_dict_params',
    'missing_key',
    'stray_percent',
    'unsupported_format_char',
    'unterminated_key',
])
def test_mogrify_formatting_failure_raises_programming_error(query, args, cause_type):
    with pytest.raises(ProgrammingError) as excinfo:
        MySQLCompiler().mogrify(StubCursor(), query, args)
    assert isinstance(excinfo.value.__cause__, cause_type)
    assert str(excinfo.value.__cause__) in str(excinfo.value)


def test_mogrify_missing_key_message_names_the_key():
    with pytest.raises(ProgrammingError) as excinfo:
        MySQLCompiler().mogrify(StubCursor(), 'SELECT %(missing_key)s', {'other': 1})
    assert 'missing_key' in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, KeyError)
