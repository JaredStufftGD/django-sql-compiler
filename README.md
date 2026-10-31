# Django SQL Compiler

[![CI](https://github.com/JaredStufftGD/django-sql-compiler/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/JaredStufftGD/django-sql-compiler/actions/workflows/ci.yml)

Use Django querysets inside raw SQL, safely.

Filter with the ORM, write the rest (CTEs, joins, window functions) by hand. The ORM builds and validates your filters, so user input never has to be pasted into SQL text: every value stays a parameter that the database driver binds, on the queryset's own database. When you need a finished literal SQL string instead (for COPY, CREATE VIEW, logs or another tool), see "Finished literal SQL" under "Choosing an API" below.

## Installation
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

`sql_and_params()`, `compose()` and `fetch_rows()` work on plain Django querysets with no custom manager. `SQLCompilerManager` is only needed for the queryset methods described below (`qs.sql_and_params()` and the finished-literal-SQL property).

## Filter with the ORM, finish in SQL.
The ORM builds and binds the filters. The handwritten SQL joins two independently filtered sets, groups them, filters on the aggregate and ranks the result in one readable statement.

Handwritten SQL is written in the dialect of the database the queryset runs on. This example's SQL runs unchanged on PostgreSQL, SQLite and MySQL 8. It runs on the `default` alias, the queryset's `qs.db`, reported as `leaderboard.alias`.

Models and the result type (no custom manager needed):

```python
import dataclasses
import datetime

from django.db import models
from sql_compiler import compose, fetch_rows


class Customer(models.Model):
    name = models.CharField(max_length=100)
    region = models.CharField(max_length=20)


class Order(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    placed = models.DateField()
    amount_cents = models.IntegerField()


@dataclasses.dataclass
class RegionLeader:
    name: str
    orders: int
    total_cents: int
    place: int
```

Data:

```python
ada = Customer.objects.create(name='Ada', region='west')
bo = Customer.objects.create(name='Bo', region='west')
cy = Customer.objects.create(name='Cy', region='west')
di = Customer.objects.create(name='Di', region='east')

for customer, placed, amount_cents in [
    (ada, datetime.date(2026, 3, 3), 4000),
    (ada, datetime.date(2026, 3, 20), 3000),
    (bo, datetime.date(2026, 3, 10), 9000),
    (bo, datetime.date(2026, 2, 28), 500),
    (cy, datetime.date(2026, 3, 15), 1500),
    (di, datetime.date(2026, 3, 5), 50000),
]:
    Order.objects.create(customer=customer, placed=placed, amount_cents=amount_cents)
```

Query:

```python
region = 'west'                                                     # user input, bound
start, end = datetime.date(2026, 3, 1), datetime.date(2026, 4, 1)   # user input, bound
min_total_cents = 5000                                              # extra value in handwritten SQL, bound

customers = Customer.objects.filter(region=region).values('id', 'name')
orders = Order.objects.filter(placed__gte=start, placed__lt=end).values('customer_id', 'amount_cents')

leaderboard = compose(
    '''
    WITH c AS (%(customers)s), o AS (%(orders)s)
    SELECT c.name AS name,
           COUNT(*) AS orders,
           SUM(o.amount_cents) AS total_cents,
           RANK() OVER (ORDER BY SUM(o.amount_cents) DESC) AS place
    FROM c JOIN o ON o.customer_id = c.id
    GROUP BY c.id, c.name
    HAVING SUM(o.amount_cents) >= %(min_total_cents)s
    ORDER BY place, name
    ''',
    customers=customers,
    orders=orders,
    min_total_cents=min_total_cents,
)
rows = fetch_rows(leaderboard, RegionLeader)   # runs on leaderboard.alias ('default' here)
# [RegionLeader(name='Bo', orders=1, total_cents=9000, place=1),
#  RegionLeader(name='Ada', orders=2, total_cents=7000, place=2)]
```

- `region`, `start`, `end` and `min_total_cents` are all params that the driver binds. Params follow placeholder order: the CTE params first, then the HAVING value. Params are adapted by the backend, so they are not printed here.
- The handwritten SQL references only the CTE names, so no table names are needed.
- Output columns are aliased explicitly in lowercase, because `fetch_rows` matches names exactly.
- The template is trusted SQL written by you, and a literal `%` in it is written `%%`. The package does not validate SQL or make interpolated identifiers safe.

## Choosing an API

### SQL and params
`sql_and_params(queryset)` returns the parameterized SQL (a `str` with Django's `%s` placeholders) and its params (a `tuple`) for any Django queryset. It compiles for the database the queryset runs on (`qs.db`, from `.using()` or your database routers), recompiles on every call, and leaves values in params for the driver to bind.

```python
from django.db import connections
from sql_compiler import sql_and_params

qs = Customer.objects.filter(region='west')
sql, params = sql_and_params(qs)
with connections[qs.db].cursor() as cursor:
    cursor.execute('select count(*) from ({}) a'.format(sql), params)
```

Querysets from `SQLCompilerManager` also have `qs.sql_and_params()`, which returns the same pair. Anything that isn't a QuerySet (a manager, a RawQuerySet) raises `TypeError`.

- The pair is for Django's cursor on that alias (`connections[qs.db].cursor()`), and for `qs.raw(sql, params)` (or `Customer.objects.raw(sql, params, using=qs.db)`), which runs on that alias, when the queryset selects the model's own instances (no `values()`, `values_list()` or aggregates). `Customer.objects.raw(sql, params)` without `using=` runs on the router's or default alias, not `qs.db`. The raw driver cursor is not supported (SQLite's, for example, uses `?`).
- In hand-written SQL around it, keep user input in params and write a literal `%` as `%%`.
- Empty querysets (`.none()`, `filter(id__in=[])`, an empty HAVING, an empty slice such as `qs[5:5]`) return SQL that matches no rows with the same columns.
- Known limitation: an aggregate written as raw SQL (`RawSQL` or `extra(select=...)`, such as `COUNT(*)`) in a queryset with no aggregate Django recognizes has no GROUP BY, so its empty SQL returns one row instead of none.

### Compose
`compose(template, **slots)` fills the `%(name)s` slots of a hand-written SQL template with querysets, earlier `compose()` results and plain values. It returns one result that unpacks as `sql, params` for the querysets' shared database, with params in placeholder order and every value bound by the driver.

```python
from django.db import connections
from sql_compiler import compose

# start comes from the CTE example above
result = compose(
    'WITH recent AS (%(recent)s), big AS (%(big)s) '
    'SELECT recent.id FROM recent JOIN big ON big.id = recent.id WHERE recent.amount_cents > %(min_cents)s',
    recent=Order.objects.filter(placed__gte=start).values('id', 'amount_cents'),
    big=Order.objects.filter(amount_cents__gte=1000).values('id'),
    min_cents=50,
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
- The result is for Django's cursor on `result.alias`, not the raw driver cursor. For `raw()`, use `Order.objects.raw(*result, using=result.alias)`.
- Empty querysets embed SQL that matches no rows, with the same raw-SQL aggregate limitation as `sql_and_params`.

### Typed rows
`fetch_rows(result, row)` runs a `compose()` result and returns the rows as dataclass instances or dicts.

```python
from sql_compiler import fetch_rows

# leaderboard: the compose() result from the CTE example above
dicts = fetch_rows(leaderboard, dict)             # [{'name': 'Bo', 'orders': 1, 'total_cents': 9000, 'place': 1}, ...]
leaders = fetch_rows(leaderboard, RegionLeader)   # [RegionLeader(...), ...]
```

- It runs the result once on `result.alias` through Django's cursor and returns a list (empty when there are no rows). It adds no transaction.
- `row=dict` gives dicts with the columns in select order. `row=<dataclass type>` builds instances by keyword.
- For a dataclass, the column names must match the constructor fields exactly and case-sensitively. Fields with a default or default_factory may be missing. `init=False` fields and ClassVar are not columns.
- Values are passed through exactly as the driver returns them, with no conversion (SQLite returns decimals as float, MySQL returns the SUM of an integer as Decimal, so on MySQL the example's `total_cents` is a `Decimal`), so alias columns explicitly in lowercase.
- Anything but a `compose()` result, or a row kind other than `dict` or a dataclass type, raises `TypeError` before any SQL runs.
- A statement with no result set (it has already run), a result with no columns, duplicate column names, and extra columns or missing fields raise `ValueError`, checked before any row is built.

### Finished literal SQL: executable_query
`executable_query` gives you usable SQL from a QuerySet as one finished string, with every value escaped by the database driver. It is a property of `SQLCompilerQuerySet`, so the model needs `objects = SQLCompilerManager()`.

Casting a queryset's `Query` object with `str(qs.query)` prints out what looks like valid SQL, but Django renders it for display: values are not escaped or quoted by the driver, so it is not actually valid SQL once there are dynamic components (such as filters from user input) in the `QuerySet`.

Use it when a finished literal string is required: COPY, CREATE VIEW, logs, or passing the SQL to another tool. Prefer the parameterized APIs above whenever the SQL can be executed with params.

```python
from django.db import connections, models
from sql_compiler import SQLCompilerManager


class Customer(models.Model):
    objects = SQLCompilerManager()
    name = models.CharField(max_length=100)
    region = models.CharField(max_length=20)


qs = Customer.objects.filter(region='west')
sql = qs.executable_query

with connections[qs.db].cursor() as cursor:
    cursor.execute('CREATE VIEW west_customers AS ' + sql)

west = Customer.objects.raw('SELECT * FROM ({}) a'.format(sql), None, using=qs.db)
```

It works only on the ENGINEs and drivers listed under "Backend and version support"; other backends (for example SQLite) raise `NotImplementedError`. Empty querysets compile to zero-row SQL with the same columns.

- Never supply a params argument when passing its output to `raw()` or `cursor.execute()`: `%` characters in inlined values (any `contains` or `startswith` lookup, or a value like `50% off`) can be interpreted as formatting placeholders. Call `cursor.execute(sql)` with no second argument. With `raw()`, pass `None` explicitly as params (`Customer.objects.raw(sql, None)`), because raw()'s default `()` counts as a params argument at the driver. Handwritten text wrapped around the output must not contain `%s` placeholders either.
- Filter values appear in plaintext in the SQL, so treat it as sensitive data in logs and caches.
- The property is cached per queryset instance (each `.filter()` returns a new queryset), so read it after the queryset is fully built.

### Django's cursor or raw()
- Use `connections[result.alias].cursor()` (or `connections[qs.db]`) with `cursor.execute(*result)` when you need arbitrary columns or aggregates, or `fetch_rows` to get rows as dicts or dataclasses.
- Use `raw(sql, params)` only when the SQL returns the model's own rows, including its primary key.
- Pass `using=` (`result.alias` or `qs.db`) to `raw()`: `Model.objects.raw` without it runs on the router's or default alias.
- Never use the raw driver cursor.

## Backend and version support
The parameterized APIs (`sql_and_params`, `compose`, `fetch_rows`) compile through Django's own backend compiler and work on every Django backend. SQL you write around them can still depend on the backend's features (the CTE example needs CTEs and window functions).

`executable_query` supports exactly these Django `ENGINE` values:

- `django.db.backends.postgresql`
- `django.db.backends.postgresql_psycopg2`: a legacy alias for the PostgreSQL backend that Django removed in Django 3.0. The package still accepts the ENGINE string and maps it to the same compiler.
- `django_tenants.postgresql_backend` (django-tenants)
- `django.db.backends.mysql` (via mysqlclient)

PostgreSQL connections work with psycopg2 and with psycopg 3 (psycopg >=3.2), including Django's `server_side_binding` option. Other PostgreSQL drivers raise `NotImplementedError`.

Python >=3.10 and Django >=4.2 are supported, subject to Django's own Python compatibility for each release. CI tests Django 4.2, 5.2 and 6.1 (on Python 3.10 to 3.14), plus live PostgreSQL 18 (psycopg2, psycopg 3 and psycopg 3 with server-side binding) and MySQL 8.4 jobs, and SQLite in every run. A job against Django's development branch runs for information only and is not a support promise.
