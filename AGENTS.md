# AGENTS.md

This file gives guidance to AI coding agents and contributors working in this repository.

## Project

`django-sql-compiler` is a small reusable Django app (published on PyPI as `django-sql-compiler`, package `sql_compiler`) that turns a Django `QuerySet` into fully interpolated, properly escaped, executable SQL. Users get the SQL via `queryset.executable_query` and embed it in raw SQL (CTEs, subqueries). Unlike `str(qs.query)`, the output is escaped by the database driver.

## Commands

There is a pytest suite in `tests/` that by default needs no database server and no database driver; DB-backed tests in `tests/db/` run against live PostgreSQL and MySQL when configured (see below). GitHub Actions runs the suite on every push to `master` and every pull request (`.github/workflows/ci.yml`, see CI below). There is no linter config yet. The only runtime dependency is Django (>=4.2, Python >=3.10). The package declares no database driver: it uses the connection the consuming project's Django already opened, so the project supplies psycopg2 or mysqlclient.

- Set up the dev environment: `uv sync` (creates `.venv/` at the repo root with Django and the `dev` group, including pytest, from the committed `uv.lock`; use `uv sync --locked` to fail on drift). After editing dependencies or bumping `[project] version` in `pyproject.toml`, run `uv lock` and commit `uv.lock`; CI's lock check (`uv lock --check`) and every `--locked` run fail on a stale lock.
- Run the tests: `uv run pytest` (after `uv sync`). `tests/conftest.py` builds the Django settings from `tests/dbconfig.py`: a live PostgreSQL or MySQL `default` alias when one is configured or reachable, otherwise an unsupported in-memory SQLite alias that never connects (see DB-backed tests below). Tests marked `xfail(strict=True, raises=...)` document known bugs; the DB pins name their issue (GRO-9, GRO-10, GRO-13, GRO-14). When you fix one of those bugs, remove its xfail marker, because a strict xfail that starts passing fails the suite.
- Build a distribution: `uv build` (writes the sdist and wheel to `dist/`, gitignored; the build backend is flit_core and the artifacts contain only `sql_compiler/`)
- Check the artifacts before publishing: `uvx --from "twine>=6.1" twine check --strict dist/*`
- The version is set in `pyproject.toml` (`[project] version`); bump it there when releasing.
- PyCharm: after `uv sync`, go to Settings > Project > Python Interpreter > Add Interpreter > Add Local Interpreter (PyCharm 2024.3+), choose type uv, and select the existing `.venv` (older versions: Virtualenv > Existing). The interpreter is `.venv\Scripts\python.exe` on Windows and `.venv/bin/python` elsewhere. `.idea/` stays gitignored. If imports show as unresolved after a dependency change, re-run `uv sync` and let PyCharm re-index.

The unit suite covers the code that doesn't need a database. End-to-end `executable_query` behavior needs a live connection, because compilation goes through a real DB cursor; those DB-backed tests live in `tests/db/`.

### DB-backed tests

`tests/db/` runs `executable_query` against live PostgreSQL and MySQL. The default suite (`uv run pytest`) needs no server and no driver: with nothing configured the DB tests skip with a reason naming each database.

