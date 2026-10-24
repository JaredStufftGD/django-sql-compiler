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
    assert utils.bytes_to_string(b'SELECT 1', 'utf8') == 'SELECT 1'


def test_bytes_to_string_non_ascii():
    text = 'café 東京 😀'
    assert utils.bytes_to_string(text.encode('utf-8'), 'utf8') == text
    assert utils.bytes_to_string('€'.encode('cp1252'), 'cp1252') == '€'


def test_bytes_to_string_unknown_encoding_raises_lookup_error():
    with pytest.raises(LookupError):
        utils.bytes_to_string(b'x', 'no-such-codec')


def test_bytes_to_string_invalid_bytes_raise_unicode_decode_error():
    with pytest.raises(UnicodeDecodeError):
        utils.bytes_to_string(b'\xff\xfe', 'utf8')


@pytest.mark.parametrize('engine', SUPPORTED_ENGINES)
def test_validate_connection_supported(engine):
    connection = SimpleNamespace(settings_dict={'ENGINE': engine})
    assert utils.validate_connection(connection) is connection


def test_validate_connection_unsupported():
    connection = SimpleNamespace(settings_dict={'ENGINE': 'django.db.backends.sqlite3'})
    assert utils.validate_connection(connection) is None
