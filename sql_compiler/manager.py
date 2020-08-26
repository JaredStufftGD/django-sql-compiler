from django.db.models import Manager
from .queryset import SQLCompilerQuerySet


class SQLCompilerManager(Manager):

    """
    Wraps the SQLCompilerQuerySet object in a manager. Use this manager for any model
    for which you'd like to retrieve an executable SQL query for subsequent query sets.
    """

    def get_queryset(self):
        return SQLCompilerQuerySet(self.model, using=self._db)
