from django.db import connections
from django.db.models import QuerySet
from django.utils.functional import cached_property
from . import utils
from . import compilers


class SQLCompilerQuerySet(QuerySet):

    @cached_property
    def executable_query(self):

        """
        Takes the parameterized SQL query with the arg list and compiles the query so
        that it can be used anywhere - as a subquery in a Raw SQL query, in a SQL GUI interface, etc.
        """

        connection = utils.validate_connection(connections[self.db])

        if not connection:
            raise NotImplementedError('{} backend is not supported.'.format(connection['ENGINE']))

        query, params = self.query.sql_with_params()

        compiler = compilers[connection['ENGINE']]

        return compiler.compile_sql(connection, query, params)
