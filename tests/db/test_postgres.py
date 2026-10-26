import pytest

from sql_compiler import utils
from sql_compiler.compilers import PostgresCompiler

from .cases import CASE_IDS, run_case
from .expected import pinned_sql
from .models import Thing


@pytest.mark.parametrize('case_id', CASE_IDS)
def test_postgres_case(postgres_db, things, case_id):
    run_case('postgres', case_id)


def set_client_encoding(connection, name):
    raw = connection.connection
    if hasattr(raw, 'set_client_encoding'):
        # psycopg2 only tracks encoding changes made through its own API
        raw.set_client_encoding(name)
    else:
        # psycopg 3 reads the live server parameter
        with connection.cursor() as cursor:
            cursor.execute("SET client_encoding TO '{}'".format(name))


@pytest.mark.parametrize('pg_encoding, raw_bytes, text', [
    pytest.param('WIN1252', b"SELECT 'caf\xe9 \x80'", "SELECT 'café €'", id='WIN1252'),
    pytest.param('LATIN1', b"SELECT 'caf\xe9'", "SELECT 'café'", id='LATIN1'),
])
def test_postgres_python_encoding_uses_the_driver_encoding_table(postgres_db, pg_encoding, raw_bytes, text):
    # No stubs: the driver's own mapping (psycopg2.extensions.encodings, or psycopg 3's info.encoding) is used
    postgres_db.ensure_connection()
    set_client_encoding(postgres_db, pg_encoding)
    try:
        encoding = PostgresCompiler().python_encoding(postgres_db)
        assert utils.bytes_to_string(raw_bytes, encoding) == text
    finally:
        set_client_encoding(postgres_db, 'UTF8')


@pytest.mark.parametrize('pg_encoding, value, key', [
    pytest.param('WIN1252', 'café', 'non_ascii', id='WIN1252-cafe'),
    pytest.param('WIN1252', '€', 'non_ascii_euro', id='WIN1252-euro'),
    pytest.param('LATIN1', 'café', 'non_ascii', id='LATIN1-cafe'),
])
def test_executable_query_under_non_utf8_client_encoding(postgres_db, things, pg_encoding, value, key):
    postgres_db.ensure_connection()
    set_client_encoding(postgres_db, pg_encoding)
    try:
        compiled = Thing.objects.filter(name=value).executable_query
    finally:
        set_client_encoding(postgres_db, 'UTF8')
    assert compiled == pinned_sql('postgres', key)
    assert value in compiled
    assert '�' not in compiled
    with postgres_db.cursor() as cursor:
        cursor.execute(compiled)
        got = {row[0] for row in cursor.fetchall()}
    assert got == set(Thing.objects.filter(name=value).values_list('pk', flat=True))
    assert len(got) == 1


def test_unencodable_value_raises_the_driver_error(postgres_db, things):
    postgres_db.ensure_connection()
    set_client_encoding(postgres_db, 'LATIN1')
    try:
        # Both drivers raise UnicodeEncodeError from their own string dumper
        with pytest.raises(UnicodeEncodeError):
            Thing.objects.filter(name='東京').executable_query
    finally:
        set_client_encoding(postgres_db, 'UTF8')
