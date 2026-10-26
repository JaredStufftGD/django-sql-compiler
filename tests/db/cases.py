import datetime
from datetime import date
from decimal import Decimal

from django.db import connection
from django.db.models import F

from .expected import pinned_sql
from .models import Thing

UTC = datetime.timezone.utc

BACKSLASH_NAME = 'back\\slash'
ROW_1_TS = datetime.datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)

ROWS = [
    {'name': "it's", 'other': 'x', 'n': 1, 'flag': True, 'day': date(2024, 1, 2),
     'ts': ROW_1_TS, 'dec': Decimal('1.50')},
    {'name': BACKSLASH_NAME, 'other': 'slash', 'n': 2, 'flag': False, 'day': date(2024, 1, 3),
     'ts': datetime.datetime(2024, 1, 3, 3, 4, 5, tzinfo=UTC), 'dec': Decimal('2.25')},
    {'name': 'plain %', 'other': '%', 'n': 3, 'flag': True, 'day': date(2024, 1, 4),
     'ts': datetime.datetime(2024, 1, 4, 3, 4, 5, tzinfo=UTC), 'dec': Decimal('3.00')},
    {'name': 'café', 'other': 'caf', 'n': None, 'flag': False, 'day': None,
     'ts': None, 'dec': None},
    {'name': 'plain', 'other': 'zzz', 'n': 4, 'flag': False, 'day': date(2024, 1, 5),
     'ts': datetime.datetime(2024, 1, 5, 3, 4, 5, tzinfo=UTC), 'dec': Decimal('4.00')},
    {'name': '東京', 'other': 'tokyo', 'n': 5, 'flag': False, 'day': None,
     'ts': None, 'dec': None},
    {'name': '😀', 'other': 'emoji', 'n': 6, 'flag': False, 'day': None,
     'ts': None, 'dec': None},
    {'name': '€', 'other': 'euro', 'n': 7, 'flag': False, 'day': None,
     'ts': None, 'dec': None},
]

CASES = [
    ('single_quote', lambda: Thing.objects.filter(name="it's")),
    ('backslash', lambda: Thing.objects.filter(name=BACKSLASH_NAME)),
    ('percent_literal_param', lambda: Thing.objects.filter(name__contains='%')),
    ('percent_empty_params', lambda: Thing.objects.extra(where=["name LIKE 'plain%%'"])),
    ('percent_with_params', lambda: Thing.objects.filter(name__contains=F('other'), n__gt=0)),
    ('null', lambda: Thing.objects.filter(n__isnull=True)),
    ('null_param', lambda: Thing.objects.extra(where=['COALESCE(n, -1) = COALESCE(%s, -1)'], params=[None])),
    ('int', lambda: Thing.objects.filter(n=1)),
    ('decimal', lambda: Thing.objects.filter(dec=Decimal('1.50'))),
    ('float_param', lambda: Thing.objects.extra(where=['n < %s'], params=[2.5])),
    ('bool', lambda: Thing.objects.filter(flag=True)),
    ('bool_param', lambda: Thing.objects.extra(where=['flag = %s'], params=[True])),
    ('in_list', lambda: Thing.objects.filter(n__in=[1, 3])),
    ('date', lambda: Thing.objects.filter(day=date(2024, 1, 2))),
    ('datetime', lambda: Thing.objects.filter(ts=ROW_1_TS)),
    ('non_ascii_cjk', lambda: Thing.objects.filter(name='東京')),
    ('non_ascii_emoji', lambda: Thing.objects.filter(name='😀')),
]

CASE_IDS = [case_id for case_id, _ in CASES]

PERCENT_PRECONDITIONS = {
    'percent_empty_params': 'empty',
    'percent_with_params': 'nonempty',
}


def run_case(vendor, case_id):
    qs = dict(CASES)[case_id]()
    kind = PERCENT_PRECONDITIONS.get(case_id)
    if kind is not None:
        sql, params = qs.query.sql_with_params()
        assert '%%' in sql
        if kind == 'empty':
            assert params == ()
        else:
            assert len(params) > 0

    compiled = qs.executable_query
    assert compiled == pinned_sql(vendor, case_id)

    # No params, so the driver does no % interpolation of the compiled SQL
    with connection.cursor() as cursor:
        cursor.execute(compiled)
        got = {row[0] for row in cursor.fetchall()}
    want = set(qs.values_list('pk', flat=True))
    assert got == want
    assert 0 < len(got) < len(ROWS)
