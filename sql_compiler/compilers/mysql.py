from .base import BaseSQLCompiler


class MySQLCompiler(BaseSQLCompiler):

    backend_name = 'django.db.backends.mysql'

    def compile_sql(self, connection, query, params):
        with connection.cursor() as cursor:
            compiled_sql = self.mogrify(cursor, query, params)
        return compiled_sql

    def mogrify(self, cursor, query, args=None):
        db = cursor.connection
        if isinstance(query, str):
            query = query.encode(db.encoding)

        if args is not None:
            if isinstance(args, dict):
                nargs = {}
                for key, item in args.items():
                    if isinstance(key, str):
                        key = key.encode(db.encoding)
                    nargs[key] = db.literal(item)
                args = nargs
            else:
                args = tuple(map(db.literal, args))
            try:
                query = query % args
            except TypeError as m:
                raise ProgrammingError(str(m))

        return query
