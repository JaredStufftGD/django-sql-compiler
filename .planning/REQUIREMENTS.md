# Requirements: django-sql-compiler

**Defined:** 2026-10-22
**Core Value:** `executable_query` must return SQL that is exactly what the database would execute for that queryset — correctly escaped by the real driver, for the right backend, with no silent data corruption.
**Source of truth:** Linear project P-GRO-1. Each requirement cites its GRO-# issue; Linear owns status.

## v1 Requirements

### Packaging (GRO-6)

- [ ] **PKG-01**: Developer can install, lock, and build the project with uv from a `pyproject.toml` (no `setup.py`); `uv.lock` is committed — GRO-6
- [ ] **PKG-02**: Installing the package declares `requires-python >=3.10` and a Django range covering 4.2 LTS, 5.2 LTS, and current — GRO-6
- [ ] **PKG-03**: User can install driver extras `django-sql-compiler[postgres]` and `django-sql-compiler[mysql]` — GRO-6
- [ ] **PKG-04**: `uv build` produces an sdist and wheel named `django-sql-compiler` containing package `sql_compiler` and excluding `tests/` — GRO-6
- [ ] **PKG-05**: CLAUDE.md and README build/dev instructions describe the uv workflow — GRO-6

### Unit Tests (GRO-5)

- [ ] **TEST-01**: Developer can run `uv run pytest` from a top-level `tests/` folder with a minimal Django settings module and no database — GRO-5
- [ ] **TEST-02**: Unit tests cover `bytes_to_string`/decode, `validate_connection`, and compiler registration (`compiler_map` / `SUPPORTED_BACKENDS` match the documented ENGINE list) — GRO-5
- [ ] **TEST-03**: Unit tests cover `MySQLCompiler.mogrify` using a stub cursor/connection — GRO-5

### DB-backed Tests (GRO-7)

- [ ] **DBT-01**: Developer can run end-to-end `executable_query` tests against live PostgreSQL and MySQL, configured by env vars and skipped cleanly when a DB is unavailable — GRO-7
- [ ] **DBT-02**: DB tests verify the compiled SQL executes and returns the same rows as the original queryset, including driver escaping of quotes, `%`, `None`, dates, `Decimal`, and non-ASCII values — GRO-7

### CI (GRO-8)

- [ ] **CI-01**: Every push and pull request runs the test suite on GitHub Actions — GRO-8
- [ ] **CI-02**: CI runs a Python × Django matrix covering the supported range (Django 4.2 / 5.2 / current, Python 3.10+) — GRO-8
- [ ] **CI-03**: CI runs the DB-backed tests against PostgreSQL and MySQL service containers — GRO-8
- [ ] **CI-04**: CI runs the Postgres tests under both psycopg2 and psycopg 3 — GRO-8, GRO-14

### Bug Fixes

- [ ] **FIX-01**: User filtering on non-ASCII strings (e.g. `'José'`, `'東京'`) gets SQL containing exactly those strings, on both backends — GRO-9
- [ ] **FIX-02**: User calling `executable_query` on a queryset routed to a non-default alias gets SQL compiled by that alias's backend — GRO-10
- [ ] **FIX-03**: User with a MySQL parameter mismatch gets `ProgrammingError` with the original message, not `NameError` — GRO-11
- [ ] **FIX-04**: User on an unsupported ENGINE gets an error naming that ENGINE string — GRO-12
- [ ] **FIX-05**: User calling `executable_query` on `.none()` or an always-empty filter gets valid SQL that returns zero rows — GRO-13

### psycopg 3 (GRO-14)

- [ ] **PG3-01**: User on `django.db.backends.postgresql` with psycopg 3 installed gets correctly escaped `executable_query` output — GRO-14
- [ ] **PG3-02**: The same compiler code path works with psycopg2, under all three Postgres ENGINE strings — GRO-14
- [ ] **PG3-03**: User on an unrecognized Postgres driver gets a clear error rather than an `AttributeError` — GRO-14

### Documentation (GRO-15)

- [ ] **DOC-01**: README lists all supported ENGINE strings, drivers (psycopg2, psycopg 3, mysqlclient), and the supported Python/Django range — GRO-15
- [ ] **DOC-02**: README warns not to pass `executable_query` output with a params argument (`%` in inlined literals) and keeps user input in parameterized `raw(sql, params)` examples — GRO-15
- [ ] **DOC-03**: README notes the output contains plaintext filter values and that `executable_query` is cached per queryset instance — GRO-15

## v2 Requirements

Deferred. Tracked but not in current roadmap. Each needs a Linear issue before it is scheduled.

### Release

- **REL-01**: Version bump and PyPI release of the fixed package
- **REL-02**: Automated PyPI publish on tag via trusted publishing

### Hardening

- **HARD-01**: Verified behavior for `union()`, `distinct(fields)`, `select_for_update()`, and vendor-specific functions
- **HARD-02**: Collapse the duplicated Postgres compiler classes into one class with multiple ENGINE names

## Out of Scope

| Feature | Reason |
|---------|--------|
| New backends (SQLite, Oracle, MSSQL) | Not requested; fix and harden existing backends first |
| Django < 4.2, Python < 3.10 | Only upstream-supported releases are targeted |
| Auto-escaping `%` → `%%` in output | Would change output semantics; documented as caveat instead (DOC-02) |
| PyPI release in this milestone | Milestone ends at merged-to-master |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Linear | Phase | Status |
|-------------|--------|-------|--------|
| PKG-01 | GRO-6 | — | Pending |
| PKG-02 | GRO-6 | — | Pending |
| PKG-03 | GRO-6 | — | Pending |
| PKG-04 | GRO-6 | — | Pending |
| PKG-05 | GRO-6 | — | Pending |
| TEST-01 | GRO-5 | — | Pending |
| TEST-02 | GRO-5 | — | Pending |
| TEST-03 | GRO-5 | — | Pending |
| DBT-01 | GRO-7 | — | Pending |
| DBT-02 | GRO-7 | — | Pending |
| CI-01 | GRO-8 | — | Pending |
| CI-02 | GRO-8 | — | Pending |
| CI-03 | GRO-8 | — | Pending |
| CI-04 | GRO-8 / GRO-14 | — | Pending |
| FIX-01 | GRO-9 | — | Pending |
| FIX-02 | GRO-10 | — | Pending |
| FIX-03 | GRO-11 | — | Pending |
| FIX-04 | GRO-12 | — | Pending |
| FIX-05 | GRO-13 | — | Pending |
| PG3-01 | GRO-14 | — | Pending |
| PG3-02 | GRO-14 | — | Pending |
| PG3-03 | GRO-14 | — | Pending |
| DOC-01 | GRO-15 | — | Pending |
| DOC-02 | GRO-15 | — | Pending |
| DOC-03 | GRO-15 | — | Pending |

**Coverage:**
- v1 requirements: 25 total
- Mapped to phases: 0
- Unmapped: 25 ⚠️ (filled by roadmap)

---
*Requirements defined: 2026-10-22*
*Last updated: 2026-10-22 after initialization*
