from django.db import models
from django.db.models import Expression, F

from .composition import ComposeResult


def require_result(value, what):
    if not isinstance(value, ComposeResult):
        raise TypeError('{} needs a compose() result, got {}'.format(what, type(value).__name__))


def check_alias(result, connection, what):
    if connection.alias != result.alias:
        raise ValueError(
            '{} was composed for database alias {!r} but the query runs on alias {!r}'.format(
                what, result.alias, connection.alias
            )
        )


class ResultIn(Expression):
    """
    Route A prototype: the keys a compose() result selects, as the right-hand side of an __in lookup.
    `Model.objects.filter(pk__in=ResultIn(result, 'id'))`
    """

    def __init__(self, result, column, output_field=None, skip_null=False):
        require_result(result, 'ResultIn')
        super().__init__(output_field=output_field or models.IntegerField())
        self.result = result
        self.column = column
        self.skip_null = skip_null

    def as_sql(self, compiler, connection):
        check_alias(self.result, connection, 'ResultIn')
        column = connection.ops.quote_name(self.column)
        where = ' WHERE k.{} IS NOT NULL'.format(column) if self.skip_null else ''
        sql = '(SELECT k.{} FROM ({}) k{})'.format(column, self.result.sql, where)
        return sql, tuple(self.result.params)


class ResultExists(Expression):
    """
    Route A prototype: an EXISTS test against a compose() result. Each keyword maps a column of the composed
    SQL to an outer field name: `ResultExists(result, id='pk')`.
    """

    def __init__(self, result, **matches):
        if not matches:
            raise ValueError('ResultExists needs at least one column to match')
        require_result(result, 'ResultExists')
        super().__init__(output_field=models.BooleanField())
        self.result = result
        self.columns = list(matches)
        self.outer = [F(name) for name in matches.values()]

    def get_source_expressions(self):
        return self.outer

    def set_source_expressions(self, exprs):
        self.outer = list(exprs)

    def as_sql(self, compiler, connection):
        check_alias(self.result, connection, 'ResultExists')
        quote = connection.ops.quote_name
        params = list(self.result.params)
        tests = []
        for column, ref in zip(self.columns, self.outer):
            ref_sql, ref_params = compiler.compile(ref)
            tests.append('k.{} = {}'.format(quote(column), ref_sql))
            params.extend(ref_params)
        sql = 'EXISTS (SELECT 1 FROM ({}) k WHERE {})'.format(self.result.sql, ' AND '.join(tests))
        return sql, tuple(params)
