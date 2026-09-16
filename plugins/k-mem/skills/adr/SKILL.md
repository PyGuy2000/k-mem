---
name: adr
description: Query the decisions of this repo and every configured repo. "/k-mem:adr open" = ADRs with open tickets; "/k-mem:adr done" = completed ADRs; "/k-mem:adr links <id>" = one ADR's relationships; "/k-mem:adr health" = index health; "/k-mem:adr <question>" = any other ADR question. Use when the user asks which decisions have outstanding work, how ADRs relate, or what was decided about a topic.
---

# ADR: decision queries

One command for questions about Architecture Decision Records. Backed by the K-mem context index (`kmem resolve`, `kmem edges`, `kmem inventory`) and, when the DevFlow plugin is installed, its ADR index (`mcp__devflow__list_adrs`, `mcp__devflow__get_adr`, `mcp__devflow__refresh_adr_index`).

## Ground rules

- **Qualify ids.** Every repo restarts at ADR-001, so a bare number names several decisions. Use `<repo>:ADR-NNN` (the id `kmem resolve` prints). If the user gives a bare number, assume the current repo and say so.
- The indexes are **derived caches**. If the user just wrote or edited an ADR, run `kmem index` (and `mcp__devflow__refresh_adr_index` when DevFlow is present) before answering.
- An ADR heading with no `[TAG]` is assumed accepted. "All its tickets are done" is the stronger completion signal.

## Subcommands

### open

ADRs with outstanding work. With DevFlow: `mcp__devflow__list_adrs(has_ticket=true)` and keep those whose tickets are not all `done`. Without DevFlow: grep `**Ref**:` and `**Goals**:` lines in `docs/project_notes/decisions/*.md` for ticket ids and list them; say that ticket status is unknown. Summarise grouped by repo: id, short title, open tickets with status. Highlight `active` above `backlog` and `blocked`.

### done

ADRs that are complete: every referenced ticket `done`, or status tag `[ACCEPTED]` with no ticket. Give the count per repo.

### links <id>

`kmem resolve --target` needs a path, so for one decision run `kmem edges --json` and filter both directions on the id, then read the ADR's header block for `Depends on`, `Supersedes`, `Superseded by`, `Ref`. With DevFlow: `mcp__devflow__get_adr(uid=...)` for ticket details. Report:

1. Title, status, date.
2. Each edge: type, target id, target title, and whether it resolves. Flag unresolved edges (they point at decisions that do not exist yet) and cross-repo edges explicitly.
3. Linked tickets with statuses.
4. One-line summary of the Decision section.

### health

Run `kmem audit` and `kmem edges`. Report: citations with no file, a stale index, STATE.md over budget, unresolved edges, ADRs with no status tag, and (with DevFlow) ADRs without tickets and stale proposals. For each non-empty bucket, say what fixing it looks like in one sentence.

### <anything else>

Treat as a free-form question. Prefer `kmem inventory` (every ADR title across repos) to find candidates, then read the one or two decision files that match. With DevFlow, `mcp__devflow__list_adrs(project=..., status=..., has_ticket=...)` for filters.

## Output style

Lead with the count or the direct answer. Keep tables short; prose for the rest. Use qualified ids so results are copy-pasteable into a follow-up `links`.
