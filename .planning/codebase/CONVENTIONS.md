# Coding Conventions

**Analysis Date:** 2026-10-22

## Naming Patterns

**Files:**
- Modules are lowercase, single-word snake_case: `sql_compiler/manager.py`, `sql_compiler/queryset.py`, `sql_compiler/utils.py`, `sql_compiler/compilers/base.py`, `sql_compiler/compilers/postgresql.py`, `sql_compiler/compilers/mysql.py`.
- Each sub-package exposes its public names through `__init__.py` (`sql_compiler/__init__.py`, `sql_compiler/compilers/__init__.py`).

**Classes:**
- PascalCase with a consistent `SQL` / `Compiler` / `Manager` / `QuerySet` suffix: `SQLCompilerManager`, `SQLCompilerQuerySet`, `BaseSQLCompiler`, `PostgresCompiler`, `MySQLCompiler`.
- Backend-specific compilers are named after the database they target: `PostgresCompiler`, `PostgresTenantsCompiler` (django_tenants), `Psycopg2Compiler`, `MySQLCompiler`.

**Functions and methods:**
- snake_case: `validate_connection`, `bytes_to_string`, `compile_sql`, `executable_query` (`sql_compiler/utils.py`, `sql_compiler/compilers/base.py`, `sql_compiler/queryset.py`).
- Private helpers are not prefixed with an underscore. `mogrify` in `sql_compiler/compilers/mysql.py` is a public method of `MySQLCompiler`.

**Variables:**
- snake_case, descriptive: `backend_name`, `compiled_sql`, `compiled_query`, `connection`, `params`.
- Loop variables are short: `compiler`, `key`, `item`, `c`.
- Local variables are reused for transformed values: `query` is reassigned from `str` to `bytes` in `MySQLCompiler.mogrify` (`sql_compiler/compilers/mysql.py`).

**Class attributes:**
- Registry keys are declared as a class attribute named `backend_name` on every compiler: `sql_compiler/compilers/base.py` (default `None`), and overridden in each subclass with the exact Django `ENGINE` string.

**Constants:**
- Module-level names are lowercase, not SCREAMING_CASE, even when used as constants: `compilers`, `compiler_map`, `SUPPORTED_BACKENDS` (`sql_compiler/compilers/__init__.py`). `SUPPORTED_BACKENDS` is the one exception to the lowercase rule and is uppercase because it is a public constant.

## Code Style

**Formatting:**
- No formatter config is committed (no `.editorconfig`, `pyproject.toml`, `black`, or `yapf` config). The code follows PEP 8 style by hand: 4-space indentation, two blank lines between top-level definitions in `sql_compiler/compilers/__init__.py`, one blank line between methods.
- Line length is not enforced. The longest lines are the docstring in `sql_compiler/compilers/postgresql.py` (line 7) and the README examples.
- Quote style is mixed. Single quotes are used in `setup.py`, `sql_compiler/compilers/*.py`, and `sql_compiler/compilers/__init__.py`. Double quotes are used in `sql_compiler/utils.py` (`"".join`) and in docstrings. Pick the quote style of the file you are editing.
- String formatting uses `str.format()` (`sql_compiler/queryset.py` line 21: `'{} backend is not supported.'.format(...)`). Do not introduce f-strings into files that currently use `.format()` without a reason. Both are acceptable in this Python 3 codebase.
- Trailing commas are used in multi-line literals: `sql_compiler/compilers/__init__.py` (`compilers` list, `__all__` list).

**Linting:**
- Not configured. No `.flake8`, `.pylintrc`, `ruff.toml`, `.pre-commit-config.yaml`, or CI workflow exists.
- Recommended when editing: keep `python -m pyflakes sql_compiler` clean. The current code has at least one undefined name (see Error Handling below).

**Type hints:**
- Not used anywhere in the package. Do not add a type-hint style unless it is applied to the whole package.

## Import Organization

**Order (as observed):**
1. Django imports (`from django.db import connections`, `from django.db.models import Manager`, `from django.utils.functional import cached_property`).
2. Package-relative imports (`from . import utils`, `from . import compilers`, `from .queryset import SQLCompilerQuerySet`).

There is no blank line separating the groups in `sql_compiler/queryset.py`. Keep Django imports first and relative imports after them.

**Relative vs absolute:**
- Always relative within the package: `from .base import BaseSQLCompiler` in `sql_compiler/compilers/postgresql.py` and `sql_compiler/compilers/mysql.py`. Do not use absolute `sql_compiler.` imports inside the package.
- Sibling sub-packages are imported as modules: `from . import utils` and `from . import compilers` (`sql_compiler/queryset.py`), so call sites read as `utils.validate_connection(...)` and `compilers.compiler_map[...]`.

**Path Aliases:**
- Not applicable. No aliasing configuration exists.

**Re-exports:**
- Public API is re-exported with an explicit `__all__` in each package `__init__.py`. When you add a public class, add it to both the import line and `__all__`.

## Error Handling

