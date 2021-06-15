from .base import BaseSQLCompiler


class PostgresCompiler(BaseSQLCompiler):

    """
    Compiles an executable SQL query from a parameterized query and arg list using the postgresql/psycopg2 backend.
    """

    backend_name = 'django.db.backends.postgresql'

    def compile_sql(self, connection, query, params):
        with connection.cursor() as cursor:
            compiled_sql = cursor.mogrify(query, params)

        return compiled_sql


class PostgresTenantsCompiler(PostgresCompiler):
    backend_name = 'django_tenants.postgresql_backend'


class Psycopg2Compiler(PostgresCompiler):
    backend_name = 'django.db.backends.postgresql_psycopg2'