- Start and stop the databases: `docker compose up -d --wait` (PostgreSQL 18 on 127.0.0.1:55432, MySQL 8.4 with utf8mb4 on 127.0.0.1:53306; throwaway credentials `sqlcompiler`), `docker compose down -v`.
- Environment variables: `SQLCOMPILER_TEST_POSTGRES_URL` (compose value `postgres://sqlcompiler:sqlcompiler@127.0.0.1:55432/sqlcompiler`), `SQLCOMPILER_TEST_MYSQL_URL` (compose value `mysql://sqlcompiler:sqlcompiler@127.0.0.1:53306/sqlcompiler`), and `SQLCOMPILER_TEST_PG_SERVER_SIDE_BINDING=1` (psycopg 3 server-side binding; only valid with --group pg3: with any other driver, or a value other than 1, pytest stops before running tests with a usage error telling you to use `uv run --exact --group pg3 pytest`). Either URL can point at any other server. Query options in either URL (for example `?sslmode=require`) are passed to the driver as connection options, digit-only values as integers; a `#fragment` or a repeated option stops pytest with a usage error. The tests create and drop one table, `sqlcompiler_thing`, in that database.
- Run commands. Set only the variables that run needs. Git Bash/Linux uses inline `VAR=value uv run ...`; PowerShell uses `$env:VAR = '...'` before the command and `Remove-Item Env:VAR` after it.
  - psycopg2: `uv run --exact --group pg2 pytest` (with `SQLCOMPILER_TEST_POSTGRES_URL`)
  - psycopg 3: `uv run --exact --group pg3 pytest` (with `SQLCOMPILER_TEST_POSTGRES_URL`; add `SQLCOMPILER_TEST_PG_SERVER_SIDE_BINDING=1` for the server-side-binding variant)
  - MySQL: `uv run --exact --group mysql pytest` (with `SQLCOMPILER_TEST_MYSQL_URL`)
  - Combined, for the GRO-10 pin: `uv run --exact --group pg2 --group mysql pytest` with both URLs set (the default alias is PostgreSQL, MySQL is alias `other`)
- Why `--exact`: plain `uv run --group X` leaves a previously installed driver in place, and Django loads psycopg 3 whenever it is importable. psycopg2 and psycopg 3 conflict in `[tool.uv]`, and the conftest refuses to start if both are installed. Run `uv sync` afterwards to return to the driver-free environment.
- Selection and skip/fail rule: one database is the `default` alias per pytest process (an explicit env var first, PostgreSQL before MySQL, else a compose default whose driver is installed and imports and which accepts a real driver connection, else SQLite; a driver that fails to import, or a port that answers but cannot complete a connection, such as a container that is still starting, is skipped with a reason). A database whose env var is set is explicitly configured: if it is unreachable or its driver is missing, its tests fail. Otherwise unavailable databases are skipped with a reason naming them, so plain `uv run pytest` stays green. The pytest header line shows which database each run uses. `tests/test_queryset.py` runs only in the no-DB run.
- Expected outcomes: the pg2 and mysql cases pass; the GRO-9 and GRO-13 pins XFAIL on psycopg2 and MySQL; the GRO-10 pin XFAILs only in the combined run. Under psycopg 3 every Postgres case and the GRO-9 pin XFAIL as GRO-14 (TypeError, or AttributeError with server-side binding) and the GRO-10 and GRO-13 pins skip. Expected SQL lives in `tests/db/expected.py` with the versions it was captured on; re-capture it in the same PR when a driver or Django version in `uv.lock` changes. A server patch update under the same compose image tags does not require re-capturing; otherwise re-capture only when CI shows an expected-SQL mismatch.
- Linux: mysqlclient has no Linux wheel, so `--group mysql` builds it and needs `pkg-config`, a C compiler and the MySQL client headers (Debian/Ubuntu: `default-libmysqlclient-dev`). Windows uses wheels.

### CI

`.github/workflows/ci.yml` runs on every push to `master` and every pull request, on Linux runners only (`ubuntu-24.04`). Drivers come only from the uv groups; databases come from `docker-compose.yml` via `docker compose up -d --wait`, so images and server settings match local runs. The MySQL jobs log and assert `character_set_server` utf8mb4 and `collation_server` utf8mb4_0900_ai_ci. Every `astral-sh/setup-uv` step pins the same uv version with `version:`, because that uv runs `uv lock --check` and every `--locked` run; bump all of them together, deliberately.

- Jobs, by exact check name:
  - `Lock file is current`: `uv lock --check`
  - `Build and twine check`: `uv build`, then `twine check --strict`
  - `no-DB 4.2 / 3.10`, `no-DB 4.2 / 3.12`, `no-DB 5.2 / 3.10`, `no-DB 5.2 / 3.14`, `no-DB 6.1 / 3.12`, `no-DB 6.1 / 3.14`: the no-DB suite with that Django line installed over the lock with `--with`; the job asserts the printed Django and Python versions
  - `Django dev (main) / 3.15`: Django's `main` branch; allowed to fail. A failure, including a strict-xfail XPASS, is informational and the run still succeeds
  - `DB pg2`, `DB pg3`, `DB pg3 server-side binding`, `DB mysql`, `DB combined pg2 + mysql`: Python 3.13 with the locked Django and drivers; the URL env vars are set, so an unreachable database fails the job
  - `CI gate`: passes only when every other job except Django dev succeeded
