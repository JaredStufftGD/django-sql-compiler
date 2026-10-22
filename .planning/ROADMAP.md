# Roadmap: django-sql-compiler

## Overview

This milestone takes `django-sql-compiler` from an untested v0.2.3 `setup.py` package to a uv-managed, test-covered library with CI, merged to master. There is no release phase.

Linear project P-GRO-1 is the source of truth. **Each phase tracks exactly one Linear issue** (its `**Linear:**` line). An issue may span several phases, but a phase never covers more than one issue, so GSD always works on one issue at a time, matching `/work`. The rule is checked by `~/.claude/skills/work/check_roadmap.py` (run by `/work` and by this repo's pre-commit hook).

The `/work` skill owns Triage → Needs Spec → Spec Review. At Ready to Work it plans the issue's phases with `/gsd-plan-phase N --prd <spec>`. Success criteria below are **provisional**: they are replaced by the acceptance criteria in the issue's Linear spec.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED). Inserted phases also need exactly one `**Linear:**` issue.

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: uv Packaging** - Move to `pyproject.toml` and uv with driver extras (GRO-6)
- [ ] **Phase 2: Unit Test Harness** - No-DB pytest suite in `tests/` (GRO-5)
- [ ] **Phase 3: DB-backed Test Harness** - End-to-end `executable_query` tests against live PostgreSQL and MySQL (GRO-7)
- [ ] **Phase 4: CI** - GitHub Actions matrix with Postgres and MySQL service containers (GRO-8)
- [ ] **Phase 5: MySQL ProgrammingError** - Param mismatches raise `ProgrammingError`, not `NameError` (GRO-11)
- [ ] **Phase 6: Unsupported-ENGINE Message** - Error names the configured ENGINE (GRO-12)
- [ ] **Phase 7: Routed DB Alias** - Compile with the queryset's alias (GRO-10)
- [ ] **Phase 8: Empty Querysets** - `.none()` returns valid zero-row SQL (GRO-13)
- [ ] **Phase 9: Non-ASCII Decoding** - Decode output with the connection encoding (GRO-9)
- [ ] **Phase 10: psycopg 3** - Support psycopg2 and psycopg 3 (GRO-14)
- [ ] **Phase 11: README** - Supported ENGINEs, drivers, versions, and safe-usage caveats (GRO-15)

## Phase Details

### Phase 1: uv Packaging
**Goal**: A developer can clone the repo, `uv sync`, and `uv build` a correct distribution from `pyproject.toml`
**Depends on**: Nothing (first phase)
**Linear:** GRO-6
**Requirements**: PKG-01, PKG-02, PKG-03, PKG-04, PKG-05
**Success Criteria** (provisional until spec):
  1. `uv build` produces an sdist and wheel named `django-sql-compiler` containing `sql_compiler`, without `tests/`, declaring Python >=3.10 and Django 4.2 / 5.2 / current. `setup.py` is gone and `uv.lock` is committed.
  2. The `[postgres]` and `[mysql]` extras pull in their drivers. A bare install pulls in only Django.
  3. CLAUDE.md and the README describe the uv workflow.
**Plans**: TBD

### Phase 2: Unit Test Harness
**Goal**: A developer can run `uv run pytest` with no database and get meaningful coverage of the non-DB code
**Depends on**: Phase 1 (GRO-6 blocks GRO-5: tests need the dev dependency group)
**Linear:** GRO-5
**Requirements**: TEST-01, TEST-02, TEST-03
**Success Criteria** (provisional until spec):
  1. `uv run pytest` passes from `tests/` on a machine with no database.
  2. Tests cover `bytes_to_string`, `validate_connection`, compiler registration against the documented ENGINE list, and `MySQLCompiler.mogrify` without a real connection.
**Plans**: TBD

### Phase 3: DB-backed Test Harness
**Goal**: A developer can prove against a real database that `executable_query` output executes and returns the same rows as the original queryset
**Depends on**: Phase 2
**Linear:** GRO-7
**Requirements**: DBT-01, DBT-02
**Success Criteria** (provisional until spec):
  1. With DB connection settings provided, the suite runs `executable_query` end to end against PostgreSQL and MySQL. Without them, those tests skip with a clear reason.
  2. The compiled SQL returns the same rows as the queryset for quotes, `%`, `None`, dates, `Decimal`, and non-ASCII values. Cases that hit known bugs are tracked against their GRO issue rather than silently passing or failing.
**Plans**: TBD

### Phase 4: CI
**Goal**: Every push and PR runs the full suite, including DB tests, across the supported Python/Django range
**Depends on**: Phase 3
**Linear:** GRO-8
**Requirements**: CI-01, CI-02, CI-03
**Success Criteria** (provisional until spec):
  1. Pushes and PRs trigger a GitHub Actions run with a visible pass/fail status.
  2. A Python × Django matrix covers Django 4.2, 5.2, and current on Python 3.10+.
  3. DB-backed tests run (not skip) against PostgreSQL and MySQL service containers.
