import subprocess
import sys

import pytest
from django.db.utils import ProgrammingError

from sql_compiler.compilers import compilers, compiler_map, SUPPORTED_BACKENDS, MySQLCompiler

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


def test_importing_package_does_not_import_db_drivers():
    # Fresh interpreter, so the result does not depend on what other tests imported
    code = (
        'import sys; import sql_compiler; '
        'sys.exit(1 if {"MySQLdb", "psycopg", "psycopg2"} & set(sys.modules) else 0)'
    )
    assert subprocess.run([sys.executable, '-c', code]).returncode == 0


@pytest.mark.xfail(strict=True, raises=NameError, reason='mysql.py raises ProgrammingError without importing it, so a param-count mismatch raises NameError')
def test_mogrify_param_mismatch_raises_programming_error():
    with pytest.raises(ProgrammingError):
        MySQLCompiler().mogrify(StubCursor(), 'SELECT %s, %s', ('a',))
