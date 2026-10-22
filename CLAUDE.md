# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`django-sql-compiler` is a small reusable Django app (published on PyPI as `django-sql-compiler`, package `sql_compiler`) that turns a Django `QuerySet` into fully interpolated, properly escaped, executable SQL. Users get the SQL via `queryset.executable_query` and embed it in raw SQL (CTEs, subqueries). Unlike `str(qs.query)`, the output is escaped by the database driver.

## Commands

There is no test suite, linter config, or CI. The only dependency is `django` (plus whichever DB driver the consuming project uses: psycopg2 or mysqlclient).

- Build a distribution: `python setup.py sdist bdist_wheel` (outputs to `dist/`, `build/`, `django_sql_compiler.egg-info/`, all gitignored)
- The version is set in `setup.py`; bump it there when releasing.

Verifying changes requires a Django project with a live connection to a supported database, because compilation goes through a real DB cursor.

## Architecture

Request flow: `SQLCompilerManager` (manager.py) → returns `SQLCompilerQuerySet` (queryset.py) → `executable_query` (a `cached_property`) does:

1. `utils.validate_connection` checks that `connections[self.db].settings_dict['ENGINE']` is in `SUPPORTED_BACKENDS`.
2. `self.query.sql_with_params()` produces the parameterized SQL and params.
3. It looks up the compiler class in `compilers.compiler_map` by the ENGINE string, then calls `compile_sql(connection, query, params)`.
4. The result (bytes from the driver) is converted to `str` with `utils.bytes_to_string`.

Compilers (`sql_compiler/compilers/`):
- `BaseSQLCompiler` defines `backend_name` (the exact Django `ENGINE` string) and `compile_sql`.
- The Postgres compilers delegate to psycopg2's `cursor.mogrify`. Subclasses only override `backend_name` so the same logic covers `django.db.backends.postgresql`, `postgresql_psycopg2`, and `django_tenants.postgresql_backend`.
- `MySQLCompiler` has no native mogrify, so it reimplements one using the MySQLdb connection's `literal()` and encodes the query to bytes.

**Adding a backend:** subclass `BaseSQLCompiler`, set `backend_name` to the ENGINE string, and add the class to the `compilers` list in `compilers/__init__.py`. `compiler_map` and `SUPPORTED_BACKENDS` are derived from that list. `compile_sql` must return bytes, because the queryset always runs `bytes_to_string` on the result. Also update the "Backend Support" section of README.md.
