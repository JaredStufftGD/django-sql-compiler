from django.core.exceptions import EmptyResultSet
from django.db.models import QuerySet
from django.db.models.sql.where import NothingNode, WhereNode

from .compilers import SUPPORTED_BACKENDS


def validate_connection(connection):

    """
    Since not all back ends provide a method to compile the SQL together with the params,
    we need to check if the connection for the QuerySet is supported.

    returns the connection if it's valid, otherwise returns None
    """

    backend_name = connection.settings_dict['ENGINE']
    if backend_name in SUPPORTED_BACKENDS:
        return connection


def bytes_to_string(bytes_obj, encoding):

    """
    Decodes a bytes object to a string with the Python codec the connection's driver reports.

    Decoding is strict: LookupError (unknown codec) and UnicodeDecodeError (invalid bytes) propagate.
    """

    return bytes_obj.decode(encoding)


class AlwaysFalseHaving:

    """
    An always-false predicate that Django's compiler moves to HAVING, because it reports an aggregate.
    """

    contains_aggregate = True
    contains_over_clause = False

    def as_sql(self, compiler, connection):
        return '0 = 1', []

    def get_group_by_cols(self):
        return []


def zero_row_query(query, clear_ordering=False):

    """
    Returns a clone of the query that matches no rows and keeps the same select list (and GROUP BY).

    The whole WHERE tree is replaced, including members Django moves to HAVING or QUALIFY, because the
    compiler does not turn an empty HAVING into an always-false predicate. When Django groups the query
    (any aggregate it recognizes, through annotate, alias or values) an always-false predicate is added
    that Django moves to HAVING, because an aggregate without GROUP BY returns one row even when WHERE
    matches nothing. Ordering is kept, so a DISTINCT select list keeps the ORDER BY columns Django adds
    to it, unless clear_ordering is set. An empty slice (qs[n:n]) loses its LIMIT/OFFSET because it would
    otherwise emit OFFSET without LIMIT; other slices are kept. Combined queries are handled part by part. The original query is
    not changed.

    When ordering must be cleared (an ORDER BY on an empty subquery raises EmptyResultSet again), an ORDER BY
    expression Django would add to a DISTINCT select list is dropped, because it can't compile.

    Known limitation: a raw-SQL aggregate (RawSQL or extra(select=...), such as COUNT(*)) in a queryset with
    no aggregate Django recognizes has no GROUP BY and gets no HAVING, so its zero-row SQL returns one row.
    """

    clone = query.clone()
    if clone.high_mark is not None and clone.low_mark == clone.high_mark:
        # an empty slice would otherwise emit OFFSET without LIMIT, which SQLite and MySQL reject
        clone.clear_limits()
    if clear_ordering:
        clone.clear_ordering(force=True)
    if clone.combined_queries:
        clone.combined_queries = tuple(zero_row_query(part, clear_ordering) for part in clone.combined_queries)
    else:
        children = [NothingNode()]
        if clone.group_by is not None:
            # an aggregate without GROUP BY returns one row even when WHERE matches nothing
            children.append(AlwaysFalseHaving())
        clone.where = WhereNode(children)
    return clone


def query_sql_and_params(query, using):

    """
    Compiles the query for the alias and returns the parameterized SQL and its params.

    A query Django itself evaluates as empty is compiled again as a zero-row query with the same columns
    (keeping its ordering, and clearing it only if that still raises), and every query that compiles today
    gets exactly the same SQL and params. See zero_row_query for the known case where the zero-row SQL still
    returns a row.
    """

    try:
        return query.get_compiler(using=using).as_sql()
    except EmptyResultSet:
        pass
    try:
        return zero_row_query(query).get_compiler(using=using, elide_empty=False).as_sql()
    except EmptyResultSet:
        pass
    # An ORDER BY on an empty subquery (CR-01) still raises; zero rows have no order
    return zero_row_query(query, clear_ordering=True).get_compiler(using=using, elide_empty=False).as_sql()


def sql_and_params(queryset):

    """
    Returns the parameterized SQL (a str with Django's %s placeholders) and its params (a tuple)
    for the queryset's own database alias (`queryset.db`, from `.using()` or a database router).
    The alias is read on every call and nothing is cached. It works on every Django backend.

    The pair is meant for `connections[queryset.db].cursor().execute(sql, params)` (Django's cursor)
    and, for a queryset of the model's own instances, `raw(sql, params)` on that alias. It is not
    meant for the raw driver cursor.

    A queryset Django evaluates as empty returns SQL that matches no rows and has the same columns.
    A raw-SQL aggregate can still return one row; see zero_row_query for that known limitation.
    """

    if not isinstance(queryset, QuerySet):
        raise TypeError('sql_and_params needs a QuerySet, got {}'.format(type(queryset).__name__))
    alias = queryset.db
    sql, params = query_sql_and_params(queryset.query, alias)
    return sql, tuple(params)
