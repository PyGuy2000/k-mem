"""Where a governed repo keeps its records. One place, so every module agrees.

All paths are relative to the repo root. A repo is governed the moment it
carries ``MAP_REL``; everything else is optional and skipped when absent.
"""

from pathlib import Path

#: Path patterns and the ADR numbers a write under them requires.
MAP_REL = Path(".claude/adr_map.json")
#: Self-expiring tolerances for the audit checks (optional).
AUDIT_REL = Path(".claude/kmem_audit.json")

NOTES_DIR = Path("docs/project_notes")
#: One file per ADR: ``ADR-NNN-slug.md``.
DECISIONS_DIR = NOTES_DIR / "decisions"
#: Either the generated index over ``DECISIONS_DIR`` or, in the single-file
#: layout, every ADR as a ``## ADR-NNN`` heading.
DECISIONS_MD = NOTES_DIR / "decisions.md"
STATE_MD = NOTES_DIR / "STATE.md"
PLANS_MD = NOTES_DIR / "plans.md"
ARCHIVE_DIR = NOTES_DIR / "archive"

#: Fact docs with frontmatter (``source_paths``, ``adr``, ``devflow_tickets``).
FACT_DOCS_DIR = Path("docs/individual_readme_files")
#: Cross-repo data contracts, one ``## Cn`` block each.
CONTRACTS_MD = FACT_DOCS_DIR / "data-contracts.md"
