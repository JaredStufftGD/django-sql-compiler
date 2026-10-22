# django-sql-compiler

## What This Is

A small reusable Django app (PyPI `django-sql-compiler`, package `sql_compiler`) that is pivoting to safe SQL composition for Django querysets: a public `(sql, params)` API compiled for the queryset's own database; `compose()` for embedding several querysets in one hand-written query, with params in placeholder order and every value bound by the driver; and typed result rows. `executable_query` is kept (with fixes) for when a finished literal string is required (COPY, CREATE VIEW, logs, other tools). Work ships in two releases: Release 0.2.0 (correctness fixes plus tests; PyPI latest is still 0.1.1 and an unknown team's CI installs it ~1.7k times/month, so it must not break Postgres users on unpinned installs), then Release 1.0 (composition APIs, psycopg 3, CI, repositioned README).

## Core Value

combining ORM querysets with hand-written SQL must produce exactly what the database would execute — values bound by the real driver (or, for `executable_query`, escaped by it), for the right backend/alias, with no silent data corruption or misaligned params.

## Source of Truth

Linear project **"django-sql-compiler: safe SQL composition"** (P-GRO-1, renamed from "django-sql-compiler modernization"; team Grok Data / GRO, label `django-sql-compiler`; milestones "Release 0.2.0: fixes" and "Release 1.0: composition") is the roadmap: it owns scope, specs, ordering (issue relations), and status. `.planning/` holds no plan of its own. `/work` drives each issue; at Ready to Work it runs either `gsd-quick` or the full GSD phase process for that one issue. New work discovered during planning is drafted as a Linear issue and created only after approval.

## Requirements

### Validated

- ✓ `SQLCompilerManager` / `SQLCompilerQuerySet` expose `executable_query` on any model using the manager — existing
- ✓ PostgreSQL support via psycopg2 `cursor.mogrify` for ENGINEs `django.db.backends.postgresql`, `postgresql_psycopg2`, `django_tenants.postgresql_backend` — existing
- ✓ MySQL support via MySQLdb `literal()` for ENGINE `django.db.backends.mysql` — existing
- ✓ Backend registry: `compilers` list → `compiler_map` / `SUPPORTED_BACKENDS` — existing

### Active

Tracked in Linear (P-GRO-1), not here. Each issue's approved spec is its requirements.

### Out of Scope

- Automated publish workflow (trusted publishing) — decide during GRO-21
- New backends (SQLite, Oracle, MSSQL) for `executable_query` — not requested; the parameterized APIs work on any Django backend
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
| Superseded: two releases instead of a no-release milestone (0.2.0 fixes, 1.0 composition; GRO-21, GRO-22) | Users on unpinned installs need fixes shipped; composition is a separate, larger release | — Pending |
| Packaging metadata folded into GRO-6 (UV migration) | Same files, same change | — Pending |
| Linear is the only roadmap; no pre-planned GSD phases, no REQUIREMENTS.md | Avoid maintaining two roadmaps | — Pending |
| `/work` owns Triage → Spec Review; at Ready to Work it chooses `gsd-quick` or full phases, with the Linear spec as input (never discuss-phase) | One spec process; GSD effort scaled to the issue | — Pending |
| Each phase tracks exactly one GRO issue (an issue may span phases); one branch + PR per issue, or per phase for multi-phase issues (`<gitBranchName>-phase-<N>`, cut from merged master) | GSD works one issue at a time, matching `/work`; enforced by `check_roadmap.py` + pre-commit hook | — Pending |
| Pivot to safe SQL composition instead of sunsetting (2026-10-22) | No package composes querysets into hand-written SQL safely; long-running Django gap (#25705, #21604, #28919); driver binding is safer than interpolation | — Pending |
| Contribute only a public sql_with_params() to Django core (GRO-20); everything else stays in the package | Core rejects executable str(qs.query); big APIs land in core only after a proven package | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Draft a Linear issue (created only after approval)
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-10-22 after the pivot to safe SQL composition*
