import pytest
from django.db import connection, connections
from django.db.models import Count, Q, Value

from tests import dbconfig

from .expected import EXPECTED
from .models import Thing

_gro14 = dbconfig.gro14_xfail()


def gro14_only(func):
    if _gro14 is None:
        return func
    return _gro14(func)


# These empty-looking shapes compiled before GRO-13 was fixed, so their SQL must stay byte-identical (list B).
UNCHANGED_CASES = [
    ('union_one_empty', lambda: Thing.objects.filter(id__in=[]).union(Thing.objects.filter(name='plain'))),
    ('union_none_part', lambda: Thing.objects.none().union(Thing.objects.filter(name='plain'))),
    ('or_empty_subquery', lambda: Thing.objects.filter(Q(pk__in=Thing.objects.none()) | Q(name='plain'))),
]
UNCHANGED_IDS = [case_id for case_id, _ in UNCHANGED_CASES]


@gro14_only
@pytest.mark.parametrize('case_id', UNCHANGED_IDS)
def test_empty_part_shapes_are_unchanged(db_under_test, things, case_id):
    qs = dict(UNCHANGED_CASES)[case_id]()
    compiled = qs.executable_query
    assert compiled == EXPECTED[db_under_test][case_id]
    with connection.cursor() as cursor:
        cursor.execute(compiled)
        got = {row[0] for row in cursor.fetchall()}
    want = {obj.pk for obj in qs}
    assert got == want
    assert len(got) == 1


# The following shapes raised EmptyResultSet before the fix (list A). Each is paired with a
# non-empty counterpart whose columns the zero-row SQL must reproduce.
EMPTY_CASES = [
    ('none', lambda: Thing.objects.none(), lambda: Thing.objects.all()),
    ('in_empty', lambda: Thing.objects.filter(id__in=[]), lambda: Thing.objects.all()),
    ('values', lambda: Thing.objects.filter(id__in=[]).values('name'), lambda: Thing.objects.values('name')),
    ('values_list', lambda: Thing.objects.filter(id__in=[]).values_list('pk', 'name'), lambda: Thing.objects.values_list('pk', 'name')),
    ('union_all_empty',
     lambda: Thing.objects.filter(id__in=[]).union(Thing.objects.filter(name__in=[])),
     lambda: Thing.objects.filter(name='plain').union(Thing.objects.filter(name="it's"))),
    ('subquery_none', lambda: Thing.objects.filter(pk__in=Thing.objects.none()), lambda: Thing.objects.filter(pk__in=Thing.objects.all())),
    ('empty_having', lambda: Thing.objects.annotate(c=Count('id')).filter(c__in=[]), lambda: Thing.objects.annotate(c=Count('id'))),
    ('aggregate_without_group_by', lambda: Thing.objects.values(x=Value(1)).annotate(c=Count('id')).filter(c__in=[]), lambda: Thing.objects.values(x=Value(1)).annotate(c=Count('id'))),
    ('distinct_ordered', lambda: Thing.objects.filter(id__in=[]).values('name').order_by('id').distinct(), lambda: Thing.objects.values('name').order_by('id').distinct()),
]
EMPTY_IDS = [case_id for case_id, _, _ in EMPTY_CASES]


def counterpart_columns(cursor, counterpart):
    sql, params = counterpart.query.get_compiler(using=counterpart.db).as_sql()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    return [col[0] for col in cursor.description], rows


@gro14_only
@pytest.mark.parametrize('case_id', EMPTY_IDS)
def test_empty_queryset_compiles_to_zero_rows(db_under_test, things, case_id):
    factories = {key: (empty, counterpart) for key, empty, counterpart in EMPTY_CASES}
    empty_factory, counterpart_factory = factories[case_id]
    qs = empty_factory()
    compiled = qs.executable_query
    assert list(qs) == []
    with connection.cursor() as cursor:
        cursor.execute(compiled)
        assert list(cursor.fetchall()) == []
        got = [col[0] for col in cursor.description]
        want, rows = counterpart_columns(cursor, counterpart_factory())
    assert got == want
    assert len(rows) > 0


@gro14_only
def test_none_queryset_compiles(db_under_test, things):
    compiled = Thing.objects.none().executable_query
    assert compiled == EXPECTED[db_under_test]['none']
    with connection.cursor() as cursor:
        cursor.execute(compiled)
        assert list(cursor.fetchall()) == []


@gro14_only
def test_empty_single_column_sql_works_as_in_subquery(db_under_test, things):
    inner = Thing.objects.filter(id__in=[]).values('pk').executable_query
    sql = 'SELECT id FROM sqlcompiler_thing WHERE id IN ({})'.format(inner)
    with connection.cursor() as cursor:
        cursor.execute(sql)
        assert list(cursor.fetchall()) == []


# Under psycopg 3 this skips with the GRO-10 reason instead of XFAILing as GRO-14, because the
# 'other' alias only exists in the psycopg2 combined run.
gro10 = pytest.mark.skipif(not dbconfig.gro10_ready(), reason='GRO-10 pin needs default=PostgreSQL via psycopg2 and MySQL as alias other; run uv run --exact --group pg2 --group mysql pytest')


@gro10
def test_other_alias_none_compiles_to_zero_rows(things_other):
    qs = Thing.objects.using('other').none()
    compiled = qs.executable_query
    assert compiled == EXPECTED['mysql']['none']
    assert list(qs) == []
    with connections['other'].cursor() as cursor:
        cursor.execute(compiled)
        assert list(cursor.fetchall()) == []
        got = [col[0] for col in cursor.description]
        want, rows = counterpart_columns(cursor, Thing.objects.using('other').all())
    assert got == want
    assert len(rows) > 0
