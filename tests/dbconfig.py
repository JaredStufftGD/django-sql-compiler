import importlib
import importlib.util
import socket
from urllib.parse import parse_qsl, unquote, urlsplit

import pytest

from sql_compiler.compilers import MySQLCompiler, PostgresCompiler

POSTGRES_ENV = 'SQLCOMPILER_TEST_POSTGRES_URL'
MYSQL_ENV = 'SQLCOMPILER_TEST_MYSQL_URL'
SERVER_SIDE_BINDING_ENV = 'SQLCOMPILER_TEST_PG_SERVER_SIDE_BINDING'
POSTGRES_DEFAULT_URL = 'postgres://sqlcompiler:sqlcompiler@127.0.0.1:55432/sqlcompiler'
MYSQL_DEFAULT_URL = 'mysql://sqlcompiler:sqlcompiler@127.0.0.1:53306/sqlcompiler'

# Filled once by conftest.pytest_configure; read by the DB fixtures and test markers
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
    if parts.fragment:
        raise pytest.UsageError('{} must not contain a #fragment'.format(env_name))
    options = {}
    if parts.query:
        try:
            pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            raise pytest.UsageError('{} is not a valid database URL'.format(env_name))
        for key, option in pairs:
            if key in options:
                raise pytest.UsageError('{} repeats the URL option {}'.format(env_name, key))
            # isascii() first: str.isdigit() accepts characters int() rejects
            options[key] = int(option) if option.isascii() and option.isdigit() else option
    return {
        'NAME': unquote(parts.path.lstrip('/')),
        'USER': unquote(parts.username or ''),
        'PASSWORD': unquote(parts.password or ''),
        'HOST': host,
        'PORT': str(port) if port else '',
        'OPTIONS': options,
    }


def probe(driver, config):
    # None when a real connection works, else a short reason without the URL or password
    try:
        module = importlib.import_module(driver)
    except ImportError as exc:
        return 'driver {} failed to import ({})'.format(driver, type(exc).__name__)
    if driver == 'MySQLdb':
        connect = dict(database=config['NAME'], charset='utf8mb4')
    else:
        connect = dict(dbname=config['NAME'])
    try:
        connection = module.connect(
            host=config['HOST'],
            port=int(config['PORT']),
            user=config['USER'],
            password=config['PASSWORD'],
            connect_timeout=3,
            **connect
        )
    except (module.Error, OSError, UnicodeError) as exc:
        return 'cannot connect at {}:{} ({})'.format(config['HOST'], config['PORT'], type(exc).__name__)
    connection.close()
    return None


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
            merged = {'connect_timeout': 3}
        else:
            merged = {'connect_timeout': 3, 'charset': 'utf8mb4'}
        merged.update(config['OPTIONS'])
        if key == 'postgres' and binding == '1':
            merged['server_side_binding'] = True
        config['OPTIONS'] = merged
        unavailable = None
        if not explicit:
            if driver is None:
                unavailable = 'no driver installed (run uv run --exact {})'.format(hint)
            else:
                try:
                    socket.create_connection((config['HOST'], int(config['PORT'])), timeout=1).close()
                except OSError:
                    unavailable = 'nothing accepting connections at {}:{}'.format(config['HOST'], config['PORT'])
                else:
                    unavailable = probe(driver, config)
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
