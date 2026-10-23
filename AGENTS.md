# AGENTS.md

This file gives guidance to AI coding agents and contributors working in this repository.

## Project

`django-sql-compiler` is a small reusable Django app (published on PyPI as `django-sql-compiler`, package `sql_compiler`) that turns a Django `QuerySet` into fully interpolated, properly escaped, executable SQL. Users get the SQL via `queryset.executable_query` and embed it in raw SQL (CTEs, subqueries). Unlike `str(qs.query)`, the output is escaped by the database driver.

## Commands

There is no test suite, linter config, or CI. The only runtime dependency is Django (>=4.2, Python >=3.10). The package declares no database driver: it uses the connection the consuming project's Django already opened, so the project supplies psycopg2 or mysqlclient.

- Set up the dev environment: `uv sync` (creates `.venv/` at the repo root with Django and the `dev` group, including pytest, from the committed `uv.lock`; use `uv sync --locked` to fail on drift). After editing dependencies in `pyproject.toml`, run `uv lock` and commit `uv.lock`.
- Build a distribution: `uv build` (writes the sdist and wheel to `dist/`, gitignored; the build backend is flit_core and the artifacts contain only `sql_compiler/`)
- Check the artifacts before publishing: `uvx --from "twine>=6.1" twine check --strict dist/*`
- The version is set in `pyproject.toml` (`[project] version`); bump it there when releasing.
- PyCharm: after `uv sync`, go to Settings > Project > Python Interpreter > Add Interpreter > Add Local Interpreter (PyCharm 2024.3+), choose type uv, and select the existing `.venv` (older versions: Virtualenv > Existing). The interpreter is `.venv\Scripts\python.exe` on Windows and `.venv/bin/python` elsewhere. `.idea/` stays gitignored. If imports show as unresolved after a dependency change, re-run `uv sync` and let PyCharm re-index.

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

## Conventions

- Relative imports inside the package (`from .base import BaseSQLCompiler`); import sibling modules as modules (`from . import utils`). Don't import `utils` or `queryset` from `compilers/` (import cycle).
- Public names go in each package `__init__.py`'s explicit `__all__`.
- `compile_sql(self, connection, query, params)` keeps that positional signature and must return bytes.
- Match the quote style and string formatting of the file you're editing; no type hints unless applied package-wide.
- Acquire cursors with `with connection.cursor() as cursor:`; let driver errors propagate (no broad `except Exception`); unsupported-backend helpers return `None` and the caller raises.
- Don't hard-code ENGINE strings outside compiler `backend_name` attributes; update README "Backend Support" when adding a backend.
- Don't add logging without discussing it.
