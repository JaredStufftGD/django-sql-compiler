from .postgresql import PostgresCompiler, PostgresTenantsCompiler, Psycopg2Compiler
from .mysql import MySQLCompiler

__all__ = [
    'MySQLCompiler',
    'PostgresCompiler',
    'PostgresTenantsCompiler',
    'Psycopg2Compiler',
    'compiler_map',
    'SUPPORTED_BACKENDS'
]

compilers = [
    MySQLCompiler,
    PostgresCompiler,
    PostgresTenantsCompiler,
    Psycopg2Compiler
]

compiler_map = {
    compiler.backend_name: compiler for compiler in compilers
}

SUPPORTED_BACKENDS = compiler_map.keys()
