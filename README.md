# Django SQL Compiler

[![CI](https://github.com/JaredStufftGD/django-sql-compiler/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/JaredStufftGD/django-sql-compiler/actions/workflows/ci.yml)

A light-weight module to generate usable SQL from a Django QuerySet.

## Backend Support
`django-sql-compiler` supports connections made via these Django `ENGINE` values:

- `django.db.backends.postgresql`
- `django.db.backends.postgresql_psycopg2`: a legacy alias for the PostgreSQL backend that Django removed in Django 3.0. The package still accepts the ENGINE string and maps it to the same compiler.
- `django_tenants.postgresql_backend` (django-tenants)
- `django.db.backends.mysql` (via mysqlclient)

PostgreSQL connections work with psycopg2 and with psycopg 3 (psycopg >=3.2), including Django's `server_side_binding` option. Other PostgreSQL drivers raise `NotImplementedError`.

The ENGINE list applies to `executable_query`. `sql_and_params` (see SQL and params below) works on every Django backend.

## About Django SQL Compiler
The Django ORM is very useful for abstracting away SQL queries from the focus of the developer. This is very useful
for preventing SQL injection attacks and generating queries programmatically using applied logic in your Django app.

However, very complex queries (such as those used in reporting, analytics, or data science projects) can be difficult
or impossible to create with the Django ORM alone. The ORM provides the `.raw` query method and exposes the raw database
`connection` objects which can be used to execute arbitrary SQL against the database. In doing so, we lose the benefit
of the ORM with respect to dynamically adding components to the query (such as filters in a `WHERE` clause) in a way that
prevents injection attacks.

The base Django `QuerySet` object has a `Query` object available at the `.query` property. Casting this `Query` object as a `str`
prints out what looks like a valid SQL query. However, this version of the query is not properly escaped or quoted, meaning
it's not **actually** valid SQL unless there are no dynamic components (such as filters from user input) in the `QuerySet`.

`django-sql-compiler` aims to provide a way to generate clean, usable SQL from a given `QuerySet`, which can be used in
tandem with a raw SQL query to give SQL users more flexibility in querying their Django-connected database while still
retaining the Django ORM for security and dynamic query generation purposes.

## Usage
Install the package:
```
pip install django-sql-compiler
```

No database driver is installed with the package and there are no extras: it uses the database connection your Django project already has, so the driver (for example psycopg2, psycopg 3 or mysqlclient) comes from your existing Django setup.

Add `sql_compiler` to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...,
    'sql_compiler'
]
```

Add the `SQLCompilerManager` to your models:

```python
from django.db import models
from sql_compiler import SQLCompilerManager


class MyModel(models.Model):

    objects = SQLCompilerManager()
    field_one = models.IntegerField()
    field_two = models.CharField(max_length=200)
    field_three = models.DateTimeField()

```

For a given `QuerySet` on the model, you can access the executable query be accessing the `.executable_query` property of the `QuerySet`.

```python
query_set = MyModel.objects.filter(field_one__lte=10)
executable_query = query_set.executable_query
print(executable_query)
```

This query can then be used in another query as a Common Table Expression or Subquery:

```python
# Basic usage
wrapper_query = """select * from ({}) a""".format(executable_query)
new_queryset = MyModel.objects.raw(wrapper_query)

```

While this is a very simple example, you can use this in more complicated queries:
```python

# inside a view
filtered_query_set = MyModel.objects.filter(
    field_one__lte=request.data.get('field_one_filter', 0),
    field_two__in=request.data.get('field_two_filter', [])
    )


more_complex_query = """
select
    RANK() over (partition by a.field_one order by a.field_three desc) as rnk
    ,a.field_one
    ,a.field_two
from
    ({}) a
""".format(filtered_query_set.executable_query)

more_complex_results = MyModel.objects.raw(more_complex_query)
```

Now, users who are more familiar with SQL rather than the Django ORM can use the ORM for security and conveniently
generating SQL queries and use SQL for the rest of their transformations.

## SQL and params
`sql_and_params(queryset)` returns the parameterized SQL (a `str` with Django's `%s` placeholders) and its params (a `tuple`) for any Django queryset. It compiles for the database the queryset runs on (`qs.db`, from `.using()` or your database routers), recompiles on every call, and leaves values in params for the driver to bind.

```python
from django.db import connections
from sql_compiler import sql_and_params

qs = MyModel.objects.filter(field_one__lte=10)
sql, params = sql_and_params(qs)
with connections[qs.db].cursor() as cursor:
    cursor.execute('select count(*) from ({}) a'.format(sql), params)
```

Querysets from `SQLCompilerManager` also have `qs.sql_and_params()`, which returns the same pair. Anything that isn't a QuerySet (a manager, a RawQuerySet) raises `TypeError`.

- The pair is for Django's cursor on that alias (`connections[qs.db].cursor()`), and for `qs.raw(sql, params)` (or `MyModel.objects.raw(sql, params, using=qs.db)`), which runs on that alias, when the queryset selects the model's own instances (no `values()`, `values_list()` or aggregates). `MyModel.objects.raw(sql, params)` without `using=` runs on the router's or default alias, not `qs.db`. The raw driver cursor is not supported (SQLite's, for example, uses `?`).
- In hand-written SQL around it, keep user input in params and write a literal `%` as `%%`.
- Empty querysets (`.none()`, `filter(id__in=[])`, an empty HAVING, an empty slice such as `qs[5:5]`) return SQL that matches no rows with the same columns.
- Known limitation: an aggregate written as raw SQL (`RawSQL` or `extra(select=...)`, such as `COUNT(*)`) in a queryset with no aggregate Django recognizes has no GROUP BY, so its empty SQL returns one row instead of none.
## Compose
`compose(template, **slots)` fills the `%(name)s` slots of a hand-written SQL template with querysets, earlier `compose()` results and plain values. It returns one result that unpacks as `sql, params` for the querysets' shared database, with params in placeholder order and every value bound by the driver.

```python
from django.db import connections
from sql_compiler import compose

result = compose(
    'WITH recent AS (%(recent)s), big AS (%(big)s) '
    'SELECT recent.id FROM recent JOIN big ON big.id = recent.id WHERE recent.total > %(min_total)s',
    recent=Order.objects.filter(created__gte=start).values('id', 'total'),
    big=Order.objects.filter(total__gte=1000).values('id'),
    min_total=50,
)
with connections[result.alias].cursor() as cursor:
    cursor.execute(*result)
    rows = cursor.fetchall()
```

- A QuerySet slot inserts its SQL as `sql_and_params` compiles it, a `compose()` result inserts its SQL (so results nest), and anything else becomes a `%s` param. Lists go to the driver unchanged.
- Write a literal `%` as `%%`. It stays `%%` in the result, also when nested.
- Embedded SQL is inserted as is, without added parentheses, so write them in the template.
- All querysets and nested results must share one alias (`result.alias`), otherwise `ValueError`. At least one slot must hold a queryset or a `compose()` result.
- Missing or unused slots, a positional `%s`, a lone `%` and any other `%(...)` form raise `ValueError` (with the position for `%` problems). A manager, a RawQuerySet, a Query, a Django expression such as `Subquery` and a `Q` raise `TypeError`.
- A tuple (such as a `sql_and_params` pair) raises `TypeError`, because drivers bind tuples differently. Pass the queryset or a `compose()` result instead.
- The template is trusted SQL: never build it from user input. Keep input in slots. A `%(name)s` inside a SQL string literal in the template is still a slot.
- The result is for Django's cursor on `result.alias`, not the raw driver cursor. For `raw()`, use `MyModel.objects.raw(*result, using=result.alias)`.
- Empty querysets embed SQL that matches no rows, with the same raw-SQL aggregate limitation as `sql_and_params`.
