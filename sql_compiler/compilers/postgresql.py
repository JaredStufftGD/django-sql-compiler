import codecs

from .base import BaseSQLCompiler


class PostgresCompiler(BaseSQLCompiler):

    """
    Compiles an executable SQL query from a parameterized query and arg list using the postgresql/psycopg2 backend.
    Also reports the raw connection's client encoding as a Python codec name, for psycopg2 and psycopg 3.
    """

    backend_name = 'django.db.backends.postgresql'

    def encoding_map(self):
        from psycopg2.extensions import encodings
        return encodings

    def python_encoding(self, connection):
        raw = connection.connection
        info = getattr(raw, 'info', None)
        if info is not None and hasattr(info, 'encoding'):
            # psycopg 3 already reports a Python codec name
            return codecs.lookup(info.encoding).name
        name = raw.encoding
        try:
            return self.encoding_map()[name]
        except KeyError:
            raise LookupError('unknown PostgreSQL client encoding: {}'.format(name)) from None

    def compile_sql(self, connection, query, params):
        with connection.cursor() as cursor:
            compiled_sql = cursor.mogrify(query, params)

        return compiled_sql


class PostgresTenantsCompiler(PostgresCompiler):
    backend_name = 'django_tenants.postgresql_backend'


class Psycopg2Compiler(PostgresCompiler):
    backend_name = 'django.db.backends.postgresql_psycopg2'
