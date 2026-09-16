# STATE: current state of {{PROJECT}}

The mandatory session-start read. Current state only: what exists, what is live versus parked, what is in flight, and the traps that cause wrong-direction work. Superseded facts are deleted here, not annotated; git holds the history. Rationale lives in `decisions/ADR-NNN-*.md`, one ADR per file, indexed by `decisions.md`. Incident history lives in `bugs.md` and `issues.md` (on demand). The plan index lives in `plans.md`.

Budget: keep this under ~15K tokens. `kmem audit` fails when it grows past that.

Last reviewed: {{DATE}}.

---

## What this is

One paragraph. What the project does and who it is for.

## Where to look

| Area | Files | Governing decisions |
|---|---|---|
| (subsystem) | `src/...` | (ADR-NNN, once written) |

Keep this table and `.claude/adr_map.json` in step: every row here with a governing ADR is a rule there.

## Live, partial, parked

- **Live:** what works end to end today.
- **Partial:** substrate exists; name the remainder.
- **Parked:** see `plans.md` for the parked rows and why.

## Traps

Things a new session gets wrong without being told. One line each.
