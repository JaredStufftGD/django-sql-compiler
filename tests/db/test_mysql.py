import codecs

import pytest
from django.db import connections

from tests import dbconfig

from .cases import CASE_IDS, run_case
from .expected import EXPECTED
from .models import Thing


@pytest.mark.parametrize('case_id', CASE_IDS)
def test_mysql_case(mysql_db, things, case_id):
    run_case('mysql', case_id)


def test_mysql_latin1_connection_round_trips_cafe_and_euro(mysql_db, things):
    mysql_db.ensure_connection()
    assert codecs.lookup(mysql_db.connection.encoding).name == 'utf-8'
    latin1 = connections[dbconfig.MYSQL_LATIN1_ALIAS]
    try:
        latin1.ensure_connection()
        assert codecs.lookup(latin1.connection.encoding).name != 'utf-8'
        for value, key in (('café', 'non_ascii'), ('€', 'non_ascii_euro')):
            qs = Thing.objects.using(dbconfig.MYSQL_LATIN1_ALIAS).filter(name=value)
            compiled = qs.executable_query
            assert compiled == EXPECTED['mysql'][key]
            with latin1.cursor() as cursor:
                cursor.execute(compiled)
                got = {row[0] for row in cursor.fetchall()}
            assert got == set(Thing.objects.filter(name=value).values_list('pk', flat=True))
            assert len(got) == 1
    finally:
        latin1.close()


def test_mysql_binary_param_invalid_in_connection_encoding_raises(mysql_db):
    # mysqlclient renders bytes as a quoted literal with the raw bytes (no _binary prefix);
    # b'\xff\xfe' is invalid UTF-8 but valid cp1252, so this runs on the default utf8mb4 alias
    qs = Thing.objects.extra(where=['name = %s'], params=[b'\xff\xfe'])
    with pytest.raises(UnicodeDecodeError):
        qs.executable_query
