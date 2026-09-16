# Example: a tiny governed repo

A billing module with four decisions, one plan table, one fact doc, and a
map that says which decision governs which path. Use it to try the tools on
the first session.

```
kmem resolve --root example --target src/billing/invoice.py
kmem resolve --root example --target src/billing/tax.py
kmem audit --root example
kmem notes index --root example
```

What you should see:

- `invoice.py` is governed by ADR-001 and ADR-002. The fact doc
  `docs/individual_readme_files/billing.md` and plan P-01 ride along as
  advisory records.
- `tax.py` is governed by ADR-002 and ADR-004. ADR-004 is superseded, and
  the map still names it: the resolver reports two collisions, the
  superseded decision and the parked plan P-02 that covers it. That drift is
  deliberate. It shows what a collision looks like before you meet one in
  your own repo.
- `kmem audit` passes all four checks.

The layout is the one `kmem init` scaffolds: `docs/project_notes/STATE.md`
(the current-state brief), `plans.md` (one row per plan), `decisions.md`
(the generated index) and `decisions/` (one file per ADR).
