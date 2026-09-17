---
description: Goal-alignment gauge. Compares ADR and PR flow since the last review against docs/project_notes/goals.md and reports goals moved, orphan work, and pace.
---

Answer one question for a solo operator deep in ADR and PR volume: **are we still moving toward the goals, or just moving?** `/k-mem:portfolio` shows the work; this shows the direction.

## Steps

1. Read `docs/project_notes/goals.md`. Note the date of the last entry in the Review log; that is the review window start `D`. If the file is missing, `kmem init` creates it; fill in the goals first and stop.

2. Gather merged work since `D` (run in parallel):
   - `git log --since=<D> --oneline --merges` in this repo and in every repo a goal's "Linked work" names (paths from the K-mem config).
   - DevFlow's `get_status_report` when DevFlow is installed, filtered to the configured repos.

3. Find ADRs written since `D`: grep `**Date**:` lines in `docs/project_notes/decisions/*.md` (or `decisions.md` in the single-file layout) and keep those dated after `D`. For each, check for a `**Goals**:` line.

4. Judge movement from evidence, not ticket status alone:
   - **Goals moved**: a goal whose status or "remaining unlocks" changed given the merged work. Cite the PR or ADR that moved it.
   - **Orphan work**: merged PRs and new ADRs that map to no goal and are not declared `none (hygiene)`. A short orphan list is normal; a long one is the drift signal.
   - **Stalled**: goals untouched for 2+ review windows while PR volume was high nearby.
   - **Pace**: PRs merged : goals moved. A high ratio is not bad by itself; call it a substrate sprint if the work clearly serves a named goal, and a drift warning if the orphan list is also long.

5. Report (format below), then **update goals.md**: adjust statuses, remaining unlocks, and last-moved dates for goals that moved, and append one Review-log line (date, window, PR count, goals moved, verdict, next gauge point). The registry stays current because the command maintains it.

## Output format

```
## On-track review: <date> (window: <D> to <date>)

### Goals moved
- G-X STATUS -> STATUS: <PR/ADR that moved it>

### Orphan work (maps to no goal)
- PR #NNN / ADR-NNN <one line>: <why it is orphaned, or "hygiene, fine">

### Stalled
- G-X: no movement since <date> despite <N> PRs in adjacent areas

### Pace
- <N> PRs, <M> ADRs, <K> goals moved (ratio N:K): <one-sentence verdict>

### Next gauge point
One concrete, checkable statement for the next review (for example "G-1 goes LIVE before 20 more PRs land").
```

Keep it under a screenful. If the orphan list is long or a goal regressed, say so plainly at the top; this command exists to be the early warning, not to reassure.
