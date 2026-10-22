---
phase: quick-261022-pgb
plan: 01
type: execute
wave: 1
depends_on: []
files_modified: [CLAUDE.md, .planning/PROJECT.md, .planning/STATE.md]
autonomous: true
requirements: []
must_haves:
  truths:
    - "CLAUDE.md line 41 states the per-phase branching rule"
    - "PROJECT.md decision row keeps its 3 columns, only branch/PR wording changed"
    - "STATE.md Config bullet describes the per-phase branch naming"
    - "No other lines in any file changed"
  artifacts:
    - path: "CLAUDE.md"
      provides: "branching rule"
      contains: "-phase-<N>"
---

<objective>
Docs-only: update the branching rule to match the revised /work skill. Quick-path and single-phase issues: one branch + one PR named with the Linear `gitBranchName`. Multi-phase issues: one branch + one PR per phase, named `<gitBranchName>-phase-<N>`, each cut from up-to-date master after the previous phase's PR merges (so each phase plans against reviewed code).
Output: exactly three edited lines. No code changes. Work on master.
</objective>

<context>
@CLAUDE.md
@.planning/PROJECT.md
@.planning/STATE.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Edit the three branching-rule lines</name>
  <files>CLAUDE.md, .planning/PROJECT.md, .planning/STATE.md</files>
  <action>
Use the Edit tool; each replacement is a single line. Do not touch any other line.

1. CLAUDE.md line 41, currently "- One branch and one PR per issue, named with the issue's Linear `gitBranchName`." Replace with a bullet stating: quick-path and single-phase issues get one branch and one PR named with the issue's Linear `gitBranchName`; multi-phase issues get one branch and one PR per phase, named `<gitBranchName>-phase-<N>`, each cut from up-to-date master after the previous phase's PR merges, so each phase plans against reviewed code. Keep it on one line.

2. .planning/PROJECT.md line 65 (decision table row). In the first (decision) cell only, replace the trailing "one branch + PR per issue" with wording such as "one branch + PR per issue, or per phase for multi-phase issues (`<gitBranchName>-phase-<N>`, cut from merged master)". Leave the rationale cell and the "— Pending" cell and the pipes unchanged so the table keeps 3 columns.

3. .planning/STATE.md line 59, the "[Config]: git.branching_strategy = none; ..." bullet. Replace the clause "giving one branch and one PR per issue" so it says `/work` checks out the issue's Linear branch (`gitBranchName`) for quick-path and single-phase issues (one branch, one PR), and for multi-phase issues one branch and PR per phase named `<gitBranchName>-phase-<N>`, each cut from up-to-date master after the previous phase's PR merges. Keep "git.branching_strategy = none" at the start and "git.base_branch = master." at the end.
  </action>
  <verify>
    <automated>cd /s/Grok/Internal/Git/django-sql-compiler && git diff --numstat && test "$(git diff --numstat | awk '{a+=$1; d+=$2} END {print a" "d}')" = "3 3" && grep -c -e '-phase-<N>' CLAUDE.md .planning/PROJECT.md .planning/STATE.md && sed -n 65p .planning/PROJECT.md | awk -F'|' '{print NF}'</automated>
  </verify>
  <done>Diff shows exactly 3 lines added and 3 removed across the three files; each contains `-phase-<N>`; PROJECT.md row still has the same column count (5 fields from awk, i.e. 3 columns).</done>
</task>

</tasks>

<verification>
git diff touches only the three listed files, one line each.
</verification>

<success_criteria>
Three lines updated per the revised /work branching rule; no code or other doc changes.
</success_criteria>

<output>
Create `.planning/quick/261022-pgb-update-branching-rule-docs-for-per-phase/261022-pgb-SUMMARY.md` when done
</output>
