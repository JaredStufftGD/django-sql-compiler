from .postgresql import PostgresCompiler

__all__ = ['PostgresCompiler', 'connection_map', 'SUPPORTED_BACKENDS']

compilers = [
    PostgresCompiler
]

connection_map = {
    compiler.backend_name: compiler for compiler in compilers
}

SUPPORTED_BACKENDS = connection_map.keys()
