from django.db import models
from django.db.models.sql.datastructures import BaseTable

from . import spike_a
from .queryset import SQLCompilerQuerySet


class DerivedTable(BaseTable):
    """
    Route B prototype: the FROM source of a query is the SQL a compose() result holds, as a derived table.
    """

    def __init__(self, table_name, alias, result=None):
        super().__init__(table_name, alias)
        self.result = result

    def as_sql(self, compiler, connection):
        spike_a.check_alias(self.result, connection, 'DerivedTable')
        # BaseTable quotes through whatever the installed Django offers, without a deprecated call
        quoted_alias = BaseTable(self.table_alias, self.table_alias).as_sql(compiler, connection)[0]
        return '({}) {}'.format(self.result.sql, quoted_alias), list(self.result.params)

    def relabeled_clone(self, change_map):
        return self.__class__(self.table_name, change_map.get(self.table_alias, self.table_alias), self.result)

    @property
    def identity(self):
        return self.__class__, self.table_name, self.table_alias, self.result


READ_ONLY_METHODS = (
    'update',
    'delete',
    'create',
    'get_or_create',
    'update_or_create',
    'bulk_create',
    'bulk_update',
    'select_for_update',
    '_raw_delete',
    '_insert',
    '_update',
)


def refuse(name):
    def method(self, *args, **kwargs):
        raise TypeError('{}() is not allowed on a queryset over composed SQL: it is read-only'.format(name))

    method.__name__ = name
    return method


class DerivedQuerySet(SQLCompilerQuerySet):
    update = refuse('update')
    delete = refuse('delete')
    create = refuse('create')
    get_or_create = refuse('get_or_create')
    update_or_create = refuse('update_or_create')
    bulk_create = refuse('bulk_create')
    bulk_update = refuse('bulk_update')
    select_for_update = refuse('select_for_update')
    _raw_delete = refuse('_raw_delete')
    _insert = refuse('_insert')
    _update = refuse('_update')


class DerivedModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        raise TypeError('save() is not allowed on a row from composed SQL: it is read-only')

    def delete(self, *args, **kwargs):
        raise TypeError('delete() is not allowed on a row from composed SQL: it is read-only')


def derived(model, result):
    spike_a.require_result(result, 'derived')
    if not (isinstance(model, type) and issubclass(model, DerivedModel)):
        raise TypeError('derived() needs a DerivedModel subclass, got {!r}'.format(model))
    qs = DerivedQuerySet(model=model, using=result.alias)
    alias = qs.query.get_initial_alias()
    qs.query.alias_map[alias] = DerivedTable(model._meta.db_table, alias, result)
    return qs
