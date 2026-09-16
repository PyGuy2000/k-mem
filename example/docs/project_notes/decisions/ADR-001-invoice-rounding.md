## ADR-001: Invoices round half-up at the line level [ACCEPTED]

**Date**: 2026-03-02
**Status**: Accepted
**Depends on**: ADR-002
**Ref**: T-1001

### Context

Totals drifted by a cent between the invoice and the ledger because one
rounded per line and the other rounded the sum.

### Decision

Round each line to two decimals, half-up, before summing. The tax on each
line uses the rate from the tax table (ADR-002).

### Consequences

`src/billing/invoice.py` owns the rounding. No other module rounds money.
