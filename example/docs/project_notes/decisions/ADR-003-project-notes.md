## ADR-003: Project notes are tiered [ACCEPTED]

**Date**: 2026-03-10
**Status**: Accepted

### Context

A session starts empty. One long notes file is read once and never again.

### Decision

Three tiers. `STATE.md` is the current-state brief under a token budget.
`plans.md` is one row per plan. `decisions/` holds one file per ADR, and
`decisions.md` is the generated index over them.

### Consequences

`kmem audit` fails when `STATE.md` is over budget or the index is stale.
