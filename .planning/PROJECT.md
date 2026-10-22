# django-sql-compiler

## What This Is

A small reusable Django app (PyPI `django-sql-compiler`, package `sql_compiler`) that turns a Django `QuerySet` into fully interpolated, driver-escaped, executable SQL via `queryset.executable_query`, for embedding ORM-built queries in raw SQL (CTEs, subqueries). This milestone fixes known correctness bugs, adds a real test suite with CI, and modernizes packaging.

## Core Value

`executable_query` must return SQL that is exactly what the database would execute for that queryset — correctly escaped by the real driver, for the right backend, with no silent data corruption.

## Source of Truth

Linear project **"django-sql-compiler modernization"** (P-GRO-1, team Grok Data / GRO, label `django-sql-compiler`) owns scope and status. Every requirement and phase in `.planning/` references its GRO-# issue. New work discovered during planning is drafted as a Linear issue and created only after approval.

## Requirements

### Validated

- ✓ `SQLCompilerManager` / `SQLCompilerQuerySet` expose `executable_query` on any model using the manager — existing
- ✓ PostgreSQL support via psycopg2 `cursor.mogrify` for ENGINEs `django.db.backends.postgresql`, `postgresql_psycopg2`, `django_tenants.postgresql_backend` — existing
- ✓ MySQL support via MySQLdb `literal()` for ENGINE `django.db.backends.mysql` — existing
- ✓ Backend registry: `compilers` list → `compiler_map` / `SUPPORTED_BACKENDS` — existing

### Active

- [ ] Packaging on uv + `pyproject.toml`, Python ≥3.10, Django 4.2/5.2/current, driver extras — GRO-6
- [ ] Pytest suite with no-DB unit tests in top-level `tests/` — GRO-5
- [ ] DB-backed `executable_query` tests against live Postgres and MySQL, skipped without a DB — GRO-7
- [ ] CI (GitHub Actions) running the suite on a Python/Django matrix with Postgres and MySQL service containers — GRO-8
- [ ] Non-ASCII parameters round-trip correctly (decode with connection encoding) — GRO-9
- [ ] SQL compiled with the queryset's DB alias, not the default — GRO-10
- [ ] MySQL param mismatch raises `ProgrammingError`, not `NameError` — GRO-11
- [ ] Unsupported-backend error names the configured ENGINE — GRO-12
- [ ] `.none()` / empty-result querysets return valid zero-row SQL — GRO-13
- [ ] Postgres compilers work with both psycopg2 and psycopg 3 — GRO-14
- [ ] README documents all ENGINEs, drivers, version range, and safe-usage caveats — GRO-15

### Out of Scope

- PyPI release / version bump — milestone ends at merged-to-master; releasing is a later decision
- Automated publish workflow (trusted publishing) — follows the release decision
- New backends (SQLite, Oracle, MSSQL) — not requested; bugs and hardening first
- Django < 4.2 or Python < 3.10 — only currently supported Django releases are targeted
- Escaping `%` → `%%` in output automatically — documented as a caveat (GRO-15) instead of changing output semantics
- Consolidating the duplicated Postgres compiler classes — only if it falls out naturally from GRO-14

## Context

- Brownfield: ~6 source files, v0.2.3, no tests, no CI, no linter. Codebase map in `.planning/codebase/` (see CONCERNS.md for the audit behind GRO-9–GRO-15).
- Compilation goes through a real DB cursor, so meaningful verification needs live Postgres and MySQL; unit tests use stubs where possible.
- Relies on Django internals (`Query.sql_with_params()`, `Manager._db`) that can shift between releases — the CI matrix is the guard.
- psycopg 3 cursors don't expose `mogrify` except `ClientCursor`; driver detection is required.
- Developer environment is Windows; CI is Linux (GitHub Actions).

## Constraints

- **Compatibility**: Python ≥3.10; Django 4.2 LTS, 5.2 LTS, and current — matches upstream-supported releases
- **Compatibility**: Keep PyPI name `django-sql-compiler`, package `sql_compiler`, and the `executable_query` API unchanged — existing users
- **Tooling**: uv for package management; pytest for tests; GitHub Actions for CI
- **Dependencies**: DB drivers remain optional extras, not hard dependencies
- **Process**: Linear (P-GRO-1) is the source of truth; `compile_sql` must keep returning bytes or the contract in CLAUDE.md must be updated with it

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Linear is source of truth; GSD mirrors GRO-# issues | User tracks all work in Linear | — Pending |
| Support both psycopg2 and psycopg 3 | Django 4.2+ users may be on either driver | — Pending |
| Target Django 4.2 / 5.2 / current, Python ≥3.10 | Only upstream-supported releases | — Pending |
| CI runs DB tests against Postgres and MySQL service containers | Driver escaping can only be verified against a real DB | — Pending |
| Milestone done = merged to master, no release | Release decided separately | — Pending |
| Packaging metadata folded into GRO-6 (UV migration) | Same files, same change | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Draft Linear issue, add to Active once created
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-10-22 after initialization*
