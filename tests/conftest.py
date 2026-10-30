import os

import django
import pytest
from django.conf import settings
from django.db import connections

from tests import dbconfig


def pytest_configure(config):
    # Guard: conftest can be loaded twice via different path spellings on Windows
    if settings.configured:
        return
    databases, state = dbconfig.build(os.environ)
    dbconfig.STATE.update(state)
    # Pinned timezone keeps expected datetime strings stable
    settings.configure(
        DATABASES=databases,
        INSTALLED_APPS=[],
        USE_TZ=True,
        TIME_ZONE='UTC',
    )
    django.setup()


def pytest_report_header(config):
    # Host and driver only: never the URL or password
    state = dbconfig.STATE
    parts = []
    for alias in ('default', 'other'):
        for key in ('postgres', 'mysql'):
            info = state[key]
            if info['alias'] != alias:
                continue
            source = 'from {}'.format(info['env']) if info['explicit'] else 'compose default'
            if key == 'postgres' and state['server_side_binding']:
                source += ', server_side_binding=True'
            parts.append('{}={} ({}, {}, {})'.format(alias, info['label'], info['driver'], info['where'], source))
    if state['default'] == 'sqlite':
        parts.append('default=SQLite (no-DB run)')
    parts.append('{}=SQLite (in-memory)'.format(dbconfig.SQLITE_LIVE_ALIAS))
    return 'sql_compiler test databases: {}'.format(', '.join(parts))


def pytest_collection_modifyitems(config, items):
    default = dbconfig.STATE['default']
    if default == 'sqlite':
        return
    label = dbconfig.STATE[default]['label']
    skip = pytest.mark.skip(
        reason='no-DB test: needs the unsupported SQLite default alias, but default is {}'.format(label)
    )
    for item in items:
        if item.path.name == 'test_queryset.py':
            item.add_marker(skip)


@pytest.fixture(scope='session')
def things_sqlite():
    # Imported here: Django is configured in pytest_configure
    from tests.db.cases import ROWS
    from tests.db.models import Thing

    alias = dbconfig.SQLITE_LIVE_ALIAS
    connection = connections[alias]
    with connection.schema_editor() as editor:
        if Thing._meta.db_table in connection.introspection.table_names():
            editor.delete_model(Thing)
        editor.create_model(Thing)
    Thing.objects.using(alias).bulk_create([Thing(**row) for row in ROWS])
    yield alias
    with connection.schema_editor() as editor:
        editor.delete_model(Thing)
