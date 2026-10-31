# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `fetch_rows(result, row)` runs a `compose()` result once on its alias through Django's cursor and returns a list of rows: dataclass instances (pass the dataclass type; columns are matched to its constructor fields by exact, case-sensitive name, and fields with defaults may be missing) or dicts in select order (pass `dict`), with values exactly as the driver returns them, on every Django backend. Input other than a `ComposeResult`, or a row kind other than `dict` or a dataclass type, raises `TypeError` before any SQL runs; extra columns, missing fields, duplicate column names, a statement with no result set and a result with no columns raise `ValueError`.
- `compose(template, **slots)` (and its result type `ComposeResult`) embeds querysets, earlier `compose()` results and plain values in a hand-written SQL template with `%(name)s` slots and returns `(sql, params)` for the querysets' shared alias (`.alias`), with params in placeholder order and repeated for reused slots, values always bound as params, `%%` kept as a literal `%`, on every Django backend; mixed aliases, missing or unused slots, bad `%` forms, a template with no queryset, and Manager, RawQuerySet, Query, expression, Q or tuple slots raise `ValueError` or `TypeError`.
- `sql_and_params(queryset)` and `SQLCompilerQuerySet.sql_and_params()` return a queryset's parameterized SQL and params (a tuple) compiled for the queryset's own database alias, on every Django backend, for executing through Django's cursor or `raw()` on that alias. Empty querysets return zero-row SQL with the same columns. Anything that isn't a QuerySet raises TypeError.
- psycopg 3 support (psycopg >=3.2) for the PostgreSQL ENGINE strings `django.db.backends.postgresql` and `django_tenants.postgresql_backend`, with Django's default client-side binding and with `OPTIONS={'server_side_binding': True}`. `executable_query` used to raise TypeError or AttributeError under psycopg 3. Values are escaped by psycopg 3 itself, so some literals differ from psycopg2's (for example strings with a backslash render as `E'...'`).

### Changed

- The README and PyPI summary now lead with parameterized composition ("Use Django querysets inside raw SQL, safely.") with one complete CTE example returning typed rows, PyPI keywords were added, and the README's `executable_query` examples no longer pass a params argument (`raw(sql, None)`, `cursor.execute(sql)`), which broke on `%` in inlined values.
- A PostgreSQL connection whose raw connection is neither psycopg2 nor psycopg 3 now raises `NotImplementedError` naming its module and class.

### Fixed

- `executable_query` no longer raises `EmptyResultSet` for querysets Django evaluates as empty (`.none()`, `filter(id__in=[])`, an empty slice such as `qs[5:5]`, an empty HAVING clause, a union of empty parts, a subquery on an empty queryset). It returns SQL that has the same columns as the non-empty queryset and matches no rows, so it can be embedded in a CTE, a UNION or an `IN (...)` subquery. SQL for querysets that already compiled is unchanged. Known limitation: an aggregate written as raw SQL (`RawSQL` or `extra(select=...)`, such as `COUNT(*)`) in a queryset with no aggregate Django recognizes has no GROUP BY, so its empty SQL returns one row instead of none. An empty slice's zero-row SQL has no LIMIT/OFFSET; other sliced querysets keep theirs.

## [0.2.0] - 2026-10-25

The first release since 0.1.1 (June 2021). It ships correctness fixes and first-time MySQL support.

### Added

- MySQL support for `django.db.backends.mysql` (via mysqlclient), contributed in [PR 2](https://github.com/JaredStufftGD/django-sql-compiler/pull/2). It is covered by the live-database test suite and CI. In 0.1.1 the MySQL compiler was a stub and was not registered.

### Fixed

- Non-ASCII parameters are decoded with the connection's encoding instead of byte by byte, so values like `café` are no longer garbled. 0.1.1 corrupted them.
- SQL is compiled for the queryset's own database alias (`.using()` or a database router) instead of the default alias.
- The unsupported-backend error names the ENGINE instead of saying "None backend is not supported".

### Changed

- Decoding is strict. Compiler output that can't be decoded with the connection's codec raises `UnicodeDecodeError` (or `LookupError` for an unknown client encoding) instead of returning garbled text. A Postgres connection on `SQL_ASCII`, or another unusual client encoding, with non-ASCII data now raises where 0.1.1 returned text. A compiler that returns non-bytes raises `TypeError`.
- Semi-public API:
  - `sql_compiler.utils.bytes_to_string` now requires an `encoding` argument.
  - `BaseSQLCompiler` has a new `python_encoding(connection)` method that custom compiler subclasses must implement (the base raises `NotImplementedError`).
  - `MySQLCompiler` is exported from `sql_compiler.compilers`.
- Install requirements: Python >=3.10 and Django >=4.2. The package declares no database driver (psycopg2 or mysqlclient comes from your Django setup). Effects on existing environments:
  - With an older Django installed but not pinned, upgrading django-sql-compiler can upgrade Django (accepted, because Django <4.2 is end-of-life).
  - With Django <4.2 pinned, or on Python <3.10, pip stays on 0.1.1.
  - An install from git master already reports 0.2.3, so pip won't treat 0.2.0 as an upgrade. Install `django-sql-compiler==0.2.0` explicitly.

### Packaging

- Ships a wheel again (0.1.1 was sdist-only; 0.0.5a0 and 0.1.0 had wheels).
- Built with flit_core instead of setuptools.
- The license is declared with PEP 639 `License-Expression: MIT`, and LICENSE ships in both artifacts.
- Metadata-Version 2.5.
- CHANGELOG.md ships in the sdist.

### Known issues

- psycopg 3 is not supported yet. With psycopg 3 installed, Django uses it and `executable_query` raises (planned for 1.0). 0.1.1 had this issue too.
- `.none()` querysets raise `EmptyResultSet` (planned for 1.0). 0.1.1 had this issue too.

[0.2.0]: https://github.com/JaredStufftGD/django-sql-compiler/releases/tag/v0.2.0
