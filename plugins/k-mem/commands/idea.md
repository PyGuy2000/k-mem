---
description: In-session collision check. Tests a new idea against active work and PARKED:: tickets across all projects before you spend a session planning it, and reports whether it extends, cannibalizes, or unparks existing work.
---

Answer one question fast enough to ask mid-session: **does this idea cannibalize something already decided?** `/k-mem:on-track` gauges direction after the fact; this gauges a candidate before a session gets committed to it.

Deliberately narrow. It reads active and parked tickets plus the plan-level registry (`docs/project_notes/plans.md`), never the full decision corpus or the backlog. That bound is what keeps it cheap enough to run on impulse, and it means a clean result is **not** proof of no conflict. Say so every time.

## Steps

1. **Gather the collision set** (run in parallel; seconds, not a minute). DevFlow calls apply when the DevFlow plugin is installed; without it, use the plan registry and the session only, and say so.
   - DevFlow's `list_tickets(project=<project resolved from cwd>, status="active")`
   - DevFlow's `search_tickets(query="PARKED::")`. Search the token **with** the `::`; the bare word pulls in prose false positives. Global across projects on purpose.
   - DevFlow's `search_tickets(query=<2-3 distinctive nouns from the idea>)`, one call per term. Also global: the collision that costs the most is the one that spans repos.
   - **The plan registry.** If the resolved project has `docs/project_notes/plans.md`, read its last column (tickets and deliberately deferred remainders). This is the plan-level tier: coarser than tickets, cheaper than the decision corpus, and it catches a parked *remainder* that was never split into its own ticket.
   - **The resolver.** If the idea names files, `kmem resolve --target <path>` for each; a PARKED plan in its collisions is a candidate.
   - Anything parked, decided, or reversed **earlier in this session**. Read it from the conversation, not from disk. This is the case no registry can cover and the reason the command exists.

2. **Judge against each candidate.** Candidates are tickets (`T-NNNN`) and plan rows (`P-NN`); cite whichever matches. Shared subject matter is not collision. Ask whether doing this idea would redo, contradict, or strand work that already exists.

3. **Verdict, exactly one:**

   - **EXTENDS**: builds on active work. Name the ticket; say whether it belongs *inside* that ticket rather than beside it.
   - **CANNIBALIZES**: redoes, competes with, or strands an active or parked item. Name it, quote its `PARKED::` reason, and state plainly which of the two should win. Do not soften this to "some overlap". A hedged collision report is the same as no report.
   - **UNPARKS**: the idea satisfies a parked ticket's `UNPARK WHEN` condition. Highest-value result: something deliberately set down just became live, and nothing else surfaces that. Say what changed.
   - **CLEAR**: no collision in the set checked. Always name the bound.

4. **Offer the next action, do not take it:**
   - CANNIBALIZES, existing work wins: `/k-mem:park "<the idea>"` against that ticket.
   - CANNIBALIZES, new idea wins: `/k-mem:park` the *old* ticket with the new idea as its reason, so the reversal is recorded rather than left as two live claims.
   - UNPARKS: set the ticket active and strip the `PARKED::` block from its `why`.
   - EXTENDS: log a note on the ticket it extends.
   - CLEAR and worth planning: hand to your planning step, carrying the CLEAR verdict's bound so it gets re-checked against the full corpus there.

## Output format

```
## <VERDICT>: <idea in one line>

<2-4 lines: what it collides with or extends, and why>

- T-1144 [parked 2026-07-19] card vocabulary must settle first
- T-1465 [active] verb rollout; same surface
- P-13 [deferred] per-category data governance; plan-level overlap

Next: <the one concrete action>

Checked: <N> active + <M> parked tickets (all projects) + <P> plan rows. Not checked: full backlog, decision corpus.
```

Keep it under half a screen. Verdict on the first line, always.

## Accuracy caveat

This reads `active` as a proxy for "in flight". If the active column holds stalled work, the collision set is wrong in a way the output will not show. Check DevFlow's `get_status_report` for `stale_active` occasionally; anything stale belongs in `/k-mem:park`, not in the collision set.

## When to run

- Any time an idea arrives mid-session and you cannot immediately place it against what is already open.
- Before planning anything that is not already a ticket.
- After a long session resumes, on any idea that survived the break. That gap is where context goes.
