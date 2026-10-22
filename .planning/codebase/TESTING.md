# Testing Patterns

**Analysis Date:** 2026-10-22

## Test Framework

**Runner:**
- None. No test framework is installed, configured, or referenced.
- Config: Not detected. No `pytest.ini`, `tox.ini`, `setup.cfg`, `noxfile.py`, `conftest.py`, or `manage.py` test settings exist in the repository.

**Assertion Library:**
- Not applicable. No test files exist.

**Run Commands:**
```bash
# No test command is defined.
python setup.py sdist bdist_wheel   # Build a distribution (the only documented command, see CLAUDE.md)
```

The project has no test suite. `CLAUDE.md` states that verifying changes requires a Django project with a live connection to a supported database (PostgreSQL via psycopg2, or MySQL via mysqlclient), because compilation goes through a real DB cursor.

## Test File Organization

**Location:**
- No test directory exists. Tracked files (`git ls-files`) contain only the package under `sql_compiler/` plus `setup.py` and `README.md`.

**Naming:**
- Not established. If tests are added, use `tests/` at the repository root with `test_*.py` files, which is the default discovery pattern for pytest and `unittest`.

**Structure:**
```
sql_compiler/            # package under test (no tests here)
tests/                   # does not exist; create if adding tests
  test_utils.py          # would cover bytes_to_string, validate_connection
  test_compilers.py      # would cover compiler_map / SUPPORTED_BACKENDS registration
  test_queryset.py       # would cover executable_query against a live DB
```

Keep tests outside the `sql_compiler` package. `setup.py` uses `find_packages()` with no `exclude`, so a top-level `tests` package with an `__init__.py` would be packaged into the distribution. Either omit `__init__.py` from `tests/` or add `exclude=['tests*']` to `find_packages()` in `setup.py`.

## Test Structure

**Suite Organization:**
Not applicable. No suites exist.

**Patterns:**
- No setup or teardown patterns exist.
- Any new DB-backed test needs a configured Django project (`DATABASES` with an ENGINE listed in `sql_compiler/compilers/__init__.py`). The library has no settings of its own.

## Mocking

**Framework:** None in use. `unittest.mock` is available in the standard library if needed.

**What to Mock:**
- Pure-Python helpers can be tested without a database: `sql_compiler/utils.py` `bytes_to_string` takes bytes and `validate_connection` only reads `connection.settings_dict['ENGINE']`, so a `types.SimpleNamespace(settings_dict={'ENGINE': ...})` stub is enough.
- `MySQLCompiler.mogrify` (`sql_compiler/compilers/mysql.py`) takes a `cursor` whose `.connection` exposes `.encoding` and `.literal(item)`. A stub with those two attributes can exercise the `%s` and `%(name)s` substitution branches without a MySQL server.

**What NOT to Mock:**
- Do not mock the PostgreSQL `cursor.mogrify` path in `sql_compiler/compilers/postgresql.py`. Its only behavior is delegating to psycopg2's escaping, and a stub would test nothing. Use a real connection.
- Do not mock `SQLCompilerQuerySet.query.sql_with_params()` when testing `executable_query`. Build a real queryset against a real database.

## Fixtures and Factories

**Test Data:**
- None exist. For integration checks, a minimal model is sufficient, for example:
```python
from django.db import models
from sql_compiler import SQLCompilerManager


class MyModel(models.Model):
    objects = SQLCompilerManager()
    field_one = models.IntegerField()
    field_two = models.CharField(max_length=200)
```

**Location:**
- Not applicable. If fixtures are added, place them under `tests/fixtures/`.

## Coverage

**Requirements:** None enforced. No coverage tool is configured.

**View Coverage:**
```bash
# Not configured. To add one, install coverage and run against a Django test runner:
coverage run -m pytest tests/ && coverage report -m
```

## Test Types

**Unit Tests:**
- None exist. Good candidates (no DB needed): `bytes_to_string` round-trip for ASCII input, `validate_connection` for supported and unsupported ENGINE strings, `compiler_map` containing every `backend_name` in `compilers`, and `MySQLCompiler.mogrify` with positional and dict args.

**Integration Tests:**
- None exist. The meaningful behavior of this package (escaping by the driver, `executable_query` end-to-end) requires a live PostgreSQL or MySQL connection. Tests should be marked or skipped when the database is unavailable.

**E2E Tests:**
- Not used.

## Known Gaps Relevant to Testing

These defects would be caught by a basic test and should be covered when a suite is added:
- `sql_compiler/compilers/mysql.py` line 31 raises `ProgrammingError`, which is not imported. A test that passes a `TypeError`-producing argument list will surface a `NameError` instead.
- `sql_compiler/queryset.py` line 21 formats the unsupported-backend message with `str(connection)`, which is always `None`. A test for an unsupported ENGINE will show the wrong message.
- `sql_compiler/utils.py` `bytes_to_string` maps each byte with `chr(c)`. This is Latin-1 decoding, not UTF-8. Any non-ASCII query text returned by the driver as UTF-8 bytes will be mojibake. A test with a non-ASCII string literal (for example `'é'`) will expose this.

## Common Patterns

**Async Testing:**
- Not applicable. The package is synchronous.

**Error Testing:**
- No error-testing pattern exists. When adding one, assert the exception type and message, for example with `pytest.raises(NotImplementedError, match=...)` for the unsupported-backend path in `sql_compiler/queryset.py`.

---

*Testing analysis: 2026-10-22*
