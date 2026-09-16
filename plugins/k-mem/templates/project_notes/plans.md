# Plans

One row per plan. A plan is one planning arc, usually a same-day or same-week cluster of decisions. The ADRs column names the decisions the plan covers (`1..3`, `7`; another repo's with its alias, `other-12`). The last column names the tickets that track it and anything deliberately set down.

Status: **LIVE** (delivered end to end), **PARTIAL** (substrate exists, named remainder), **OPEN** (decided, nothing built yet), **PARKED** (deliberately set down). A PARKED plan reached from a governing ADR shows up as a collision when you resolve a path.

| ID | Plan | Window | Status | ADRs | Tickets and parked remainders |
|---|---|---|---|---|---|
| P-01 | (first plan) | {{DATE}} | OPEN | (none yet) | (T-NNNN) |
