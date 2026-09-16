---
# Keep this file FACT-based. Intent lives in README.md and the ADR.
source_paths:        # code this doc describes; drift here flags the doc stale
  - src/
last_synced_sha:     # set with: kmem docs stamp <this-file>  (after you sync it)
adr:                 # durable intent anchor(s), e.g. ADR-035
  - ADR-
devflow_tickets:     # in-flight work, e.g. T-1123 (optional, transient)
  - T-
---

# <Subsystem name>

Fact-based description of what this subsystem does now. No rationale; the *why* belongs in README.md (intent index) and the linked ADR.

## What it exposes
- Public functions, classes, endpoints, CLI commands and their signatures.

## Data flow
- Inputs, outputs, and how data moves through the module.

## Config
- Env vars, ports, files, secrets (reference by name; never paste secrets).

## Depends on
- Internal modules and external services this relies on.
