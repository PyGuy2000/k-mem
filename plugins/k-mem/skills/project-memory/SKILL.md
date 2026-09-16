---
name: project-memory
description: Set up and maintain the tiered project memory in docs/project_notes/ (STATE.md brief, plans.md, one file per decision, key facts, bugs, work log). Use when asked to "set up project memory", "track our decisions", "log a bug fix", "update project memory", "write an ADR", or when a problem feels familiar ("didn't we solve this before?").
---

# Project memory

A project remembers across sessions through `docs/project_notes/`. The files are tiered so a session loads a small brief first and reads the rest on demand.

## Layout

```
docs/project_notes/
  STATE.md         current state; the mandatory session-start read (budget ~15K tokens)
  plans.md         one row per plan; status LIVE / PARTIAL / OPEN / PARKED
  decisions.md     generated index over decisions/ (never hand-edit below the marker)
  decisions/       one file per ADR: ADR-NNN-slug.md
  key_facts.md     ports, paths, service names, where credentials live (never values)
  bugs.md          one section per bug with root cause, fix, prevention
  issues.md        work log, one section per piece of work, ticket ids on every open item
  goals.md         goal registry, read by /k-mem:on-track
  archive/         what `kmem notes archive` moved out of bugs.md and issues.md
.claude/adr_map.json   which ADRs govern which paths; the read gate enforces it
```

## Setup

Run `kmem init` in the repo. It writes every missing file from the templates, the map, and a `<!-- k-mem:start -->` block in `CLAUDE.md`. It never overwrites a file that exists. Then:

1. Fill in `STATE.md` "What this is" and the "Where to look" table.
2. Write the first decision with `kmem notes adr "Title"`; fill it in; set its status tag.
3. Put the same numbers into `.claude/adr_map.json` for the paths the decision governs.
4. Run `kmem audit`. It passes when the index is fresh, every citation resolves, and STATE.md is under budget.

## Protocols

**Before proposing an architectural change:** run `kmem resolve --target <path>` for the files involved. Read the mandatory ADRs it lists and name them in your reply. If the change conflicts with one, say so and explain why revisiting is warranted; then write a new ADR that supersedes it (`**Supersedes**: ADR-NNN` in the new one, `**Status**: Superseded by ADR-MMM` in the old one).

**When a bug appears:** grep `docs/project_notes/bugs.md` for the symptom first. Apply the known fix if there is one. When you fix a new one, add a section: issue, root cause, solution, prevention.

**When you need configuration:** read `key_facts.md` before assuming a port, a path or a service name.

**When work finishes:** add a section to `issues.md` with the ticket id. Any line that names future work carries a ticket id on the same line; the pre-commit intent guard (`kmem install-git-hooks`) refuses the commit otherwise.

**When something is decided:** it goes in a decision file, not in a readme or a chat reply. `kmem notes adr "Title"` creates the next number and refreshes the index. The write guard shows a checklist the first time you write into `decisions/`; answer it, then re-issue the same write.

## Entry formats

Bug:

```markdown
## YYYY-MM-DD Short description

- **Issue**: what went wrong
- **Root cause**: why
- **Solution**: how it was fixed
- **Prevention**: how to avoid it next time
```

Work log:

```markdown
## YYYY-MM-DD T-NNNN: Short description

- **Status**: done | in progress | blocked
- **What**: one or two lines
- **Links**: PR, ticket, dashboard
```

Decision: the file `kmem notes adr` creates has the sections. Keep the heading `## ADR-NNN: Title [STATUS]`, the `**Date**` and `**Status**` lines; the index and the resolver parse them.

## Maintenance

- `kmem audit` before a push. It fails on a stale index, a citation with no file, a STATE.md over budget, or a decision that cites a decision that does not exist.
- `kmem notes archive` when bugs.md or issues.md grows past the nudge the Stop hook prints.
- Prune STATE.md; do not annotate it. Superseded facts are deleted; git holds the history.
- Keep every decision file. They are small and they are the history.

## Searching

```bash
grep -i "connection refused" docs/project_notes/bugs.md
grep -n "^## ADR-" docs/project_notes/decisions/*.md
kmem resolve --target src/billing/invoice.py
kmem inventory        # every ADR title across every configured repo
```
