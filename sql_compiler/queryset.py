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

        The SQL is built for the queryset's own database alias, so the dialect and the
        escaping come from the same database.

        The result is decoded with the encoding the driver reports for this connection,
        and undecodable output raises instead of being garbled.
        """

        alias = self.db
        connection = utils.validate_connection(connections[alias])

        if not connection:
            raise NotImplementedError('{} backend is not supported.'.format(str(connection)))

        query, params = self.query.get_compiler(using=alias).as_sql()

        backend_name = connection.settings_dict['ENGINE']
        compiler = compilers.compiler_map[backend_name]()
        compiled_query = compiler.compile_sql(connection, query, params)
        if not isinstance(compiled_query, (bytes, bytearray)):
            raise TypeError('compile_sql must return bytes, got {}'.format(type(compiled_query).__name__))
        encoding = compiler.python_encoding(connection)
        compiled_query = utils.bytes_to_string(compiled_query, encoding)

        return compiled_query
