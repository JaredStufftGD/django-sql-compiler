from .postgresql import PostgresCompiler

__all__ = ['PostgresCompiler', 'compiler_map', 'SUPPORTED_BACKENDS']

compilers = [
    PostgresCompiler
]

compiler_map = {
    compiler.backend_name: compiler for compiler in compilers
}

SUPPORTED_BACKENDS = compiler_map.keys()
