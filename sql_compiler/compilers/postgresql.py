from .base import BaseSQLCompiler


class PostgresCompiler(BaseSQLCompiler):

    """
    Compiles an executable SQL query from a parameterized query and arg list using the postgresql/psycopg2 backend.
    Also reports the psycopg2 connection's client encoding as a Python codec name.
    """

    backend_name = 'django.db.backends.postgresql'

    def encoding_map(self):
        from psycopg2.extensions import encodings
        return encodings

    def python_encoding(self, connection):
        name = connection.connection.encoding
        try:
            return self.encoding_map()[name]
        except KeyError:
            raise LookupError('unknown PostgreSQL client encoding: {}'.format(name))

    def compile_sql(self, connection, query, params):
        with connection.cursor() as cursor:
            compiled_sql = cursor.mogrify(query, params)

        return compiled_sql


class PostgresTenantsCompiler(PostgresCompiler):
    backend_name = 'django_tenants.postgresql_backend'


class Psycopg2Compiler(PostgresCompiler):
    backend_name = 'django.db.backends.postgresql_psycopg2'
