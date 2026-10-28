import inspect

import pytest
from django.db import connections
from django.db.models import QuerySet

import sql_compiler
import sql_compiler.utils
from sql_compiler.queryset import SQLCompilerQuerySet
from sql_compiler import utils

from tests import dbconfig
from tests.db.models import PlainThing, Thing

REJECTED = {
    'manager': (lambda: Thing.objects, 'SQLCompilerManager'),
    'plain_manager': (lambda: PlainThing.objects, 'Manager'),
    'raw_queryset': (lambda: Thing.objects.raw('select 1'), 'RawQuerySet'),
    'str': (lambda: 'x', 'str'),
    'none': (lambda: None, 'NoneType'),
}

QUERYSETS = {
    'filtered': lambda: Thing.objects.filter(n__lte=3),
    'none': lambda: Thing.objects.none(),
    'values': lambda: Thing.objects.values('name'),
    'union': lambda: Thing.objects.filter(n__lte=3).union(Thing.objects.filter(n__gte=2)),
}


def test_sql_and_params_is_exported():
    from sql_compiler import sql_and_params
    assert 'sql_and_params' in sql_compiler.__all__
    assert sql_compiler.sql_and_params is sql_compiler.utils.sql_and_params
    assert sql_and_params is sql_compiler.utils.sql_and_params


@pytest.mark.parametrize('case_id', list(REJECTED))
def test_rejects_non_querysets(case_id):
    from sql_compiler import sql_and_params
    factory, name = REJECTED[case_id]
    with pytest.raises(TypeError) as excinfo:
        sql_and_params(factory())
    assert str(excinfo.value) == 'sql_and_params needs a QuerySet, got {}'.format(name)


def test_accepts_plain_manager_queryset():
    from sql_compiler import sql_and_params
    qs = PlainThing.objects.filter(n__lte=3)
    assert type(qs) is QuerySet
    sql, params = qs.query.get_compiler(using=qs.db).as_sql()
    assert sql_and_params(qs) == (sql, tuple(params))


@pytest.mark.parametrize('case_id', list(QUERYSETS))
def test_method_equals_module_function(case_id):
    from sql_compiler import sql_and_params
    qs = QUERYSETS[case_id]()
    assert qs.sql_and_params() == sql_and_params(qs)


def test_pair_is_str_with_placeholders_and_tuple_params():
    from sql_compiler import sql_and_params
    sql, params = sql_and_params(Thing.objects.filter(name="it's"))
    assert isinstance(sql, str)
    assert '%s' in sql
    assert type(params) is tuple
    assert params == ("it's",)
    assert "it's" not in sql


@pytest.mark.parametrize('case_id', ['filtered', 'none'])
def test_pair_matches_the_shared_compile_path(case_id):
    from sql_compiler import sql_and_params
    qs = QUERYSETS[case_id]()
    sql, params = utils.query_sql_and_params(qs.query, qs.db)
    assert sql_and_params(qs) == (sql, tuple(params))


def test_no_backend_gate():
    from sql_compiler import sql_and_params
    sql, params = sql_and_params(Thing.objects.all())
    assert isinstance(sql, str)
    if dbconfig.STATE['default'] == 'sqlite':
        assert connections['default'].connection is None


def test_managers_get_no_sql_and_params():
    assert not hasattr(Thing.objects, 'sql_and_params')
    assert not hasattr(PlainThing.objects, 'sql_and_params')


def test_method_is_not_cached():
    assert inspect.isfunction(SQLCompilerQuerySet.__dict__['sql_and_params'])
    qs = Thing.objects.filter(n__lte=3)
    qs.sql_and_params()
    assert 'sql_and_params' not in qs.__dict__
