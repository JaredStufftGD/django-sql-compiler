from django.db import models

from sql_compiler import SQLCompilerManager


class Thing(models.Model):
    name = models.CharField(max_length=50)
    other = models.CharField(max_length=50)
    n = models.IntegerField(null=True)
    flag = models.BooleanField(default=False)
    day = models.DateField(null=True)
    ts = models.DateTimeField(null=True)
    dec = models.DecimalField(max_digits=6, decimal_places=2, null=True)

    objects = SQLCompilerManager()

    class Meta:
        app_label = 'tests'
        db_table = 'sqlcompiler_thing'
