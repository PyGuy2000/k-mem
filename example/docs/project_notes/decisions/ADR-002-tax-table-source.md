## ADR-002: Tax rates come from a versioned table [ACCEPTED]

**Date**: 2026-03-04
**Status**: Accepted
**Supersedes**: ADR-004
**Ref**: T-1002

### Context

Rates were constants in code (ADR-004). A rate change meant a release.

### Decision

`src/billing/tax.py` reads rates from a table keyed by region and effective
date. The table is data, versioned beside the code.

### Consequences

A rate change is a data change with a date, not a code release.
