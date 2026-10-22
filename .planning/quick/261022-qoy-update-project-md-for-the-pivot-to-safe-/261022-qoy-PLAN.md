---
phase: quick-261022-qoy
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/PROJECT.md
  - CLAUDE.md
autonomous: true
requirements: []
must_haves:
  truths:
    - "PROJECT.md describes the 2026-10-22 pivot to safe SQL composition and the two-release plan"
    - "Core Value covers composition (driver binding, right backend/alias, no misaligned params)"
    - "CLAUDE.md mirrored block matches PROJECT.md What This Is and Core Value; nothing else in CLAUDE.md changes"
  artifacts:
    - path: ".planning/PROJECT.md"
      provides: "Updated project definition"
      contains: "Release 1.0"
    - path: "CLAUDE.md"
      provides: "Mirrored What This Is paragraph and Core Value line"
      contains: "safe SQL composition"
  key_links: []
---

<objective>
Docs-only update of .planning/PROJECT.md and the mirrored block in CLAUDE.md (between `<!-- GSD:project-start source:PROJECT.md -->` and `<!-- GSD:project-end -->`) for the 2026-10-22 pivot. No code changes. Work on master. Linear issue: this is a user-approved doc quick task (no new phase).

Output: edited PROJECT.md and CLAUDE.md.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@CLAUDE.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Update .planning/PROJECT.md</name>
  <files>.planning/PROJECT.md</files>
  <action>
Use Edit for each change; keep everything not listed below untouched.

1. "What This Is" paragraph: keep the existing first sentence's identity (PyPI `django-sql-compiler`, package `sql_compiler`), then state the package is pivoting to safe SQL composition for Django querysets: a public `(sql, params)` API compiled for the queryset's own database; `compose()` (several querysets in one hand-written query, params in placeholder order, the driver binds every value); typed result rows. `executable_query` is kept (with fixes) for when a finished literal string is required (COPY, CREATE VIEW, logs, other tools). Remove the sentence "This milestone fixes known correctness bugs, adds a real test suite with CI, and modernizes packaging." and replace with the two-release plan: Release 0.2.0 (correctness fixes + tests; PyPI latest is still 0.1.1 and an unknown team's CI installs it ~1.7k times/month, so it must not break Postgres users on unpinned installs), then Release 1.0 (composition APIs, psycopg 3, CI, repositioned README). Store this paragraph text in your working notes verbatim; Task 2 reuses it.
2. "Core Value": replace with a line covering composition: combining ORM querysets with hand-written SQL must produce exactly what the database would execute — values bound by the real driver (or, for `executable_query`, escaped by it), for the right backend/alias, with no silent data corruption or misaligned params. Reuse in Task 2.
3. "Source of Truth": change the project name to **"django-sql-compiler: safe SQL composition"** (still P-GRO-1; renamed from "django-sql-compiler modernization") and add that it has milestones "Release 0.2.0: fixes" and "Release 1.0: composition". Keep the rest of the paragraph.
4. "Out of Scope": delete the "PyPI release / version bump" bullet (releases are now in scope: GRO-21, GRO-22). Change "Automated publish workflow (trusted publishing)" reason to "decide during GRO-21". Change the "New backends (SQLite, Oracle, MSSQL)" bullet to say new backends for `executable_query` are out of scope, while the parameterized APIs work on any Django backend. Keep the other bullets unchanged.
5. "Key Decisions": rewrite the "Milestone done = merged to master, no release" row so the decision reads as superseded by two releases (0.2.0 fixes, 1.0 composition), outcome "— Pending" unless the row already differs. Append two rows (outcome "— Pending"): "Pivot to safe SQL composition instead of sunsetting (2026-10-22)" | "No package composes querysets into hand-written SQL safely; long-running Django gap (#25705, #21604, #28919); driver binding is safer than interpolation". And "Contribute only a public sql_with_params() to Django core (GRO-20); everything else stays in the package" | "Core rejects executable str(qs.query); big APIs land in core only after a proven package".
6. Footer line becomes exactly: `*Last updated: 2026-10-22 after the pivot to safe SQL composition*`
  </action>
  <verify>
    <automated>grep -c "Release 1.0" .planning/PROJECT.md && grep -c "safe SQL composition" .planning/PROJECT.md && ! grep -q "PyPI release / version bump" .planning/PROJECT.md && ! grep -q "This milestone fixes" .planning/PROJECT.md && grep -q "Last updated: 2026-10-22 after the pivot to safe SQL composition" .planning/PROJECT.md</automated>
  </verify>
  <done>All six PROJECT.md changes applied; unlisted sections (Requirements Validated/Active, Context, Constraints, Evolution, other Key Decisions rows) unchanged per git diff.</done>
</task>

<task type="auto">
  <name>Task 2: Mirror paragraph and Core Value into CLAUDE.md</name>
  <files>CLAUDE.md</files>
  <action>
Within the GSD:project block only (lines ~43-59), replace the description paragraph (line ~48) and the `**Core Value:**` line (line ~50) with the exact text from PROJECT.md Task 1 (paragraph) and Task 1 item 2 (Core Value, keeping the `**Core Value:**` prefix). Do not touch the Constraints list, the block markers, or any other part of CLAUDE.md.
  </action>
  <verify>
    <automated>git diff --stat CLAUDE.md && git diff -U0 CLAUDE.md | grep -E '^@@' | wc -l && grep -c "safe SQL composition" CLAUDE.md</automated>
  </verify>
  <done>git diff of CLAUDE.md shows changes only on the two mirrored lines (hunks within lines 43-59); text matches PROJECT.md.</done>
</task>

</tasks>

<verification>
Run `git diff --stat`: only .planning/PROJECT.md and CLAUDE.md changed. Run `python ~/.claude/skills/work/check_roadmap.py .planning/ROADMAP.md` (should be unaffected).
</verification>

<success_criteria>
All seven requested changes are present, nothing else was altered, and no source code was modified.
</success_criteria>

<output>
Create `.planning/quick/261022-qoy-update-project-md-for-the-pivot-to-safe-/261022-qoy-SUMMARY.md` when done
</output>
