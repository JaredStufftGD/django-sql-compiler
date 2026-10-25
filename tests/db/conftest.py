import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, connections
from django.db.utils import DatabaseError

from tests import dbconfig


def vendor_unavailable(key):
    info = dbconfig.STATE[key]
    if info['unavailable']:
        return '{} unavailable: {}'.format(info['label'], info['unavailable'])
    default = dbconfig.STATE['default']
    if default == 'sqlite':
        return '{} not under test: no database under test'.format(info['label'])
    if info['alias'] == 'other':
        return "{} not under test: it is the 'other' alias in this run; its cases run in the mysql-only run".format(
            info['label']
        )
    return '{} not under test: default alias is {}'.format(info['label'], dbconfig.STATE[default]['label'])


@pytest.fixture(scope='session', autouse=True)
def explicit_databases_ready():
    for key in ('postgres', 'mysql'):
        info = dbconfig.STATE[key]
        if not info['explicit']:
            continue
        if info['driver'] is None:
            pytest.fail(
                '{label} is explicitly configured by {env} ({where}) but its driver is not installed; '
                'run uv run --exact --group <group> pytest'.format(**info)
            )
        alias = info['alias'] or ('default' if dbconfig.STATE['default'] == key else None)
        if alias is None:
            continue
        try:
            connections[alias].ensure_connection()
        except (ImproperlyConfigured, DatabaseError) as exc:
            pytest.fail(
                '{label} is explicitly configured by {env} ({where}) but cannot connect: '.format(**info)
                + '{}: {}'.format(type(exc).__name__, exc)
            )


@pytest.fixture(scope='session')
def postgres_db():
    if dbconfig.STATE['default'] == 'postgres':
        return connections['default']
    pytest.skip(vendor_unavailable('postgres'))


@pytest.fixture(scope='session')
def mysql_db():
    if dbconfig.STATE['default'] == 'mysql':
        return connections['default']
    pytest.skip(vendor_unavailable('mysql'))


@pytest.fixture(scope='session')
def db_under_test():
    default = dbconfig.STATE['default']
    if default == 'sqlite':
        pytest.skip('No database under test: {}; {}'.format(vendor_unavailable('postgres'), vendor_unavailable('mysql')))
    return default


@pytest.fixture(scope='session')
def things(db_under_test):
    # Imported here: this conftest loads before pytest_configure sets up Django
    from .cases import ROWS
    from .models import Thing

    with connection.schema_editor() as editor:
        if Thing._meta.db_table in connection.introspection.table_names():
            editor.delete_model(Thing)
        editor.create_model(Thing)
    Thing.objects.bulk_create([Thing(**row) for row in ROWS])
    yield
    with connection.schema_editor() as editor:
        editor.delete_model(Thing)


@pytest.fixture(scope='session')
def things_other(things):
    # Imported here: this conftest loads before pytest_configure sets up Django
    from .cases import ROWS
    from .models import Thing

    other = connections['other']
    with other.schema_editor() as editor:
        if Thing._meta.db_table in other.introspection.table_names():
            editor.delete_model(Thing)
        editor.create_model(Thing)
    Thing.objects.using('other').bulk_create([Thing(**row) for row in ROWS])
    yield
    with other.schema_editor() as editor:
        editor.delete_model(Thing)
