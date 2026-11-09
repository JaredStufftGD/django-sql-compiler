import uuid

from django.db import connections, models

from sql_compiler import SQLCompilerManager

SPIKE_LABELS = [(1, 'a%'), (2, 'a%%'), (3, 'b')]
UUID_1 = uuid.UUID('00000000-0000-4000-8000-000000000001')
UUID_2 = uuid.UUID('00000000-0000-4000-8000-000000000002')
SPIKE_UUIDS = [(UUID_1, 'u1'), (UUID_2, 'u2')]
SPIKE_PAIRS = [(1, 1, 1, 'p11'), (2, 1, 2, 'p12'), (3, 2, 1, 'p21')]


class SpikeLabel(models.Model):
    id = models.IntegerField(primary_key=True)
    label = models.CharField(max_length=20)

    objects = SQLCompilerManager()

    class Meta:
        app_label = 'tests'
        db_table = 'sqlcompiler_spike_label'


class SpikeUuid(models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=20)

    objects = SQLCompilerManager()

    class Meta:
        app_label = 'tests'
        db_table = 'sqlcompiler_spike_uuid'


class SpikePair(models.Model):
    id = models.IntegerField(primary_key=True)
    a = models.IntegerField()
    b = models.IntegerField()
    label = models.CharField(max_length=20)

    objects = SQLCompilerManager()

    class Meta:
        app_label = 'tests'
        db_table = 'sqlcompiler_spike_pair'
        unique_together = [('a', 'b')]


class SpikeBench(models.Model):
    id = models.IntegerField(primary_key=True)
    v = models.IntegerField()

    objects = SQLCompilerManager()

    class Meta:
        app_label = 'tests'
        db_table = 'sqlcompiler_spike_bench'


SPIKE_MODELS = [SpikeLabel, SpikeUuid, SpikePair]

SPIKE_ROWS = {
    SpikeLabel: [{'id': pk, 'label': label} for pk, label in SPIKE_LABELS],
    SpikeUuid: [{'id': pk, 'name': name} for pk, name in SPIKE_UUIDS],
    SpikePair: [{'id': pk, 'a': a, 'b': b, 'label': label} for pk, a, b, label in SPIKE_PAIRS],
}


def install(alias):
    connection = connections[alias]
    for model in SPIKE_MODELS:
        with connection.schema_editor() as editor:
            if model._meta.db_table in connection.introspection.table_names():
                editor.delete_model(model)
            editor.create_model(model)
        model.objects.using(alias).bulk_create([model(**row) for row in SPIKE_ROWS[model]])


def uninstall(alias):
    connection = connections[alias]
    for model in reversed(SPIKE_MODELS):
        with connection.schema_editor() as editor:
            editor.delete_model(model)
