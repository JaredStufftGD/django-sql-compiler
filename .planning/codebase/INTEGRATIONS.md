# External Integrations

**Analysis Date:** 2026-10-22

## APIs & External Services

**Third-party APIs:**
- None detected. The package makes no HTTP, gRPC, or other network calls. Searches for SDK imports (`requests`, `httpx`, `boto3`, `stripe`, `supabase`, and similar) in `sql_compiler/` found nothing.

## Data Storage

**Databases:**
- The only external system the package touches is the consuming project's relational database, accessed through Django's connection layer (`django.db.connections`, used in `sql_compiler/queryset.py`).
  - PostgreSQL
    - Engines: `django.db.backends.postgresql`, `django.db.backends.postgresql_psycopg2`, `django_tenants.postgresql_backend`
    - Compiler: `sql_compiler/compilers/postgresql.py` (`PostgresCompiler`, `Psycopg2Compiler`, `PostgresTenantsCompiler`)
    - Client: psycopg2 cursor `mogrify()` (not declared as a dependency)
  - MySQL
    - Engine: `django.db.backends.mysql`
    - Compiler: `sql_compiler/compilers/mysql.py` (`MySQLCompiler`)
    - Client: MySQLdb connection `literal()` and `encoding` (`mysqlclient`, not declared as a dependency)
- Connection configuration: the consuming project's `DATABASES` setting in its Django `settings.py`. The package reads only `connection.settings_dict['ENGINE']`. Credentials are not read or stored by this package.
- The package only compiles SQL and does not execute the resulting query. The mogrify step runs against the live cursor, but it only produces a string and does not run the user query.

**File Storage:**
- Local filesystem only for packaging artifacts (`dist/`, `build/`). The runtime package does not read or write files.

**Caching:**
- None. `executable_query` is a `cached_property` on the queryset instance (`sql_compiler/queryset.py`), which is per-instance in-memory caching only and not an external cache.

## Authentication & Identity

**Auth Provider:**
- Not applicable. The package does not authenticate users. It relies on the consuming project's configured database credentials for the connection it compiles against.

## Monitoring & Observability

**Error Tracking:**
- None.

**Logs:**
- None. The package does not log. Errors are raised as exceptions:
  - `NotImplementedError` in `sql_compiler/queryset.py` when the ENGINE is not supported.
  - `NotImplementedError` from `BaseSQLCompiler.compile_sql` in `sql_compiler/compilers/base.py` if a subclass does not implement it.

## CI/CD & Deployment

**Hosting:**
- PyPI for distribution (package name `django-sql-compiler`), per `README.md` and `CLAUDE.md`.
- GitHub repository: `https://github.com/GrokData/django-sql-compiler` (`setup.py`). The git log shows merges from a `fifthlane/master` fork (`601985e`).

**CI Pipeline:**
- None detected. No `.github/workflows/`, `.gitlab-ci.yml`, `tox.ini`, or similar CI config is present in the repository.

**Release process:**
- Manual. Version is bumped in `setup.py`, then `python setup.py sdist bdist_wheel` is run (per `CLAUDE.md`). No publish script is present in the repo.

## Environment Configuration

**Required env vars:**
- None read by the package.
- The consuming project's database settings (host, name, user, password, engine) are required at runtime, but they are defined in the consumer's Django settings and not in this repository.

**Secrets location:**
- Not applicable to this repository. No `.env` files or secret files are present in the working tree.

## Webhooks & Callbacks

**Incoming:**
- None.

**Outgoing:**
- None.

## Integration Notes

- The supported ENGINE list is a hardcoded mapping in `sql_compiler/compilers/__init__.py`. Adding a new database integration means adding a `BaseSQLCompiler` subclass and listing it in the `compilers` list there (see `CLAUDE.md`).
- `sql_compiler/compilers/mysql.py` calls `ProgrammingError(str(m))` in `mogrify()` but does not import `ProgrammingError`. The `TypeError` path would raise `NameError` instead of the intended exception. This affects the MySQL integration's error path only.
- `django_tenants.postgresql_backend` is supported by ENGINE string only. The `django-tenants` package is not a declared dependency and is not imported by this code.

---

*Integration audit: 2026-10-22*
