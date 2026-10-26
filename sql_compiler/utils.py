from django.core.exceptions import EmptyResultSet
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


def zero_row_query(query):

    """
    Returns a clone of the query that matches no rows and keeps the same select list (and GROUP BY).

    The whole WHERE tree is replaced, including members Django moves to HAVING or QUALIFY, because the
    compiler does not turn an empty HAVING into an always-false predicate. Ordering is cleared, because
    zero rows have no order and an ORDER BY on an empty subquery would raise EmptyResultSet again.
    Combined queries are handled part by part. The original query is not changed.

    Known limitation: an aggregate Django doesn't recognize (RawSQL or extra(select=...) such as COUNT(*))
    gets no GROUP BY, so the zero-row SQL is an aggregate without GROUP BY and returns one row.
    """

    clone = query.clone()
    clone.clear_ordering(force=True)
    if clone.combined_queries:
        clone.combined_queries = tuple(zero_row_query(part) for part in clone.combined_queries)
    else:
        clone.where = WhereNode([NothingNode()])
    return clone


def query_sql_and_params(query, using):

    """
    Compiles the query for the alias and returns the parameterized SQL and its params.

    A query Django itself evaluates as empty is compiled again as a zero-row query with the same columns,
    and every query that compiles today gets exactly the same SQL and params. See zero_row_query for the
    one known case where the zero-row SQL still returns a row.
    """

    try:
        return query.get_compiler(using=using).as_sql()
    except EmptyResultSet:
        return zero_row_query(query).get_compiler(using=using, elide_empty=False).as_sql()
