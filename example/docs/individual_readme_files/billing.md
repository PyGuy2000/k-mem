---
source_paths:
  - src/billing/
adr: [ADR-001, ADR-002]
devflow_tickets: [T-1001]
last_synced_sha: ""
---

# Billing facts

- `invoice.py` computes totals. It rounds each line half-up before summing.
- `tax.py` returns the rate for a region on a date from the versioned table.
- Money is a `Decimal` everywhere. No floats.
