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

## Planning (Linear + GSD)

Linear project P-GRO-1 is the roadmap: scope, specs, ordering, and status. The `/work` skill moves issues through Linear and, at Ready to Work, runs either `gsd-quick` or the full GSD phase process for that one issue. Don't pre-plan phases in `.planning/ROADMAP.md`: it is an add-only log that `/work` appends to. There is no REQUIREMENTS.md; the issue's Linear spec is its requirements.

- **Each GSD phase tracks exactly one Linear issue:** one `**Linear:** <ISSUE-ID>` line per phase in `.planning/ROADMAP.md`. An issue may span several phases; a phase never covers several issues, or none. This applies to every phase, including inserted, split, and gap-closure phases. Work with no Linear issue needs one created first (with the user's approval).
- Check with `python ~/.claude/skills/work/check_roadmap.py .planning/ROADMAP.md`. The repo's pre-commit hook runs the same check and blocks commits that break the rule.
- Approved Linear specs win over `.planning/` when they disagree. GSD never changes Linear statuses.
- Quick-path and single-phase issues get one branch and one PR, named with the issue's Linear `gitBranchName`. Multi-phase issues get one branch and one PR per phase, named `<gitBranchName>-phase-<N>`, each cut from up-to-date master after the previous phase's PR merges, so each phase plans against reviewed code.

<!-- GSD:project-start source:PROJECT.md -->
## Project

**django-sql-compiler**

A small reusable Django app (PyPI `django-sql-compiler`, package `sql_compiler`) that turns a Django `QuerySet` into fully interpolated, driver-escaped, executable SQL via `queryset.executable_query`, for embedding ORM-built queries in raw SQL (CTEs, subqueries). This milestone fixes known correctness bugs, adds a real test suite with CI, and modernizes packaging.

**Core Value:** `executable_query` must return SQL that is exactly what the database would execute for that queryset — correctly escaped by the real driver, for the right backend, with no silent data corruption.

### Constraints

- **Compatibility**: Python ≥3.10; Django 4.2 LTS, 5.2 LTS, and current — matches upstream-supported releases
- **Compatibility**: Keep PyPI name `django-sql-compiler`, package `sql_compiler`, and the `executable_query` API unchanged — existing users
- **Tooling**: uv for package management; pytest for tests; GitHub Actions for CI
- **Dependencies**: DB drivers remain optional extras, not hard dependencies
- **Process**: Linear (P-GRO-1) is the source of truth; `compile_sql` must keep returning bytes or the contract in CLAUDE.md must be updated with it
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3 - All source code in `sql_compiler/` (`sql_compiler/__init__.py`, `sql_compiler/manager.py`, `sql_compiler/queryset.py`, `sql_compiler/utils.py`, `sql_compiler/compilers/*.py`). The package classifiers in `setup.py` declare "Programming Language :: Python :: 3". No specific minimum Python version is declared (no `python_requires`). The IDE project SDK is configured as "Python 3.7 (django-sql-compiler)" in `.idea/misc.xml`.
- Markdown - `README.md` (also used as `long_description` in `setup.py`).
## Runtime
- CPython 3 running inside a consuming Django project. This package is a library and has no standalone entry point.
- Requires an active Django project with `DATABASES` configured, because `executable_query` resolves a live `django.db.connections[...]` alias and executes through a real DB cursor (`sql_compiler/queryset.py`).
- pip / setuptools (build backend implied by `setup.py`; no `pyproject.toml` present)
- Lockfile: Not applicable (library; no `requirements*.txt`, `Pipfile`, `poetry.lock`, or `uv.lock` present)
## Frameworks
- Django (unpinned) - Provides the `Manager` and `QuerySet` base classes that `SQLCompilerManager` (`sql_compiler/manager.py`) and `SQLCompilerQuerySet` (`sql_compiler/queryset.py`) subclass. Also provides `django.db.connections` and `django.utils.functional.cached_property`.
- Not detected. There is no test directory, no test runner config (pytest, tox, unittest discovery), and no test dependency. The project documentation (`CLAUDE.md`) states that verification requires a live Django project against a supported database.
- setuptools - `setup.py` uses `setuptools.setup` and `find_packages()`. Build commands per `CLAUDE.md`: `python setup.py sdist bdist_wheel`.
- wheel - Needed for the `bdist_wheel` build target (implied, not declared).
- JetBrains IDE project files - `.idea/` (`.idea/django-sql-compiler.iml`, `.idea/codeStyles/Project.xml`). Gitignored per `.gitignore`, though some files are present in the working tree.
## Key Dependencies
- `django` (unpinned, `install_requires=['django']` in `setup.py`) - Only declared runtime dependency. The ORM internals used are `Query.sql_with_params()` and `connection.settings_dict['ENGINE']`, so changes across Django versions may affect behavior.
- `psycopg2` - Required for the PostgreSQL compilers. `PostgresCompiler.compile_sql` in `sql_compiler/compilers/postgresql.py` calls `cursor.mogrify(query, params)`, which is a psycopg2 cursor method. The package does not list it in `install_requires`.
- `mysqlclient` (`MySQLdb`) - Required for the MySQL compiler. `MySQLCompiler` in `sql_compiler/compilers/mysql.py` calls `db.literal(...)` and reads `db.encoding` on the underlying MySQLdb connection. The package does not list it in `install_requires`.
- `django-tenants` - Only needed if the consumer uses the `django_tenants.postgresql_backend` ENGINE, which maps to `PostgresTenantsCompiler` in `sql_compiler/compilers/postgresql.py`. Not declared as a dependency.
- Not applicable. The package has no network, queue, cache, or storage dependencies.
## Supported Database Engines (ENGINE strings)
| ENGINE string | Compiler class | File |
|---------------|----------------|------|
| `django.db.backends.mysql` | `MySQLCompiler` | `sql_compiler/compilers/mysql.py` |
| `django.db.backends.postgresql` | `PostgresCompiler` | `sql_compiler/compilers/postgresql.py` |
| `django.db.backends.postgresql_psycopg2` | `Psycopg2Compiler` | `sql_compiler/compilers/postgresql.py` |
| `django_tenants.postgresql_backend` | `PostgresTenantsCompiler` | `sql_compiler/compilers/postgresql.py` |
## Configuration
- No environment variables are read by the package itself.
- No `.env` files are present in the repository.
- Runtime configuration comes entirely from the consuming project's `DATABASES` setting. The package only reads `connection.settings_dict['ENGINE']` to pick a compiler.
- `setup.py` - Package metadata and version. Current declared version: `0.2.3` (`version=` in `setup.py`).
- `.gitignore` - Ignores `.idea/`, `dist/*`, `django_sql_compiler.egg-info/*`, `build/*`.
- `include_package_data=True` and `zip_safe=False` in `setup.py`. No `MANIFEST.in` is present.
- Stale build artifacts exist in the working tree and are gitignored: `dist/django-sql-compiler-0.1.1.tar.gz`, `build/lib/sql_compiler/`, `django_sql_compiler.egg-info/` (PKG-INFO reports version 0.1.1). These do not reflect the current `setup.py` version.
## Platform Requirements
- Python 3 with `django` installed.
- A database driver for the target backend: `psycopg2` for PostgreSQL, or `mysqlclient` for MySQL.
- A running database that matches the consuming project's `DATABASES` configuration. There is no bundled test database or fixture setup.
- Build tools: `setuptools` and `wheel` to produce sdist/wheel artifacts.
- Distributed as a package on PyPI under the name `django-sql-compiler` (import name `sql_compiler`), per `README.md` install instructions and `CLAUDE.md`.
- Source hosted on GitHub: `https://github.com/GrokData/django-sql-compiler` (`url=` in `setup.py`).
- Deployed as a library inside a consuming Django application. It is not a service and has no deployment target of its own.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Modules are lowercase, single-word snake_case: `sql_compiler/manager.py`, `sql_compiler/queryset.py`, `sql_compiler/utils.py`, `sql_compiler/compilers/base.py`, `sql_compiler/compilers/postgresql.py`, `sql_compiler/compilers/mysql.py`.
- Each sub-package exposes its public names through `__init__.py` (`sql_compiler/__init__.py`, `sql_compiler/compilers/__init__.py`).
- PascalCase with a consistent `SQL` / `Compiler` / `Manager` / `QuerySet` suffix: `SQLCompilerManager`, `SQLCompilerQuerySet`, `BaseSQLCompiler`, `PostgresCompiler`, `MySQLCompiler`.
- Backend-specific compilers are named after the database they target: `PostgresCompiler`, `PostgresTenantsCompiler` (django_tenants), `Psycopg2Compiler`, `MySQLCompiler`.
- snake_case: `validate_connection`, `bytes_to_string`, `compile_sql`, `executable_query` (`sql_compiler/utils.py`, `sql_compiler/compilers/base.py`, `sql_compiler/queryset.py`).
- Private helpers are not prefixed with an underscore. `mogrify` in `sql_compiler/compilers/mysql.py` is a public method of `MySQLCompiler`.
- snake_case, descriptive: `backend_name`, `compiled_sql`, `compiled_query`, `connection`, `params`.
- Loop variables are short: `compiler`, `key`, `item`, `c`.
- Local variables are reused for transformed values: `query` is reassigned from `str` to `bytes` in `MySQLCompiler.mogrify` (`sql_compiler/compilers/mysql.py`).
- Registry keys are declared as a class attribute named `backend_name` on every compiler: `sql_compiler/compilers/base.py` (default `None`), and overridden in each subclass with the exact Django `ENGINE` string.
- Module-level names are lowercase, not SCREAMING_CASE, even when used as constants: `compilers`, `compiler_map`, `SUPPORTED_BACKENDS` (`sql_compiler/compilers/__init__.py`). `SUPPORTED_BACKENDS` is the one exception to the lowercase rule and is uppercase because it is a public constant.
## Code Style
- No formatter config is committed (no `.editorconfig`, `pyproject.toml`, `black`, or `yapf` config). The code follows PEP 8 style by hand: 4-space indentation, two blank lines between top-level definitions in `sql_compiler/compilers/__init__.py`, one blank line between methods.
- Line length is not enforced. The longest lines are the docstring in `sql_compiler/compilers/postgresql.py` (line 7) and the README examples.
- Quote style is mixed. Single quotes are used in `setup.py`, `sql_compiler/compilers/*.py`, and `sql_compiler/compilers/__init__.py`. Double quotes are used in `sql_compiler/utils.py` (`"".join`) and in docstrings. Pick the quote style of the file you are editing.
- String formatting uses `str.format()` (`sql_compiler/queryset.py` line 21: `'{} backend is not supported.'.format(...)`). Do not introduce f-strings into files that currently use `.format()` without a reason. Both are acceptable in this Python 3 codebase.
- Trailing commas are used in multi-line literals: `sql_compiler/compilers/__init__.py` (`compilers` list, `__all__` list).
- Not configured. No `.flake8`, `.pylintrc`, `ruff.toml`, `.pre-commit-config.yaml`, or CI workflow exists.
- Recommended when editing: keep `python -m pyflakes sql_compiler` clean. The current code has at least one undefined name (see Error Handling below).
- Not used anywhere in the package. Do not add a type-hint style unless it is applied to the whole package.
## Import Organization
- Always relative within the package: `from .base import BaseSQLCompiler` in `sql_compiler/compilers/postgresql.py` and `sql_compiler/compilers/mysql.py`. Do not use absolute `sql_compiler.` imports inside the package.
- Sibling sub-packages are imported as modules: `from . import utils` and `from . import compilers` (`sql_compiler/queryset.py`), so call sites read as `utils.validate_connection(...)` and `compilers.compiler_map[...]`.
- Not applicable. No aliasing configuration exists.
- Public API is re-exported with an explicit `__all__` in each package `__init__.py`. When you add a public class, add it to both the import line and `__all__`.
## Error Handling
- Base class raises `NotImplementedError` with a message naming the missing method: `raise NotImplementedError('Subclasses must implement compile_sql')` (`sql_compiler/compilers/base.py`).
- Unsupported backends are signalled by returning `None`, not by raising, from `validate_connection` (`sql_compiler/utils.py`). The caller in `sql_compiler/queryset.py` (lines 18-21) then raises `NotImplementedError`. Follow this two-step pattern when adding new validation helpers: return `None` from the helper and raise in the caller.
- Driver errors are re-raised under a different type in `MySQLCompiler.mogrify` (`sql_compiler/compilers/mysql.py` lines 28-31): `except TypeError as m: raise ProgrammingError(str(m))`.
- `ProgrammingError` is used in `sql_compiler/compilers/mysql.py` (line 31) but is never imported. The error path raises `NameError` instead. Import it from `MySQLdb` (or the appropriate DB-API module) before relying on this branch.
- In `sql_compiler/queryset.py` line 21, the message is formatted with `str(connection)`, but `connection` is `None` at that point, so the message always reads `None backend is not supported.`. The unsupported ENGINE string is available as `connections[self.db].settings_dict['ENGINE']` and should be used instead.
- Cursors are always acquired with `with connection.cursor() as cursor:` (`sql_compiler/compilers/postgresql.py`, `sql_compiler/compilers/mysql.py`). Do the same for any new driver call.
## Logging
- Do not add logging to the library without discussing it. Errors surface as exceptions to the caller.
## Comments
- Comments are sparse. Explanations of intent live in docstrings. Example: `validate_connection` documents why the check exists ("Since not all back ends provide a method to compile the SQL together with the params...").
- Triple-double-quoted, multi-line, no type or parameter sections (no Sphinx or Google style). Two placements exist:
- Use the second form for functions. Use the first form for classes.
- Docstrings describe behavior and return values in prose: "returns the connection if it's valid, otherwise returns None".
- Not applicable (Python project).
## Function Design
- Compilers take `(self, connection, query, params)` in `compile_sql`. Keep this signature for any new compiler, since `queryset.py` calls it positionally.
- Optional arguments default to `None` and are checked with `is not None` (`mogrify(self, cursor, query, args=None)`).
- Compilers return `bytes`. `SQLCompilerQuerySet.executable_query` always passes the result through `utils.bytes_to_string`, so returning `str` from a compiler will break the `chr()`-based conversion.
- Helpers that can fail to match return `None` implicitly (`validate_connection`). Prefer an explicit `return None` in new code so the intent is visible.
- Expensive, per-queryset results use `django.utils.functional.cached_property` (`sql_compiler/queryset.py`, `executable_query`). New derived values on the queryset should follow the same pattern.
## Class Design
- Backend compilers form a shallow hierarchy: `BaseSQLCompiler` -> `PostgresCompiler` -> (`PostgresTenantsCompiler`, `Psycopg2Compiler`). Subclasses override only `backend_name`, and inherit `compile_sql` (`sql_compiler/compilers/postgresql.py`, lines 19-24).
- `MySQLCompiler` subclasses `BaseSQLCompiler` directly and overrides `compile_sql`.
- To add a backend, subclass `BaseSQLCompiler`, set `backend_name`, and append the class to the `compilers` list in `sql_compiler/compilers/__init__.py`. `compiler_map` and `SUPPORTED_BACKENDS` are derived from that list, so do not edit them directly.
## Module Design
- Explicit `__all__` in every package `__init__.py`.
- Modules do not define `__all__` themselves.
- `sql_compiler/compilers/__init__.py` is a barrel: it imports each compiler class and builds the registry. `sql_compiler/utils.py` imports `SUPPORTED_BACKENDS` from it, so the import graph is `queryset -> compilers`, `utils -> compilers`, and `queryset -> utils`. Do not import `utils` or `queryset` from `compilers/` or it will create a cycle.
- Models opt in by assigning `objects = SQLCompilerManager()` (see `README.md`). `SQLCompilerManager.get_queryset` returns `SQLCompilerQuerySet(self.model, using=self._db)`; keep that constructor shape if you override it.
## Anti-Patterns to Avoid
- Do not return `str` from a compiler's `compile_sql`. It must return `bytes`.
- Do not add a new backend without updating the "Backend Support" section of `README.md`.
- Do not hard-code ENGINE strings outside the compiler `backend_name` attributes.
- Do not catch broad `Exception` in the compile path. Let driver errors propagate.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## System Overview
```text
```
## Component Responsibilities
| Component | Responsibility | File |
|-----------|----------------|------|
| Package facade | Re-exports `SQLCompilerManager` and `SQLCompilerQuerySet` | `sql_compiler/__init__.py` |
| Manager | Subclasses Django `Manager`; `get_queryset()` returns the custom queryset | `sql_compiler/manager.py` |
| QuerySet | Owns `executable_query` (cached property): validate, build SQL+params, compile, decode | `sql_compiler/queryset.py` |
| Connection validation | Checks the connection ENGINE against the supported list; decodes driver bytes to `str` | `sql_compiler/utils.py` |
| Compiler registry | Builds `compilers`, `compiler_map` (ENGINE → class) and `SUPPORTED_BACKENDS` from one list | `sql_compiler/compilers/__init__.py` |
| Base compiler | Defines `backend_name` slot and abstract `compile_sql` | `sql_compiler/compilers/base.py` |
| Postgres compilers | Delegate to psycopg2 `cursor.mogrify`; subclasses only change `backend_name` | `sql_compiler/compilers/postgresql.py` |
| MySQL compiler | Reimplements mogrify with `connection.literal()` and `%` formatting | `sql_compiler/compilers/mysql.py` |
| Packaging | Distribution metadata, version (0.2.3), `find_packages()` | `setup.py` |
## Pattern Overview
- No models, migrations, views, or URLs. `sql_compiler` is a Django-installable app in name only (no `models.py`), used for its manager/queryset.
- Strategy pattern for backends: `BaseSQLCompiler` subclasses are looked up by `connection.settings_dict['ENGINE']`.
- Registry is derived, not hand-maintained twice: `compiler_map` and `SUPPORTED_BACKENDS` are computed from the `compilers` list in `sql_compiler/compilers/__init__.py`.
- Compilers are stateless and instantiated per call (`compiler_map[backend_name]()` in `sql_compiler/queryset.py`).
- The library does not import any DB driver directly. Drivers are reached only through the Django connection's cursor (`connection.cursor()`), so psycopg2 / MySQLdb are the consumer's responsibility.
- Requires a live database connection: compilation executes through a real cursor, so `executable_query` cannot be produced offline.
## Layers
- Purpose: Expose `executable_query` on any `QuerySet` from a model whose manager is `SQLCompilerManager`.
- Location: `sql_compiler/manager.py`, `sql_compiler/queryset.py`
- Contains: `SQLCompilerManager(Manager)`, `SQLCompilerQuerySet(QuerySet)`, `executable_query` cached property.
- Depends on: `django.db.connections`, `django.db.models`, `sql_compiler.utils`, `sql_compiler.compilers`.
- Used by: Consumer code (`MyModel.objects.filter(...).executable_query`).
- Purpose: Connection gating and byte-to-string decoding.
- Location: `sql_compiler/utils.py`
- Contains: `validate_connection(connection)`, `bytes_to_string(bytes_obj)`.
- Depends on: `sql_compiler.compilers.SUPPORTED_BACKENDS`.
- Used by: `sql_compiler/queryset.py`.
- Purpose: Turn `(query_sql, params)` into fully interpolated, escaped SQL as bytes.
- Location: `sql_compiler/compilers/`
- Contains: `base.py` (`BaseSQLCompiler`), `postgresql.py` (`PostgresCompiler`, `PostgresTenantsCompiler`, `Psycopg2Compiler`), `mysql.py` (`MySQLCompiler`), registry in `__init__.py`.
- Depends on: Django connection cursor and, for MySQL, `connection.literal` / `cursor.connection.encoding` from the driver.
- Used by: `SQLCompilerQuerySet.executable_query` only.
- Purpose: Ship the package to PyPI.
- Location: `setup.py`, `README.md` (also used as `long_description`).
- Contains: Metadata, `install_requires=['django']` only.
## Data Flow
### Primary Request Path
### Secondary Flow: Unsupported backend
- No persistent state. The only state is the `cached_property` result on each queryset instance and the module-level `compiler_map` / `SUPPORTED_BACKENDS` constants, which are built once at import time.
## Key Abstractions
- Purpose: Contract for backend-specific SQL rendering.
- Examples: `sql_compiler/compilers/base.py`
- Pattern: Class attribute `backend_name` (the Django ENGINE string) plus instance method `compile_sql(connection, query, params) -> bytes`. Base raises `NotImplementedError`.
- Purpose: Single list of supported backends that drives both dispatch and validation.
- Examples: `sql_compiler/compilers/__init__.py` (`compilers`, `compiler_map`, `SUPPORTED_BACKENDS`)
- Pattern: Dict comprehension keyed by `backend_name`. Duplicate `backend_name` values would silently overwrite each other.
- Purpose: Same mogrify logic under several Django ENGINE strings.
- Examples: `PostgresCompiler` (`django.db.backends.postgresql`), `Psycopg2Compiler` (`django.db.backends.postgresql_psycopg2`), `PostgresTenantsCompiler` (`django_tenants.postgresql_backend`) in `sql_compiler/compilers/postgresql.py`.
- Pattern: Subclass overrides only `backend_name`; no behavior change.
## Entry Points
- Location: `sql_compiler/manager.py` (`SQLCompilerManager`)
- Triggers: Consumer declares `objects = SQLCompilerManager()` on a model (per `README.md`).
- Responsibilities: Returns `SQLCompilerQuerySet` from `get_queryset()`, so all manager-level queries carry the executable property.
- Location: `sql_compiler/queryset.py` (`SQLCompilerQuerySet.executable_query`)
- Triggers: Attribute access on any queryset produced by the manager.
- Responsibilities: Full compile pipeline described in Primary Request Path.
- Location: `sql_compiler/__init__.py`
- Triggers: `from sql_compiler import SQLCompilerManager` (per `README.md`).
- Responsibilities: Re-exports the manager and queryset. Importing it also imports `sql_compiler.compilers`, which builds the registry.
## Architectural Constraints
- **Threading:** No threading or async code. Each `executable_query` call uses `connections[alias]`, which Django keeps thread-local, so concurrent use follows Django's per-thread connection model.
- **Global state:** Module-level registry in `sql_compiler/compilers/__init__.py` (`compilers`, `compiler_map`, `SUPPORTED_BACKENDS`). `SUPPORTED_BACKENDS` is a live `dict_keys` view of `compiler_map`. No mutable state is written after import.
- **Database routing:** `executable_query` validates and executes against `connections[self.db]`, but `self.query.sql_with_params()` is called without a database argument. In Django's `Query` implementation this compiles SQL through the default alias's connection operations (not verified in this repo; Django is not installed in the workspace). Multi-database routing with non-default backends may therefore produce SQL that does not match the executing connection.
- **Driver coupling:** `compilers/mysql.py` and `compilers/postgresql.py` do not import `MySQLdb` or `psycopg2`. They rely on the methods exposed by the live cursor/connection (`mogrify`, `literal`, `encoding`).
- **Return type contract:** `compile_sql` must return `bytes` (or an object iterable of ints), because `utils.bytes_to_string` iterates over the result. A `str` return breaks decoding (see Anti-Patterns).
- **Circular imports:** None. Import order is `queryset` → `utils` → `compilers`; `manager` → `queryset`. `compilers/__init__.py` does not import from the package root.
- **Test suite:** None in the repository. Behavior is verified only against a live Django project (per `CLAUDE.md`).
## Anti-Patterns
### Byte-wise decoding in `bytes_to_string`
### Unimported exception in `MySQLCompiler.mogrify`
### Misleading unsupported-backend error
### Hand-maintained backend list in documentation
## Error Handling
- Unsupported ENGINE: `validate_connection` returns `None`, then `NotImplementedError` in `sql_compiler/queryset.py`.
- Base compiler: `BaseSQLCompiler.compile_sql` raises `NotImplementedError` in `sql_compiler/compilers/base.py`.
- Database errors from `cursor.mogrify` or `literal` propagate unchanged to the caller.
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