- Per-DB-job outcomes:
  - `DB pg2`: Postgres cases pass; GRO-9 and GRO-13 pins XFAIL; MySQL cases and the GRO-10 pin skip
  - `DB pg3`: Postgres cases and the GRO-9 pin XFAIL as GRO-14 (TypeError); GRO-10 and GRO-13 pins skip; MySQL cases skip
  - `DB pg3 server-side binding`: as pg3, but the GRO-14 XFAILs raise AttributeError
  - `DB mysql`: MySQL cases pass; GRO-9 and GRO-13 pins XFAIL; Postgres cases and the GRO-10 pin skip
  - `DB combined pg2 + mysql`: Postgres cases pass; GRO-9, GRO-10 and GRO-13 pins XFAIL; MySQL cases skip because MySQL is alias `other`
  - `tests/test_queryset.py` skips in every DB job. Each DB job fails on any other skip reason. If these outcomes change, fix the tests or this list, not the CI check.
- Reproduce a job locally (Git Bash/Linux syntax; for the DB variants run `docker compose up -d --wait` first and `uv sync` afterwards):
  - Lock: `uv lock --check`
  - Packaging: `uv build` then `uvx --from "twine>=6.1" twine check --strict dist/*`
  - no-DB, one row each: `uv run --python 3.10 --locked --with "django~=4.2.0" pytest`; `uv run --python 3.12 --locked --with "django~=4.2.0" pytest`; `uv run --python 3.10 --locked --with "django~=5.2.0" pytest`; `uv run --python 3.14 --locked --with "django~=5.2.0" pytest`; `uv run --python 3.12 --locked --with "django~=6.1.0" pytest`; `uv run --python 3.14 --locked --with "django~=6.1.0" pytest`
  - Django dev: `uv run --python 3.15 --locked --with "django @ https://github.com/django/django/archive/refs/heads/main.tar.gz" pytest`
  - pg2: `SQLCOMPILER_TEST_POSTGRES_URL=postgres://sqlcompiler:sqlcompiler@127.0.0.1:55432/sqlcompiler uv run --locked --exact --group pg2 pytest`
  - pg3: `SQLCOMPILER_TEST_POSTGRES_URL=postgres://sqlcompiler:sqlcompiler@127.0.0.1:55432/sqlcompiler uv run --locked --exact --group pg3 pytest`
  - pg3 server-side binding: `SQLCOMPILER_TEST_POSTGRES_URL=postgres://sqlcompiler:sqlcompiler@127.0.0.1:55432/sqlcompiler SQLCOMPILER_TEST_PG_SERVER_SIDE_BINDING=1 uv run --locked --exact --group pg3 pytest`
  - mysql: `SQLCOMPILER_TEST_MYSQL_URL=mysql://sqlcompiler:sqlcompiler@127.0.0.1:53306/sqlcompiler uv run --locked --exact --group mysql pytest`
  - combined: `SQLCOMPILER_TEST_POSTGRES_URL=postgres://sqlcompiler:sqlcompiler@127.0.0.1:55432/sqlcompiler SQLCOMPILER_TEST_MYSQL_URL=mysql://sqlcompiler:sqlcompiler@127.0.0.1:53306/sqlcompiler uv run --locked --exact --group pg2 --group mysql pytest`
- Branch protection (repo owner): in Settings > Branches (or Rules > Rulesets) protect `master`, enable "Require status checks to pass before merging" and add only `CI gate` (GitHub Actions source), not individual matrix jobs and not Django dev; include administrators. The check must have run once (on a pull request) before it can be selected. Because only `CI gate` is required, adding or removing a Django line or Python needs no settings change; a new required job (for example a lint job) must be added to `needs` of the `ci-gate` job in `ci.yml`, and Django dev must never be added.

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
