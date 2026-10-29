from collections import Counter

import pytest
from django.db import connections
from django.db.models import Count

# (shape_id, factory(base), kind, ordered); base is a manager or queryset already bound to the alias
SHAPES = [
    ('filtered', lambda base: base.filter(n__lte=3), 'instances', False),
    ('ordered', lambda base: base.filter(n__isnull=False).order_by('-n', 'pk'), 'instances', True),
    ('values', lambda base: base.filter(n__gte=2).values('id', 'name', 'n').order_by('n', 'pk'), 'values', True),
    ('values_list', lambda base: base.values_list('id', 'name', 'n').order_by('n', 'pk'), 'values', True),
    ('count_group_by', lambda base: base.values('flag').annotate(c=Count('id')).order_by('flag'), 'count', True),
    ('annotated', lambda base: base.annotate(c=Count('other')).order_by('pk'), 'annotated', True),
    ('union', lambda base: base.filter(n__lte=3).union(base.filter(n__gte=2)), 'combined', False),
    (
        'union_ordered',
        lambda base: base.filter(n__lte=3).union(base.filter(n__gte=6)).order_by('n'),
        'combined',
        True,
    ),
    ('intersection', lambda base: base.filter(n__lte=3).intersection(base.filter(n__gte=2)), 'combined', False),
    ('difference', lambda base: base.filter(n__lte=3).difference(base.filter(n__gte=2)), 'combined', False),
]
SHAPE_IDS = [shape[0] for shape in SHAPES]
# Model-instance shapes without aggregates: raw() needs the pk column
RAW_SHAPE_IDS = ['filtered', 'ordered']

# (shape_id, empty_factory(base), counterpart_factory(base))
EMPTY_SHAPES = [
    ('none', lambda base: base.none(), lambda base: base.all()),
    ('in_empty', lambda base: base.filter(id__in=[]), lambda base: base.all()),
    (
        'empty_having',
        lambda base: base.annotate(c=Count('id')).filter(c__in=[]),
        lambda base: base.annotate(c=Count('id')),
    ),
    ('empty_slice', lambda base: base.all()[5:5], lambda base: base.all()),
    ('empty_offset', lambda base: base.filter(id__in=[])[2:5], lambda base: base.all()),
]
EMPTY_IDS = [shape[0] for shape in EMPTY_SHAPES]

FEATURE_FLAGS = {
    'union': 'supports_select_union',
    'union_ordered': 'supports_select_union',
    'intersection': 'supports_select_intersection',
    'difference': 'supports_select_difference',
}


def run_pair(alias, sql, params):
    with connections[alias].cursor() as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall()), [col[0] for col in cursor.description]


def expected_rows(qs, kind):
    if kind == 'instances':
        return [obj.pk for obj in qs]
    if kind == 'values':
        return [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in qs]
    if kind == 'count':
        return [d['c'] for d in qs]
    if kind == 'annotated':
        return [(obj.pk, obj.c) for obj in qs]
    if kind == 'combined':
        return [(obj.pk, obj.name, obj.n) for obj in qs]
    raise ValueError(kind)


def cursor_projection(rows, kind):
    if kind == 'instances':
        return [row[0] for row in rows]
    if kind == 'values':
        return [tuple(row) for row in rows]
    if kind == 'count':
        return [row[-1] for row in rows]
    if kind == 'annotated':
        return [(row[0], row[-1]) for row in rows]
    if kind == 'combined':
        return [(row[0], row[1], row[3]) for row in rows]
    raise ValueError(kind)


def assert_pair_matches_queryset(qs, alias, pair, kind, ordered):
    sql, params = pair
    assert isinstance(sql, str)
    assert type(params) is tuple
    rows, _ = run_pair(alias, sql, params)
    got = cursor_projection(rows, kind)
    want = expected_rows(qs, kind)
    assert len(want) > 0
    if ordered:
        assert got == want
    else:
        assert Counter(got) == Counter(want)
    return rows


def assert_empty_pair(alias, pair, counterpart_pair):
    rows, columns = run_pair(alias, *pair)
    counterpart_rows, counterpart_columns = run_pair(alias, *counterpart_pair)
    assert rows == []
    assert columns == counterpart_columns
    assert counterpart_rows != []


def require_features(alias, shape_id):
    flag = FEATURE_FLAGS.get(shape_id)
    if flag is None:
        return
    connection = connections[alias]
    if not getattr(connection.features, flag):
        pytest.skip('{} does not support {} (connection.features.{})'.format(connection.vendor, shape_id, flag))
