---
description: Ticket brief across the configured repos. Blocked tickets, active work, cross-repo dependency chains, status drift between the tracker and git, and one suggested next action.
---

Produce a brief for the repos K-mem knows about (`kmem doctor` lists them), using the DevFlow plugin. Do not show unrelated projects. Without DevFlow, say so and stop; there is nothing to brief from.

## Steps

1. Call `mcp__devflow__get_status_report` once.
2. Filter every section (blocked, active, dependency chains, alerts) to the projects that correspond to the configured repos. Drop everything else.
3. Map each surviving ticket to its repo path from the K-mem config.
4. **Verify before you brief. The status column lies; the log and git do not.** For every surviving **active** and **blocked** ticket:
   - `mcp__devflow__get_ticket` and read the LAST work-log entry. If it contradicts the status (status `active` but the log says the fix landed and only a grade remains), the brief says what the LOG says.
   - `git -C <repo> log --all --grep='T-NNNN' --oneline -1` (batch these in one Bash call). A landed commit against a still-open ticket is drift.
   - Do NOT auto-update ticket statuses from here. Report drift; fixing it is a separate, deliberate step.
5. If a dependency chain spans repos, render it explicitly with each node's repo, status, and what unblocks what.
6. **Temperature.** From the same report and the tickets you read:
   - Open EPICs versus a cap of 3. Over the cap: the brief demands a disposition (one in, one out).
   - Quiet-not-parked: tickets 30+ days silent with no `PARKED::` marker. Each gets a named decision in the brief: work, park, or close. Silence is not a status.
   - Grade-pending: open tickets whose last log waits on a human grade. List them. These are the product; they get worked before anything meta.

## Output format

```
## Brief: <date>

### Blocked (needs unblocking)
- T-NNNN <title> [<project> -> <repo path>]: waiting on T-MMMM (<status>)

### Active
- T-NNNN <title> [<project>]: priority, unblocks: ...
  Last log: <one-line distillation of the latest work-log entry, with its date>

### Status drift (ticket says X, evidence says Y)
- T-NNNN: status `active`, but <log/git evidence>.
(omit when nothing drifts)

### Cross-repo chains
- T-AAAA (<repo>, <status>) -> T-BBBB (<repo>, <status>) -> T-CCCC (<repo>, <status>)

### Temperature
- Open EPICs: N/3 [over cap -> name the disposition candidates]
- Quiet, not parked: T-NNNN (Nd silent) -> decision: work / park / close
- Grade-pending (the product): T-NNNN <what the grade is>

### Suggested next action
One concrete recommendation: which ticket to work, in which repo, and why.
```

**Sequencing rules for the suggested action:**

1. If ANY grade-pending item exists, the suggested action MUST be one of them. Tooling and docs are wind-down work, never the headline suggestion.
2. If a dated commitment (demo, client date) is within 7 days, meta tickets are frozen: do not suggest them, and flag any created this week.
3. Over the EPIC cap: the suggested action may be the disposition pass itself; it costs an afternoon and clears the board.

The rules are mechanical on purpose: starts outrun finishes at the arc level, and meta work wins the "what next" decision because it grades instantly while product work waits on a human. The brief exists to invert that.

Keep it under a screenful. End with the suggested next action and offer to start it in this session.
