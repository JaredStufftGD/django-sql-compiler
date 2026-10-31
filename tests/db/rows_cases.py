import datetime
from dataclasses import InitVar, dataclass, field
from decimal import Decimal
from typing import ClassVar

import pytest
from django.db import connections

from sql_compiler import compose, fetch_rows

from .cases import ROWS
from .models import Thing

TRACKED = []


@dataclass
class Bucket:
    bucket: str
    cnt: int
    total: Decimal


@dataclass
class Flagged:
    id: int
    flag: bool
    amount: Decimal


@dataclass
class IdN:
    id: int
    n: int


@dataclass
class IdNName:
    id: int
    n: int
    name: str


@dataclass
class IdNDay:
    id: int
    n: int
    day: datetime.date


@dataclass
class WithDefaults:
    id: int
    n: int
    label: str = 'none'
    tags: list = field(default_factory=list)


@dataclass
class CaseTotal:
    id: int
    Total: int


@dataclass
class Tracked:
    id: int
    n: int

    def __post_init__(self):
        TRACKED.append(self.id)


@dataclass
class Scaled:
    id: int
    scale: InitVar[int]
    n: int
    scaled: int = field(init=False)

    def __post_init__(self, scale):
        self.scaled = self.n * scale


@dataclass
class Kinded:
    id: int
    n: int
    scaled: int = field(init=False, default=0)
    kind: ClassVar[str] = 'thing'


@dataclass
class Unrelated:
    other_name: str


def things(alias):
    return Thing.objects.using(alias)


AGG = (
    "SELECT CASE WHEN x.n > 3 THEN 'high' ELSE 'low' END AS bucket, COUNT(*) AS cnt, SUM(x.dec) AS total "
    "FROM (%(q)s) x WHERE x.n >= %(lo)s GROUP BY CASE WHEN x.n > 3 THEN 'high' ELSE 'low' END ORDER BY bucket"
)
AGG_EXPECTED = [('high', 4, Decimal('4.00')), ('low', 3, Decimal('6.75'))]


def dataclass_rows(alias):
    rows = fetch_rows(compose(AGG, q=things(alias).all(), lo=1), Bucket)
    assert type(rows) is list
    assert [type(r) for r in rows] == [Bucket, Bucket]
    assert [(r.bucket, r.cnt, r.total) for r in rows] == AGG_EXPECTED


def dict_rows(alias):
    rows = fetch_rows(compose(AGG, q=things(alias).all(), lo=1), dict)
    assert type(rows) is list
    assert [list(r) for r in rows] == [['bucket', 'cnt', 'total']] * 2
    assert [tuple(r.values()) for r in rows] == AGG_EXPECTED


def no_rows(alias):
    result = compose(AGG, q=things(alias).all(), lo=1000)
    for row in (dict, Bucket):
        rows = fetch_rows(result, row)
        assert rows == []
        assert type(rows) is list


def values_pass_through(alias):
    vendor = connections[alias].vendor
    template = (
        'SELECT x.id AS id, CASE WHEN x.flag THEN 1 ELSE 0 END AS flag, x.dec AS amount FROM (%(q)s) x'
    )
    result = compose(template, q=things(alias).filter(name="it's"))
    for row in (Flagged, dict):
        rows = fetch_rows(result, row)
        assert len(rows) == 1
        if row is dict:
            flag, dec = rows[0]['flag'], rows[0]['amount']
        else:
            flag, dec = rows[0].flag, rows[0].amount
        assert type(flag) is int
        assert flag == 1
        if vendor == 'sqlite':
            assert type(dec) is float
            assert dec == 1.5
        else:
            assert type(dec) is Decimal
            assert dec == Decimal('1.50')


def percent_literal(alias):
    result = compose(
        "SELECT x.name AS name FROM (%(q)s) x WHERE x.name LIKE 'plain %%' ORDER BY x.name",
        q=things(alias).all(),
    )
    assert result.params == ()
    assert fetch_rows(result, dict) == [{'name': 'plain %'}]


def duplicate_columns(alias):
    template = (
        'SELECT a.id AS id, b.id AS id, a.n AS n, b.n AS n, a.name AS name '
        'FROM (%(a)s) a JOIN (%(b)s) b ON a.id = b.id'
    )
    result = compose(template, a=things(alias).filter(n__lte=2), b=things(alias).filter(n__lte=2))
    message = "fetch_rows: the result has duplicate column names: 'id', 'n'"
    for row in (dict, IdNName, Unrelated):
        with pytest.raises(ValueError) as excinfo:
            fetch_rows(result, row)
        assert str(excinfo.value) == message


