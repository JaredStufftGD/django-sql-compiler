import importlib.util
import socket
from urllib.parse import unquote, urlsplit

import pytest

from sql_compiler.compilers import MySQLCompiler, PostgresCompiler

POSTGRES_ENV = 'SQLCOMPILER_TEST_POSTGRES_URL'
MYSQL_ENV = 'SQLCOMPILER_TEST_MYSQL_URL'
SERVER_SIDE_BINDING_ENV = 'SQLCOMPILER_TEST_PG_SERVER_SIDE_BINDING'
POSTGRES_DEFAULT_URL = 'postgres://sqlcompiler:sqlcompiler@127.0.0.1:55432/sqlcompiler'
MYSQL_DEFAULT_URL = 'mysql://sqlcompiler:sqlcompiler@127.0.0.1:53306/sqlcompiler'

# Filled once by conftest.pytest_configure; later plans read it
STATE = {}


def postgres_driver():
    # Django prefers psycopg 3 whenever it is importable
    if importlib.util.find_spec('psycopg'):
        return 'psycopg'
    if importlib.util.find_spec('psycopg2'):
        return 'psycopg2'
    return None


def mysql_driver():
    if importlib.util.find_spec('MySQLdb'):
        return 'MySQLdb'
    return None


def psycopg3_is_default():
    return STATE['default'] == 'postgres' and STATE['postgres']['driver'] == 'psycopg'


def gro10_ready():
    return (
        STATE['default'] == 'postgres'
        and STATE['postgres']['driver'] == 'psycopg2'
        and STATE['mysql']['alias'] == 'other'
    )


def gro14_xfail():
    if not psycopg3_is_default():
        return None
    if STATE['server_side_binding']:
        return pytest.mark.xfail(
            strict=True,
            raises=AttributeError,
            reason='GRO-14: with server_side_binding=True Django uses psycopg 3 server-binding cursors, which have no mogrify',
        )
    return pytest.mark.xfail(
        strict=True,
        raises=TypeError,
        reason="GRO-14: psycopg 3's client-side mogrify returns str, and bytes_to_string calls chr() on each character",
    )


def parse_url(env_name, value, schemes):
    # Never echo the value: it may carry a password
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
    except ValueError:
        raise pytest.UsageError('{} is not a valid database URL'.format(env_name))
    if parts.scheme not in schemes or not host or not parts.path.lstrip('/'):
        raise pytest.UsageError(
            '{} must be a {} URL with host and database name'.format(env_name, '/'.join(schemes))
        )
    return {
        'NAME': parts.path.lstrip('/'),
        'USER': unquote(parts.username or ''),
        'PASSWORD': unquote(parts.password or ''),
        'HOST': host,
        'PORT': str(port) if port else '',
    }


def build(environ):
    if importlib.util.find_spec('psycopg') and importlib.util.find_spec('psycopg2'):
        raise pytest.UsageError(
            'psycopg2 and psycopg 3 are both installed and Django would load psycopg 3. '
            'Run `uv run --exact --group pg2 pytest` (or `--group pg3`).'
        )

    binding = environ.get(SERVER_SIDE_BINDING_ENV, '')
    if binding and binding != '1':
        raise pytest.UsageError('{} must be 1 or unset'.format(SERVER_SIDE_BINDING_ENV))
    if binding == '1' and postgres_driver() != 'psycopg':
        raise pytest.UsageError(
            '{}=1 needs psycopg 3, run `uv run --exact --group pg3 pytest`'.format(SERVER_SIDE_BINDING_ENV)
        )

    specs = (
        ('postgres', 'PostgreSQL', POSTGRES_ENV, POSTGRES_DEFAULT_URL, ('postgres', 'postgresql'),
         PostgresCompiler.backend_name, postgres_driver(), '--group pg2 or pg3'),
        ('mysql', 'MySQL', MYSQL_ENV, MYSQL_DEFAULT_URL, ('mysql',),
         MySQLCompiler.backend_name, mysql_driver(), '--group mysql'),
    )
    state = {'server_side_binding': binding == '1'}
    settings_for = {}
    for key, label, env_name, default_url, schemes, engine, driver, hint in specs:
        explicit = bool(environ.get(env_name))
        config = parse_url(env_name, environ[env_name] if explicit else default_url, schemes)
        config['ENGINE'] = engine
        if key == 'postgres':
            config['OPTIONS'] = {'connect_timeout': 3}
            if binding == '1':
                config['OPTIONS']['server_side_binding'] = True
        else:
            config['OPTIONS'] = {'connect_timeout': 3, 'charset': 'utf8mb4'}
        unavailable = None
        if not explicit:
            if driver is None:
                unavailable = 'no driver installed (run uv run --exact {})'.format(hint)
            else:
                try:
                    socket.create_connection((config['HOST'], int(config['PORT'])), timeout=1).close()
                except OSError:
                    unavailable = 'nothing accepting connections at {}:{}'.format(config['HOST'], config['PORT'])
        settings_for[key] = config
        state[key] = {
            'label': label,
            'env': env_name,
            'explicit': explicit,
            'where': '{}:{}'.format(config['HOST'], config['PORT']),
            'driver': driver,
            'alias': None,
            'unavailable': unavailable,
        }

    def usable(key):
        return state[key]['explicit'] or state[key]['unavailable'] is None

    if state['postgres']['explicit']:
        default = 'postgres'
    elif state['mysql']['explicit']:
        default = 'mysql'
    elif usable('postgres'):
        default = 'postgres'
    elif usable('mysql'):
        default = 'mysql'
    else:
        default = 'sqlite'
    state['default'] = default

    if default == 'sqlite':
        # SQLite is only an unsupported ENGINE here; no connection is ever opened
        return {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}, state

    databases = {'default': settings_for[default]}
    state[default]['alias'] = 'default'
    if default == 'postgres' and usable('mysql'):
        databases['other'] = settings_for['mysql']
        state['mysql']['alias'] = 'other'
    return databases, state
