# Roadmap: django-sql-compiler

## Overview

This milestone takes `django-sql-compiler` from an untested v0.2.3 `setup.py` package to a uv-managed, test-covered library that has CI. It starts by moving packaging to uv and `pyproject.toml` and adding a no-DB pytest harness (GRO-6 blocks GRO-5). Next comes a DB-backed harness that runs `executable_query` against live PostgreSQL and MySQL. The known correctness bugs and psycopg 3 support are then fixed under that harness, so each fix is proven by a test. The milestone ends with a GitHub Actions matrix using service containers and an accurate README, merged to master. There is no release phase. Linear project P-GRO-1 is the source of truth, and every phase lists the GRO-# issues it covers.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: uv Packaging & Unit Test Harness** - Move to `pyproject.toml` and uv with driver extras, and add a no-DB pytest suite in `tests/`
- [ ] **Phase 2: DB-backed Test Harness** - End-to-end `executable_query` tests against live PostgreSQL and MySQL, skipped when no DB is available
- [ ] **Phase 3: Correctness Fixes & psycopg 3** - Fix the five audited bugs and support psycopg 2 and 3, each proven by tests
- [ ] **Phase 4: CI Matrix & Documentation** - GitHub Actions matrix with DB service containers, plus a README that matches the code

## Phase Details

### Phase 1: uv Packaging & Unit Test Harness
**Goal**: A developer can clone the repo, `uv sync`, run `uv run pytest` with no database, and `uv build` a correct distribution
**Depends on**: Nothing (first phase)
**Linear:** GRO-6, GRO-5 (GRO-6 blocks GRO-5: the tests need the dev dependency group that packaging adds)
**Requirements**: PKG-01, PKG-02, PKG-03, PKG-04, PKG-05, TEST-01, TEST-02, TEST-03
**Success Criteria** (what must be TRUE):
  1. On a fresh clone, `uv sync` followed by `uv build` produces an sdist and a wheel named `django-sql-compiler`. They contain package `sql_compiler`, do not contain `tests/`, and declare `requires-python >=3.10` and a Django range that covers 4.2, 5.2, and current. `setup.py` is gone and `uv.lock` is committed.
  2. `pip install "django-sql-compiler[postgres]"` and `pip install "django-sql-compiler[mysql]"` (from the built wheel) pull in the matching driver. A bare install pulls in only Django.
  3. `uv run pytest` passes from the top-level `tests/` folder on a machine with no database, using a minimal Django settings module.
  4. Unit tests cover `bytes_to_string`, `validate_connection`, compiler registration (`compiler_map` / `SUPPORTED_BACKENDS` equal the documented ENGINE list), and `MySQLCompiler.mogrify` via a stub cursor/connection.
  5. CLAUDE.md and the README dev section describe the uv workflow (sync, test, build) in place of `python setup.py`.
**Plans**: TBD

### Phase 2: DB-backed Test Harness
**Goal**: A developer can prove against a real database that `executable_query` output executes and returns the same rows as the original queryset
**Depends on**: Phase 1
**Linear:** GRO-7
**Requirements**: DBT-01, DBT-02
**Success Criteria** (what must be TRUE):
  1. When PostgreSQL and MySQL connection env vars are set, `uv run pytest` runs end-to-end `executable_query` tests against both databases.
  2. With no DB env vars, or an unreachable DB, those tests are reported as skipped with a clear reason, and the unit suite still passes.
  3. For each backend, the tests run the compiled SQL through a raw cursor and assert that it returns the same rows as the original queryset. Covered values include quotes, `%`, `None`, dates, `Decimal`, and non-ASCII strings.
  4. Cases that hit known bugs (non-ASCII on both backends, `.none()`) are recorded as strict expected failures that name the GRO issue. Phase 3 flips them to passing.
**Plans**: TBD

### Phase 3: Correctness Fixes & psycopg 3
**Goal**: `executable_query` returns SQL exactly as the routed database would execute it, on psycopg2, psycopg 3, and mysqlclient, with clear errors on unsupported paths
**Depends on**: Phase 2
**Linear:** GRO-9, GRO-10, GRO-11, GRO-12, GRO-13, GRO-14
**Requirements**: FIX-01, FIX-02, FIX-03, FIX-04, FIX-05, PG3-01, PG3-02, PG3-03
**Success Criteria** (what must be TRUE):
  1. Filtering on `'José'` or `'東京'` produces SQL that contains exactly those strings and returns the matching rows on PostgreSQL (psycopg2 and psycopg 3) and MySQL. The Phase 2 strict expected failures for non-ASCII now pass.
  2. A queryset routed to a non-default alias with a different vendor than `default` gets SQL compiled by that alias's backend. `.none()` and always-empty filters return valid SQL that executes and yields zero rows.
  3. With psycopg 3 installed, `django.db.backends.postgresql` produces correctly escaped output. The same compiler code path still works under psycopg2 for all three Postgres ENGINE strings. An unrecognized Postgres driver raises a clear error, not `AttributeError`.
  4. A MySQL parameter mismatch raises `ProgrammingError` with the original message, not `NameError`. An unsupported ENGINE raises an error that names the configured ENGINE string.
  5. Each fix above has at least one unit or DB-backed test that fails without the fix. The `compile_sql` bytes contract is either kept or updated in CLAUDE.md alongside the decode change.
**Plans**: TBD

### Phase 4: CI Matrix & Documentation
**Goal**: Every push and PR is verified automatically across the supported Python/Django/driver range, and the README tells users exactly what is supported and how to use the output safely
**Depends on**: Phase 3 (CI-04 needs psycopg 3 support; the README documents the final driver behavior)
**Linear:** GRO-8, GRO-15 (CI-04 also closes out GRO-14 verification)
**Requirements**: CI-01, CI-02, CI-03, CI-04, DOC-01, DOC-02, DOC-03
**Success Criteria** (what must be TRUE):
  1. Opening a PR or pushing to any branch triggers a GitHub Actions run of the full suite, with a visible pass/fail status on the commit.
  2. The workflow runs a Python × Django matrix covering Django 4.2, 5.2, and current on Python 3.10+. The DB-backed tests run (not skip) against PostgreSQL and MySQL service containers.
  3. The Postgres DB tests run under both psycopg2 and psycopg 3 in CI, and both pass.
  4. The README lists all four ENGINE strings, the drivers (psycopg2, psycopg 3, mysqlclient), and the supported Python/Django range.
  5. The README warns against passing `executable_query` output with a params argument (because of `%` in inlined literals), uses parameterized `raw(sql, params)` for user input, and notes that the output contains plaintext values and is cached per queryset instance.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. uv Packaging & Unit Test Harness | 0/TBD | Not started | - |
| 2. DB-backed Test Harness | 0/TBD | Not started | - |
| 3. Correctness Fixes & psycopg 3 | 0/TBD | Not started | - |
| 4. CI Matrix & Documentation | 0/TBD | Not started | - |

---
*Roadmap created: 2026-10-22*
*Milestone ends at merged-to-master; no release phase.*
