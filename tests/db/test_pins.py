import pytest
from django.core.exceptions import EmptyResultSet
from django.db import connection

from tests import dbconfig

from .cases import ROWS
from .expected import EXPECTED
from .models import Thing

GRO9_XFAIL = dbconfig.gro14_xfail() or pytest.mark.xfail(strict=True, raises=AssertionError, reason='GRO-9: bytes_to_string decodes each UTF-8 byte as its own character, so café comes out garbled')


@GRO9_XFAIL
def test_non_ascii_param_is_not_garbled(db_under_test, things):
    qs = Thing.objects.filter(name='café')
    assert qs.executable_query == EXPECTED[db_under_test]['non_ascii']

    with connection.cursor() as cursor:
        cursor.execute(qs.executable_query)
        got = {row[0] for row in cursor.fetchall()}
    assert got == set(qs.values_list('pk', flat=True))
    assert 0 < len(got) < len(ROWS)


@pytest.mark.skipif(not dbconfig.gro10_ready(), reason='GRO-10 pin needs default=PostgreSQL via psycopg2 and MySQL as alias other; run uv run --exact --group pg2 --group mysql pytest')
@pytest.mark.xfail(strict=True, raises=AssertionError, reason='GRO-10: sql_with_params() compiles for the default alias, so a queryset on the MySQL alias gets PostgreSQL SQL')
def test_non_default_alias_compiles_for_its_own_backend():
    assert Thing.objects.using('other').filter(name="it's").executable_query == EXPECTED['mysql']['single_quote']


@pytest.mark.skipif(dbconfig.psycopg3_is_default(), reason='GRO-13 pin is skipped under psycopg 3: EmptyResultSet is raised before mogrify, so it cannot strict-xfail naming GRO-14')
@pytest.mark.xfail(strict=True, raises=EmptyResultSet, reason='GRO-13: sql_with_params() raises EmptyResultSet for .none() querysets before any SQL is compiled')
def test_none_queryset_compiles(db_under_test, things):
    compiled = Thing.objects.none().executable_query
    with connection.cursor() as cursor:
        cursor.execute(compiled)
        assert cursor.fetchall() == []
