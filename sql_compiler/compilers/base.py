

class BaseSQLCompiler:

    backend_name = None

    def compile_sql(self, connection, query, params):
        raise NotImplementedError('Subclasses must implement compile_sql')
