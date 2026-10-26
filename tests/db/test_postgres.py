import pytest

from sql_compiler import utils
from sql_compiler.compilers import PostgresCompiler

from .cases import CASE_IDS, run_case

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
