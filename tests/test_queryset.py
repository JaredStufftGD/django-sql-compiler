import pytest
from django.db import connections, models

from sql_compiler import SQLCompilerManager


class Widget(models.Model):
    name = models.CharField(max_length=10)

    objects = SQLCompilerManager()

    class Meta:
        app_label = 'tests'


def test_unsupported_backend_raises_without_connecting():
    with pytest.raises(NotImplementedError):
        Widget.objects.all().executable_query
    assert connections['default'].connection is None


@pytest.mark.xfail(strict=True, raises=AssertionError, reason='queryset.py formats the message with the None returned by validate_connection, so it always reads "None backend is not supported."')
def test_unsupported_backend_message_names_engine():
    engine = connections['default'].settings_dict['ENGINE']
    with pytest.raises(NotImplementedError) as excinfo:
        Widget.objects.all().executable_query
    assert engine in str(excinfo.value)
