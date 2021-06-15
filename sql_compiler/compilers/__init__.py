from .postgresql import PostgresCompiler, PostgresTenantsCompiler, Psycopg2Compiler

__all__ = [
    'PostgresCompiler',
    'PostgresTenantsCompiler',
    'Psycopg2Compiler',
    'compiler_map',
    'SUPPORTED_BACKENDS'
]

compilers = [
    PostgresCompiler,
    PostgresTenantsCompiler,
    Psycopg2Compiler
]

compiler_map = {
    compiler.backend_name: compiler for compiler in compilers
}

SUPPORTED_BACKENDS = compiler_map.keys()