**Plans**: TBD

### Phase 5: MySQL ProgrammingError
**Goal**: A MySQL parameter mismatch surfaces the real error instead of a `NameError`
**Depends on**: Phase 2
**Linear:** GRO-11
**Requirements**: FIX-03
**Success Criteria** (provisional until spec):
  1. A MySQL parameter mismatch raises `ProgrammingError` with the original message.
  2. A test fails without the fix.
**Plans**: TBD

### Phase 6: Unsupported-ENGINE Message
**Goal**: Users on an unsupported database can tell which ENGINE is configured
**Depends on**: Phase 2
**Linear:** GRO-12
**Requirements**: FIX-04
**Success Criteria** (provisional until spec):
  1. An unsupported ENGINE raises an error naming that ENGINE string.
  2. A test fails without the fix.
**Plans**: TBD

### Phase 7: Routed DB Alias
**Goal**: `executable_query` compiles for the database the queryset actually targets
**Depends on**: Phase 3
**Linear:** GRO-10
**Requirements**: FIX-02
**Success Criteria** (provisional until spec):
  1. A queryset routed to a non-default alias gets SQL compiled by that alias's backend, on Django 4.2, 5.2, and current.
  2. A test fails without the fix.
**Plans**: TBD

### Phase 8: Empty Querysets
**Goal**: Empty querysets produce usable SQL instead of an internal exception
**Depends on**: Phase 3
**Linear:** GRO-13
**Requirements**: FIX-05
**Success Criteria** (provisional until spec):
  1. `.none()` and always-empty filters return valid SQL that executes and yields zero rows.
  2. A test fails without the fix.
**Plans**: TBD

### Phase 9: Non-ASCII Decoding
**Goal**: Non-ASCII filter values appear exactly in the output on every backend
**Depends on**: Phase 3
**Linear:** GRO-9
**Requirements**: FIX-01
**Success Criteria** (provisional until spec):
  1. Filtering on `'José'` or `'東京'` produces SQL containing exactly those strings and matching rows on PostgreSQL and MySQL.
  2. A test fails without the fix.
**Plans**: TBD

### Phase 10: psycopg 3
**Goal**: The Postgres compilers work on both psycopg2 and psycopg 3
**Depends on**: Phase 4, Phase 9 (same decode path; CI-04 adds the psycopg 3 leg to the CI matrix)
**Linear:** GRO-14
**Requirements**: PG3-01, PG3-02, PG3-03, CI-04
**Success Criteria** (provisional until spec):
  1. psycopg 3 produces correctly escaped output; psycopg2 still works under all three Postgres ENGINE strings.
  2. An unknown Postgres driver raises a clear error.
  3. CI runs the Postgres tests under both psycopg2 and psycopg 3.
**Plans**: TBD

### Phase 11: README
**Goal**: The README tells users exactly what is supported and how to use the output safely
**Depends on**: Phase 10 (documents final driver behavior)
**Linear:** GRO-15
**Requirements**: DOC-01, DOC-02, DOC-03
**Success Criteria** (provisional until spec):
  1. The README lists all four ENGINE strings, the drivers, and the supported Python/Django range.
  2. The README warns against passing the output with a params argument, uses parameterized `raw(sql, params)` for user input, and notes plaintext values and per-instance caching.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order. Phases 5 and 6 only need Phase 2; phases 7, 8, and 9 only need Phase 3.

| Phase | Linear | Plans Complete | Status | Completed |
|-------|--------|----------------|--------|-----------|
| 1. uv Packaging | GRO-6 | 0/TBD | Not started | - |
| 2. Unit Test Harness | GRO-5 | 0/TBD | Not started | - |
| 3. DB-backed Test Harness | GRO-7 | 0/TBD | Not started | - |
| 4. CI | GRO-8 | 0/TBD | Not started | - |
| 5. MySQL ProgrammingError | GRO-11 | 0/TBD | Not started | - |
| 6. Unsupported-ENGINE Message | GRO-12 | 0/TBD | Not started | - |
| 7. Routed DB Alias | GRO-10 | 0/TBD | Not started | - |
| 8. Empty Querysets | GRO-13 | 0/TBD | Not started | - |
| 9. Non-ASCII Decoding | GRO-9 | 0/TBD | Not started | - |
| 10. psycopg 3 | GRO-14 | 0/TBD | Not started | - |
| 11. README | GRO-15 | 0/TBD | Not started | - |

---
*Roadmap created: 2026-10-22. Re-split 2026-10-22 to one Linear issue per phase, matching `/work`.*
*Milestone ends at merged-to-master; no release phase.*
