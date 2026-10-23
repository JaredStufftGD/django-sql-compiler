import django
from django.conf import settings


def pytest_configure(config):
    # Guard: conftest can be loaded twice via different path spellings on Windows
    if settings.configured:
        return
    # SQLite is only an unsupported ENGINE here; no connection is ever opened
    settings.configure(
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        INSTALLED_APPS=[],
    )
    django.setup()
