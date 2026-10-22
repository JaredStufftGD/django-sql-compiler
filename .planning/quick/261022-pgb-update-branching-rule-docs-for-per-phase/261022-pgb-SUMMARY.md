# Quick 261022-pgb: Per-phase branching rule docs

Updated the branching rule in CLAUDE.md (line 41), .planning/PROJECT.md (line 65) and .planning/STATE.md (line 59): single-phase/quick issues use `gitBranchName`; multi-phase issues use one branch + PR per phase named `<gitBranchName>-phase-<N>`, cut from merged master.

Deviations: none. Diff is exactly 3 lines changed in 3 files; PROJECT.md table keeps 3 columns.
