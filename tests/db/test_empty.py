import pytest
from django.db import connection
from django.db.models import Q

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
