

class BaseSQLCompiler:

    backend_name = None

    def compile_sql(self, connection, query, params):
        raise NotImplementedError('Subclasses must implement compile_sql')

    def python_encoding(self, connection):
        raise NotImplementedError('Subclasses must implement python_encoding')