**Patterns observed:**
- Base class raises `NotImplementedError` with a message naming the missing method: `raise NotImplementedError('Subclasses must implement compile_sql')` (`sql_compiler/compilers/base.py`).
- Unsupported backends are signalled by returning `None`, not by raising, from `validate_connection` (`sql_compiler/utils.py`). The caller in `sql_compiler/queryset.py` (lines 18-21) then raises `NotImplementedError`. Follow this two-step pattern when adding new validation helpers: return `None` from the helper and raise in the caller.
- Driver errors are re-raised under a different type in `MySQLCompiler.mogrify` (`sql_compiler/compilers/mysql.py` lines 28-31): `except TypeError as m: raise ProgrammingError(str(m))`.

**Known defects in these patterns (do not copy):**
- `ProgrammingError` is used in `sql_compiler/compilers/mysql.py` (line 31) but is never imported. The error path raises `NameError` instead. Import it from `MySQLdb` (or the appropriate DB-API module) before relying on this branch.
- In `sql_compiler/queryset.py` line 21, the message is formatted with `str(connection)`, but `connection` is `None` at that point, so the message always reads `None backend is not supported.`. The unsupported ENGINE string is available as `connections[self.db].settings_dict['ENGINE']` and should be used instead.

**Cursor usage:**
- Cursors are always acquired with `with connection.cursor() as cursor:` (`sql_compiler/compilers/postgresql.py`, `sql_compiler/compilers/mysql.py`). Do the same for any new driver call.

## Logging

**Framework:** None. The package does not import `logging` or `print`.

**Patterns:**
- Do not add logging to the library without discussing it. Errors surface as exceptions to the caller.

## Comments

**When to Comment:**
- Comments are sparse. Explanations of intent live in docstrings. Example: `validate_connection` documents why the check exists ("Since not all back ends provide a method to compile the SQL together with the params...").

**Docstrings:**
- Triple-double-quoted, multi-line, no type or parameter sections (no Sphinx or Google style). Two placements exist:
  - Class docstring directly after the `class` line, followed by a blank line before the next attribute: `sql_compiler/compilers/postgresql.py` (`PostgresCompiler`), `sql_compiler/manager.py` (`SQLCompilerManager`).
  - Function docstring with a blank line before the text: `sql_compiler/queryset.py` (`executable_query`), `sql_compiler/utils.py` (`validate_connection`, `bytes_to_string`).
- Use the second form for functions. Use the first form for classes.
- Docstrings describe behavior and return values in prose: "returns the connection if it's valid, otherwise returns None".

**JSDoc/TSDoc:**
- Not applicable (Python project).

## Function Design

**Size:** Functions are short, typically under 15 lines (`sql_compiler/utils.py`, `sql_compiler/compilers/postgresql.py`). `MySQLCompiler.mogrify` (~20 lines) is the longest function in the package and is the one to split first if it grows.

**Parameters:**
- Compilers take `(self, connection, query, params)` in `compile_sql`. Keep this signature for any new compiler, since `queryset.py` calls it positionally.
- Optional arguments default to `None` and are checked with `is not None` (`mogrify(self, cursor, query, args=None)`).

**Return Values:**
- Compilers return `bytes`. `SQLCompilerQuerySet.executable_query` always passes the result through `utils.bytes_to_string`, so returning `str` from a compiler will break the `chr()`-based conversion.
- Helpers that can fail to match return `None` implicitly (`validate_connection`). Prefer an explicit `return None` in new code so the intent is visible.

**Properties:**
- Expensive, per-queryset results use `django.utils.functional.cached_property` (`sql_compiler/queryset.py`, `executable_query`). New derived values on the queryset should follow the same pattern.

## Class Design

**Inheritance:**
- Backend compilers form a shallow hierarchy: `BaseSQLCompiler` -> `PostgresCompiler` -> (`PostgresTenantsCompiler`, `Psycopg2Compiler`). Subclasses override only `backend_name`, and inherit `compile_sql` (`sql_compiler/compilers/postgresql.py`, lines 19-24).
- `MySQLCompiler` subclasses `BaseSQLCompiler` directly and overrides `compile_sql`.

**Registration:**
- To add a backend, subclass `BaseSQLCompiler`, set `backend_name`, and append the class to the `compilers` list in `sql_compiler/compilers/__init__.py`. `compiler_map` and `SUPPORTED_BACKENDS` are derived from that list, so do not edit them directly.

## Module Design

**Exports:**
- Explicit `__all__` in every package `__init__.py`.
- Modules do not define `__all__` themselves.

**Barrel Files:**
- `sql_compiler/compilers/__init__.py` is a barrel: it imports each compiler class and builds the registry. `sql_compiler/utils.py` imports `SUPPORTED_BACKENDS` from it, so the import graph is `queryset -> compilers`, `utils -> compilers`, and `queryset -> utils`. Do not import `utils` or `queryset` from `compilers/` or it will create a cycle.

**Model integration:**
- Models opt in by assigning `objects = SQLCompilerManager()` (see `README.md`). `SQLCompilerManager.get_queryset` returns `SQLCompilerQuerySet(self.model, using=self._db)`; keep that constructor shape if you override it.

## Anti-Patterns to Avoid

- Do not return `str` from a compiler's `compile_sql`. It must return `bytes`.
- Do not add a new backend without updating the "Backend Support" section of `README.md`.
- Do not hard-code ENGINE strings outside the compiler `backend_name` attributes.
- Do not catch broad `Exception` in the compile path. Let driver errors propagate.

---

*Convention analysis: 2026-10-22*
