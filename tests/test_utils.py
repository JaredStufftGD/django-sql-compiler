from types import SimpleNamespace

import pytest

from sql_compiler import utils

SUPPORTED_ENGINES = [
    'django.db.backends.mysql',
    'django.db.backends.postgresql',
    'django.db.backends.postgresql_psycopg2',
    'django_tenants.postgresql_backend',
]


def test_bytes_to_string_ascii():
    assert utils.bytes_to_string(b'SELECT 1') == 'SELECT 1'


@pytest.mark.xfail(strict=True, raises=AssertionError, reason='bytes_to_string decodes each byte as Latin-1 via chr(), garbling UTF-8 non-ASCII text')
def test_bytes_to_string_non_ascii():
    assert utils.bytes_to_string('é'.encode('utf-8')) == 'é'


@pytest.mark.parametrize('engine', SUPPORTED_ENGINES)
def test_validate_connection_supported(engine):
    connection = SimpleNamespace(settings_dict={'ENGINE': engine})
    assert utils.validate_connection(connection) is connection


def test_validate_connection_unsupported():
    connection = SimpleNamespace(settings_dict={'ENGINE': 'django.db.backends.sqlite3'})
    assert utils.validate_connection(connection) is None
