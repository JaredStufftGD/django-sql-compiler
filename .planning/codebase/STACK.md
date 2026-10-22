# Technology Stack

**Analysis Date:** 2026-10-22

## Languages

**Primary:**
- Python 3 - All source code in `sql_compiler/` (`sql_compiler/__init__.py`, `sql_compiler/manager.py`, `sql_compiler/queryset.py`, `sql_compiler/utils.py`, `sql_compiler/compilers/*.py`). The package classifiers in `setup.py` declare "Programming Language :: Python :: 3". No specific minimum Python version is declared (no `python_requires`). The IDE project SDK is configured as "Python 3.7 (django-sql-compiler)" in `.idea/misc.xml`.

**Secondary:**
- Markdown - `README.md` (also used as `long_description` in `setup.py`).

## Runtime

**Environment:**
- CPython 3 running inside a consuming Django project. This package is a library and has no standalone entry point.
- Requires an active Django project with `DATABASES` configured, because `executable_query` resolves a live `django.db.connections[...]` alias and executes through a real DB cursor (`sql_compiler/queryset.py`).

**Package Manager:**
- pip / setuptools (build backend implied by `setup.py`; no `pyproject.toml` present)
- Lockfile: Not applicable (library; no `requirements*.txt`, `Pipfile`, `poetry.lock`, or `uv.lock` present)

## Frameworks

**Core:**
- Django (unpinned) - Provides the `Manager` and `QuerySet` base classes that `SQLCompilerManager` (`sql_compiler/manager.py`) and `SQLCompilerQuerySet` (`sql_compiler/queryset.py`) subclass. Also provides `django.db.connections` and `django.utils.functional.cached_property`.

**Testing:**
- Not detected. There is no test directory, no test runner config (pytest, tox, unittest discovery), and no test dependency. The project documentation (`CLAUDE.md`) states that verification requires a live Django project against a supported database.

**Build/Dev:**
- setuptools - `setup.py` uses `setuptools.setup` and `find_packages()`. Build commands per `CLAUDE.md`: `python setup.py sdist bdist_wheel`.
- wheel - Needed for the `bdist_wheel` build target (implied, not declared).
- JetBrains IDE project files - `.idea/` (`.idea/django-sql-compiler.iml`, `.idea/codeStyles/Project.xml`). Gitignored per `.gitignore`, though some files are present in the working tree.

## Key Dependencies

**Critical:**
- `django` (unpinned, `install_requires=['django']` in `setup.py`) - Only declared runtime dependency. The ORM internals used are `Query.sql_with_params()` and `connection.settings_dict['ENGINE']`, so changes across Django versions may affect behavior.

**Database drivers (not declared, required at runtime by the consuming project):**
- `psycopg2` - Required for the PostgreSQL compilers. `PostgresCompiler.compile_sql` in `sql_compiler/compilers/postgresql.py` calls `cursor.mogrify(query, params)`, which is a psycopg2 cursor method. The package does not list it in `install_requires`.
- `mysqlclient` (`MySQLdb`) - Required for the MySQL compiler. `MySQLCompiler` in `sql_compiler/compilers/mysql.py` calls `db.literal(...)` and reads `db.encoding` on the underlying MySQLdb connection. The package does not list it in `install_requires`.
- `django-tenants` - Only needed if the consumer uses the `django_tenants.postgresql_backend` ENGINE, which maps to `PostgresTenantsCompiler` in `sql_compiler/compilers/postgresql.py`. Not declared as a dependency.

**Infrastructure:**
- Not applicable. The package has no network, queue, cache, or storage dependencies.

## Supported Database Engines (ENGINE strings)

Defined in `sql_compiler/compilers/__init__.py` (`compilers` list and derived `compiler_map` / `SUPPORTED_BACKENDS`):

| ENGINE string | Compiler class | File |
|---------------|----------------|------|
| `django.db.backends.mysql` | `MySQLCompiler` | `sql_compiler/compilers/mysql.py` |
| `django.db.backends.postgresql` | `PostgresCompiler` | `sql_compiler/compilers/postgresql.py` |
| `django.db.backends.postgresql_psycopg2` | `Psycopg2Compiler` | `sql_compiler/compilers/postgresql.py` |
| `django_tenants.postgresql_backend` | `PostgresTenantsCompiler` | `sql_compiler/compilers/postgresql.py` |

Note: `README.md` ("Backend Support") lists only `django.db.backends.postgresql` and `django.db.backends.mysql`. The code also accepts `postgresql_psycopg2` and `django_tenants.postgresql_backend`. Keep the README in sync when backends change (per `CLAUDE.md`).

## Configuration

**Environment:**
- No environment variables are read by the package itself.
- No `.env` files are present in the repository.
- Runtime configuration comes entirely from the consuming project's `DATABASES` setting. The package only reads `connection.settings_dict['ENGINE']` to pick a compiler.

**Build:**
- `setup.py` - Package metadata and version. Current declared version: `0.2.3` (`version=` in `setup.py`).
- `.gitignore` - Ignores `.idea/`, `dist/*`, `django_sql_compiler.egg-info/*`, `build/*`.
- `include_package_data=True` and `zip_safe=False` in `setup.py`. No `MANIFEST.in` is present.
- Stale build artifacts exist in the working tree and are gitignored: `dist/django-sql-compiler-0.1.1.tar.gz`, `build/lib/sql_compiler/`, `django_sql_compiler.egg-info/` (PKG-INFO reports version 0.1.1). These do not reflect the current `setup.py` version.

## Platform Requirements

**Development:**
- Python 3 with `django` installed.
- A database driver for the target backend: `psycopg2` for PostgreSQL, or `mysqlclient` for MySQL.
- A running database that matches the consuming project's `DATABASES` configuration. There is no bundled test database or fixture setup.
- Build tools: `setuptools` and `wheel` to produce sdist/wheel artifacts.

**Production:**
- Distributed as a package on PyPI under the name `django-sql-compiler` (import name `sql_compiler`), per `README.md` install instructions and `CLAUDE.md`.
- Source hosted on GitHub: `https://github.com/GrokData/django-sql-compiler` (`url=` in `setup.py`).
- Deployed as a library inside a consuming Django application. It is not a service and has no deployment target of its own.

---

*Stack analysis: 2026-10-22*
