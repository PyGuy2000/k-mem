# STATE: current state of the example project

Budget: ~15K tokens. Read this first; read one ADR when you need it.

## What this is

A billing module. It computes invoice totals from line items and a tax table.

## Where to look

| Area | Files | Governing decisions |
|---|---|---|
| Invoice totals | `src/billing/invoice.py` | ADR-001, ADR-002 |
| Tax table | `src/billing/tax.py` | ADR-002 (ADR-004 superseded) |
| Project notes | `docs/project_notes/` | ADR-003 |

## Open work

See `plans.md`. P-01 is live. P-02 is parked until a second currency is needed.
