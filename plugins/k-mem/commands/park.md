---
description: Record a deliberate deferral. Writes a PARKED:: marker plus an unpark condition into a DevFlow ticket (creating one first if the idea was never ticketed) so a later idea can collide with it.
---

Capture *why* something was set down, at the moment you set it down. A backlog ticket that merely went quiet is indistinguishable from one deferred on purpose, and that ambiguity is why an idea in July never gets checked against a decision from May. This command removes the ambiguity.

`/k-mem:idea` is the reciprocal: it reads what this writes. Needs the DevFlow plugin; without it, record the same three fields as a row in `docs/project_notes/plans.md` with status PARKED and say so.

## Invocation

- `/k-mem:park T-1144 "<reason>"`: park an existing ticket.
- `/k-mem:park "<the idea>"`: park something from this session that was never ticketed. Creates the ticket first, then parks it. **This is the common case**: mid-session ideas you decide not to chase are exactly what goes missing.

Resolve the DevFlow project from the current working directory. If no project matches, say so and offer DevFlow's `create_project` rather than guessing at an existing one.

## Steps

1. **Resolve the target.**
   - Ticket id given: DevFlow's `get_ticket(ticket_id)`. Read it fully; you need the existing `why` verbatim for step 4.
   - No ticket id: DevFlow's `add_ticket(title=<short form of the idea>, why=<what it would unlock>, project=<resolved project>, priority=low, status="backlog")`. Report the new id.

2. **Fill the three fields.** Ask only for what you cannot infer from the session:
   - **Why deferred**: the actual reason: waiting on something, wrong sequencing, cost, superseded, not worth it yet. "Later" is not a reason and must not be accepted.
   - **UNPARK WHEN**: the concrete condition that makes this live again. A date, a merged ticket, a graded result, a decision. If neither of you can state one, say so plainly: an item nobody can describe reactivating is a deletion candidate, not a parking candidate; offer that instead.
   - **TOUCHES**: tickets, ADRs, services, or repos this overlaps. This is the field `/k-mem:idea` collides against, so be generous. Name cross-repo overlaps explicitly.

3. **Concurrency guard.** `edit_ticket` replaces `why` wholesale, so an edit made by another session between your read and your write is discarded silently. Note the last log entry's timestamp from step 1. Immediately before writing, `get_ticket` once more and compare. If it moved, **stop**, show what changed, and re-read rather than overwrite.

4. **Write the marker into `why`.** Compose the new value as the block below, a blank line, then the **original `why` preserved verbatim**.

   ```
   PARKED:: <YYYY-MM-DD> <one-line reason>
   UNPARK WHEN: <concrete condition>
   TOUCHES: T-xxxx, ADR-xxx, <repo/service>
   ```

   The `::` is load-bearing. `search_tickets` is case-insensitive, so a bare `PARKED` also matches ordinary prose. `PARKED::` cannot occur by accident. Write it exactly. Already parked? Update the existing block in place. Never stack a second one.

5. **Log it.** DevFlow's `log_work(ticket_id, note=...)` with the same three fields plus session context worth resuming from: file paths, what was tried, what changed your mind. `why` is for discovery; the log is for resumption.

6. **Fix the status.** If the ticket was `active`, DevFlow's `update_ticket_status(ticket_id, "backlog")`. There is no `parked` status, so the marker in `why` carries the meaning. Genuinely waiting on another ticket rather than on a judgment call? Use `blocked` plus DevFlow's `add_dependency` instead, and say so. Blocked and parked are different states.

7. **Confirm in one line.** Id, marker, unpark condition. No ceremony.

## Output format

```
Parked T-1144 (was: active)
  Why:     card action-bar vocabulary from ADR-102 must settle first
  Unpark:  T-1465 merges and the verb list is graded
  Touches: ADR-059, ADR-102, dashboard tree
```

## Scope

Writes to the tracker only. Does not touch decisions, goals, or the work log; parking a ticket is not an architectural decision and does not move a goal. If the deferral *is* architecturally load-bearing (a plan direction abandoned rather than a task postponed), say so and offer an ADR separately.

## When to run

- The moment you say "not now" about anything, before the thought is gone.
- On any ticket sitting in `active` that has not moved in weeks.
- When closing a long session with threads left open: park each one rather than trusting the transcript.
- When `/k-mem:idea` reports a collision and the existing work wins: park the new idea against the ticket that beat it.
