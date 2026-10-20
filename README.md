# Django SQL Compiler

A light-weight module to generate usable SQL from a Django QuerySet.

## Backend Support
Currently, `django-sql-compiler` only supports connections made via the `django.db.backends.postgresql` and `django.db.backends.mysql` backends.

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
