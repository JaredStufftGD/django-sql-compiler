import codecs
import sys

from .base import BaseSQLCompiler


class PostgresCompiler(BaseSQLCompiler):

    """
    Compiles an executable SQL query from a parameterized query and arg list with the connection's own driver:
    psycopg2's cursor.mogrify, or for psycopg 3 (3.2 or later, client-side or server-side binding) a ClientCursor
    on the same raw connection. Any other driver raises NotImplementedError.
    Also reports the raw connection's client encoding as a Python codec name.
    """

    backend_name = 'django.db.backends.postgresql'

    def encoding_map(self):
        from psycopg2.extensions import encodings
        return encodings

    def driver(self, raw):
        # An established connection means its driver module is already imported, so this never imports one
        psycopg = sys.modules.get('psycopg')
        if psycopg is not None and isinstance(raw, psycopg.Connection):
            return 'psycopg'
        extensions = sys.modules.get('psycopg2.extensions')
        if extensions is not None and isinstance(raw, extensions.connection):
            return 'psycopg2'
        raise NotImplementedError(
            '{}.{} is not a psycopg2 or psycopg 3 connection; only those PostgreSQL drivers are supported.'.format(
                type(raw).__module__, type(raw).__qualname__))

    def psycopg_encoding(self, raw):
        # psycopg 3 reports a Python codec name, or raises its NotSupportedError for a client encoding Python has
        # no codec for (EUC_TW, MULE_INTERNAL); report that as LookupError, like an unknown psycopg2 encoding
        not_supported = sys.modules['psycopg'].NotSupportedError
        try:
            name = raw.info.encoding
        except not_supported as exc:
            raise LookupError('unsupported PostgreSQL client encoding: {}'.format(exc)) from None
        return codecs.lookup(name).name

    def python_encoding(self, connection):
        if connection.connection is None:
            connection.ensure_connection()
        raw = connection.connection
        if self.driver(raw) == 'psycopg':
            return self.psycopg_encoding(raw)
        name = raw.encoding
        try:
            return self.encoding_map()[name]
        except KeyError:
            raise LookupError('unknown PostgreSQL client encoding: {}'.format(name)) from None

    def compile_sql(self, connection, query, params):
        with connection.cursor() as cursor:
            raw = connection.connection
            if self.driver(raw) == 'psycopg':
                # Resolve the codec first, so an encoding Python can't handle raises LookupError, not from mogrify
                encoding = self.psycopg_encoding(raw)
                from psycopg import ClientCursor
                with ClientCursor(raw) as client_cursor:
                    text = client_cursor.mogrify(query, params)
                compiled_sql = text.encode(encoding)
            else:
                compiled_sql = cursor.mogrify(query, params)

        return compiled_sql


class PostgresTenantsCompiler(PostgresCompiler):
    backend_name = 'django_tenants.postgresql_backend'


class Psycopg2Compiler(PostgresCompiler):
    backend_name = 'django.db.backends.postgresql_psycopg2'
