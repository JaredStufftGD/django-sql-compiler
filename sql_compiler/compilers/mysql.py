from .base import BaseSQLCompiler


class MySQLCompiler(BaseSQLCompiler):

    backend_name = 'django.db.backends.mysql'

    def compile_sql(self, connection, query, params):
        pass
