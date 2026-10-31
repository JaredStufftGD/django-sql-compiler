import dataclasses

from django.db import connections

from .composition import ComposeResult


def row_kind_name(row):
    if isinstance(row, type):
        return row.__name__
    return '{} instance'.format(type(row).__name__)


def constructor_fields(row):
    fields = {}
    for name, field in row.__dataclass_fields__.items():
        # dataclasses records ClassVar vs InitVar only in the private _field_type; public API can't tell
        # them apart under string annotations (from __future__ import annotations). Guarded in tests/test_rows.py.
        if not field.init or field._field_type is dataclasses._FIELD_CLASSVAR:
            continue
        fields[name] = (
            field.default is not dataclasses.MISSING
            or field.default_factory is not dataclasses.MISSING
        )
    return fields


def names_list(names):
    return ', '.join(repr(name) for name in sorted(names))


def fetch_rows(result, row):

    """
    Runs a compose() result once on `result.alias` through Django's cursor and returns a list of rows
    (an empty list when there are no rows). Pass `dict` for dicts keyed by column name in select order,
    or a dataclass type for instances built by keyword from the same-named columns.

    Matching is exact and case-sensitive. The constructor fields are the dataclass fields its generated
    __init__ takes: InitVar fields are included, while `init=False` fields and ClassVar attributes are not
    fields, so a column of that name is an extra column. Fields with a default or default_factory may be
    missing from the columns and then get their default. With `@dataclass(init=False)` or a custom
    __init__ the same fields are used and the class is called with them as keyword arguments.

    Values are exactly what Django's cursor returns for the backend, never converted or checked against
    annotations (for example SQLite returns decimals as float). Portable results need explicit lowercase
    column aliases, because unaliased column names differ by backend: SQLite names them by expression
    text, and PostgreSQL uses `?column?` and folds unquoted aliases to lowercase.

    Checks run in this order: result is a ComposeResult, row is dict or a dataclass type (both TypeError,
    before any SQL runs), the statement executes, no result set, zero columns, duplicate column names, and
    dataclass mismatches (all ValueError), then the rows are fetched and built. The mismatch checks use only
    the cursor description, so a mismatch never instantiates the dataclass and is raised with zero rows too.
    Duplicate column names are an error for both row kinds.

    No transaction is added: the statement runs as the connection state dictates, so the no-result-set
    error is raised after the statement has run. So is any exception raised while building a row, which
    propagates unchanged: one from `__post_init__` or a custom __init__, or the TypeError raised when a
    `@dataclass(init=False)` class has no __init__ of its own and can't take keyword arguments. Inside
    `transaction.atomic()` the exception rolls it back.
    """

    if not isinstance(result, ComposeResult):
        raise TypeError('fetch_rows needs a ComposeResult from compose(), got {}'.format(type(result).__name__))
    is_dict = row is dict
    if not (is_dict or (isinstance(row, type) and dataclasses.is_dataclass(row))):
        raise TypeError('fetch_rows row must be dict or a dataclass type, got {}'.format(row_kind_name(row)))
    with connections[result.alias].cursor() as cursor:
        cursor.execute(result.sql, result.params)
        description = cursor.description
        if description is None:
            raise ValueError('fetch_rows: the statement returned no result set; it has already run')
        if not description:
            raise ValueError('fetch_rows: the result has no columns')
        names = [column[0] for column in description]
        duplicated = {name for name in names if names.count(name) > 1}
        if duplicated:
            raise ValueError(
                'fetch_rows: the result has duplicate column names: {}'.format(names_list(duplicated))
            )
        if not is_dict:
            fields = constructor_fields(row)
            extra = set(names) - set(fields)
            missing = {name for name, has_default in fields.items() if not has_default and name not in names}
            if extra or missing:
                parts = []
                if extra:
                    parts.append('columns with no field: ' + names_list(extra))
                if missing:
                    parts.append('fields with no column: ' + names_list(missing))
                raise ValueError(
                    'fetch_rows: the result columns do not match the constructor fields of {}: {}'.format(
                        row.__name__, '; '.join(parts)
                    )
                )
        records = cursor.fetchall()
    if is_dict:
        return [dict(zip(names, record)) for record in records]
    return [row(**dict(zip(names, record))) for record in records]