def no_result_set(alias):
    before = list(things(alias).order_by('id').values_list('id', 'n', 'name'))
    q = things(alias).filter(n__gt=1000).values('id')
    result = compose('UPDATE sqlcompiler_thing SET n = n WHERE id IN (SELECT x.id FROM (%(q)s) x)', q=q)
    message = 'fetch_rows: the statement returned no result set; it has already run'
    for row in (dict, IdN):
        with pytest.raises(ValueError) as excinfo:
            fetch_rows(result, row)
        assert str(excinfo.value) == message
    after = list(things(alias).order_by('id').values_list('id', 'n', 'name'))
    assert after == before
    assert len(after) == len(ROWS)


def mismatch(row, detail):
    return 'fetch_rows: the result columns do not match the constructor fields of {}: {}'.format(row.__name__, detail)


def run_select(alias, select, row, q=None):
    q = things(alias).filter(n__lte=3) if q is None else q
    return fetch_rows(compose(select + ' FROM (%(q)s) x ORDER BY x.id', q=q), row)


def expect_mismatch(alias, select, row, detail, q=None):
    with pytest.raises(ValueError) as excinfo:
        run_select(alias, select, row, q)
    assert str(excinfo.value) == mismatch(row, detail)


EXTRA = 'SELECT x.id AS id, x.n AS n, x.name AS name'


def extra_column(alias):
    expect_mismatch(alias, EXTRA, IdN, "columns with no field: 'name'")


def missing_field(alias):
    expect_mismatch(alias, 'SELECT x.id AS id', IdN, "fields with no column: 'n'")


def defaults_fill_missing(alias):
    rows = run_select(alias, 'SELECT x.id AS id, x.n AS n', WithDefaults)
    assert len(rows) == 3
    assert [r.n for r in rows] == [1, 2, 3]
    assert [r.label for r in rows] == ['none'] * 3
    assert [r.tags for r in rows] == [[], [], []]
    assert rows[0].tags is not rows[1].tags


def several_mismatches(alias):
    expect_mismatch(
        alias, 'SELECT x.id AS id, x.name AS name, x.other AS other', IdNDay,
        "columns with no field: 'name', 'other'; fields with no column: 'day', 'n'",
    )


def case_only_mismatch(alias):
    expect_mismatch(
        alias, 'SELECT x.id AS id, x.n AS total', CaseTotal,
        "columns with no field: 'total'; fields with no column: 'Total'",
    )


def mismatch_with_zero_rows(alias):
    expect_mismatch(alias, EXTRA, IdN, "columns with no field: 'name'", q=things(alias).filter(n__gt=1000))


def post_init_not_called(alias):
    del TRACKED[:]
    detail = "columns with no field: 'name'"
    expect_mismatch(alias, EXTRA, Tracked, detail)
    expect_mismatch(alias, EXTRA, Tracked, detail, q=things(alias).filter(n__gt=1000))
    assert TRACKED == []
    rows = run_select(alias, 'SELECT x.id AS id, x.n AS n', Tracked)
    assert len(rows) == 3
    assert TRACKED == [r.id for r in rows]


def initvar_filled(alias):
    rows = run_select(alias, 'SELECT x.id AS id, x.n AS n, 10 AS scale', Scaled)
    assert [r.scaled for r in rows] == [10, 20, 30]
    assert 'scale' not in vars(rows[0])


def init_false_and_classvar_are_extra(alias):
    expect_mismatch(
        alias, 'SELECT x.id AS id, x.n AS n, x.n AS scaled, x.name AS kind', Kinded,
        "columns with no field: 'kind', 'scaled'",
    )


CHECKS = {
    'dataclass_rows': dataclass_rows,
    'dict_rows': dict_rows,
    'no_rows': no_rows,
    'values_pass_through': values_pass_through,
    'percent_literal': percent_literal,
    'duplicate_columns': duplicate_columns,
    'no_result_set': no_result_set,
    'extra_column': extra_column,
    'missing_field': missing_field,
    'defaults_fill_missing': defaults_fill_missing,
    'several_mismatches': several_mismatches,
    'case_only_mismatch': case_only_mismatch,
    'mismatch_with_zero_rows': mismatch_with_zero_rows,
    'post_init_not_called': post_init_not_called,
    'initvar_filled': initvar_filled,
    'init_false_and_classvar_are_extra': init_false_and_classvar_are_extra,
}
CHECK_IDS = list(CHECKS)


def run_check(alias, check_id):
    CHECKS[check_id](alias)
