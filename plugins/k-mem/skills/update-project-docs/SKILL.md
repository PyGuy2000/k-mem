---
name: update-project-docs
description: Keep a project's docs in sync with its code and its intent. Use when the user says "update the docs", "sync the docs", "the readmes are stale", "document this subsystem", or when the Stop hook's docs check flags stale files. Enforces the fact/intent split: individual readmes stay fact-based with frontmatter linking to source, ADRs and tickets; README.md is the intent index.
---

# update-project-docs

Sync a project's documentation layers so facts track the code and intent stays linked.

## The model

Fact-based docs rot because nothing forces an update when the code they describe changes, and the link from a stale fact to the *why* behind it goes missing. Two layers and a durable link fix both:

- **Facts** live in `docs/individual_readme_files/*.md`: what the code does now. They go stale fastest, so each carries frontmatter that pins it to its source and its intent.
- **Intent** lives in `README.md` (the index) and, durably, in the ADRs under `docs/project_notes/decisions/`. Tickets are the transient, in-flight form of intent.
- The chain: `ADR (why) <-> ticket (in flight) <-> individual readme (facts) <-> README (intent index)`. Anchor to the ADR, not the ticket; tickets close and vanish, ADRs stay.

The context resolver reads the same frontmatter: a fact doc's `source_paths` make it an advisory record for every path under them, so `kmem resolve --target <path>` shows which doc describes a file.

## Frontmatter (the enrollment contract)

Every file in `docs/individual_readme_files/` starts with:

```yaml
---
source_paths:          # code this doc describes; drift here flags it stale
  - src/etl/loader.py
  - src/etl/adapters/
last_synced_sha: a3145f5   # HEAD when this doc was last synced (kmem docs stamp sets it)
adr:                   # durable intent anchor(s)
  - ADR-035
devflow_tickets:       # in-flight work (optional, transient)
  - T-1451
---
```

Only `source_paths` and `last_synced_sha` are required for staleness detection. A doc missing them is "not enrolled" and skipped silently. Seed a new one with `kmem docs init <file>`; the template is at `templates/individual_readme.md` next to this skill.

## The sync procedure

### 1. Find what drifted

```bash
kmem docs check --force
```

This lists the readmes whose `source_paths` changed since their `last_synced_sha`, and any project-notes file over budget. Regenerate only those. For each stale doc, see exactly what changed:

```bash
git log --oneline <last_synced_sha>..HEAD -- <source_paths...>
git diff <last_synced_sha>..HEAD -- <source_paths...>
```

### 2. Regenerate the facts

For each stale readme, update it to match the current code: facts only (what the module exposes, key types and functions, data flow, config and env, ports). No rationale; that is the intent layer. Keep the existing frontmatter.

### 3. Refresh the intent index (README.md)

One row per documented subsystem: a one-line *why* (from the ADR, not invented), a link to its readme, a link to its ADR, and the open tickets (`mcp__devflow__list_tickets` when DevFlow is installed). Show only open tickets; closed ones drop off naturally.

### 4. Reconcile with the notes and the tickets

- If a subsystem changed enough to need a new decision, write one (`kmem notes adr "Title"`). Do not bury a decision in a readme.
- If work a `devflow_tickets` entry names is done, say so, so the ticket can be closed.

### 5. Stamp the synced docs

Only after a doc matches the code:

```bash
kmem docs stamp docs/individual_readme_files/<file>.md   # one
kmem docs stamp-all                                       # all enrolled
```

Stamping sets `last_synced_sha` to HEAD, which clears the flag. Never stamp a doc you did not verify; that is lying to the detector.

## In-code comments (keep it tight)

- Do: file and module header comments, public-API docstrings. Match the surrounding density.
- Do not: line-by-line internal comments, or restating what the code plainly says.

## Enrolling a project (first time)

1. `kmem init` (creates `docs/project_notes/` if missing).
2. `mkdir -p docs/individual_readme_files/` and add one fact-based file per subsystem.
3. `kmem docs init docs/individual_readme_files/<name>.md`, fill `source_paths` and `adr`, then `kmem docs stamp <file>`.
4. Make `README.md` the intent index linking to each.

After that the Stop hook flags drift automatically; run this skill to resync. The flag is advisory; it never edits or blocks.
