# Goals: {{PROJECT}}

The single place where goals live, so decision and PR volume can be measured against direction instead of activity.

- Goals have stable ids: `G-1`, `G-2`, ...
- Status: **LIVE** (works end to end today), **PARTIAL** (substrate exists, named unlocks remain), **OPEN** (no substrate), **PARKED** (deliberately set down).
- Every new ADR may carry a `**Goals**: G-1, G-2` line, or `**Goals**: none (hygiene)`. An ADR you cannot map to a goal is a signal to pause before writing it.
- `/k-mem:on-track` reads this file, gathers merged work since the last review, reports goals moved, orphan work and pace, then appends to the review log.

## Goals

| ID | Goal | Status | Remaining unlocks | Linked work | Last moved |
|---|---|---|---|---|---|
| G-1 | (first goal) | OPEN | | | {{DATE}} |

## Review log

| Date | Window | PRs | Goals moved | Verdict | Next gauge point |
|---|---|---|---|---|---|
| {{DATE}} | start | 0 | 0 | baseline | first review |
