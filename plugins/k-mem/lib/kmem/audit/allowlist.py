"""Self-expiring tolerances, read from the governed repo's ``.claude/kmem_audit.json``.

Every entry names a ticket and an expiry date. Past the date the entry stops
counting and the check goes red. An entry with either missing never protects
anything.

.. code-block:: json

    {
      "adr_refs": {"42": {"ticket": "T-1042", "expires": "2026-10-15"}},
      "context_edges": {"29": {"ticket": "T-1042", "expires": "2026-10-15"}},
      "state_grace": {"ceiling_tokens": 18000, "ticket": "T-1044", "expires": "2026-09-30"},
      "skip_prefixes": ["docs/project_notes/decisions/", "docs/project_notes/archive/", "tests/"]
    }

``adr_refs``: ADR numbers cited bare with no local file (other repos' ADRs
written without a qualifier, usually) tolerated while the citation sweep
runs. ``context_edges``: the same for edges inside ADR headers.
``state_grace``: a ceiling above the STATE.md budget while a prune is
scheduled. ``skip_prefixes``: paths the citation scan ignores.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from ..layout import AUDIT_REL

DEFAULT_SKIP_PREFIXES: tuple[str, ...] = (
    "docs/project_notes/decisions/",
    "docs/project_notes/archive/",
    # Test fixtures cite invented numbers to prove a check goes red; they are
    # not citations.
    "tests/",
)


@dataclass
class Allowlist:
    adr_refs: dict[int, dict[str, Any]] = field(default_factory=dict)
    context_edges: dict[int, dict[str, Any]] = field(default_factory=dict)
    state_grace: dict[str, Any] | None = None
    skip_prefixes: tuple[str, ...] = DEFAULT_SKIP_PREFIXES
    path: Path | None = None


def _numbered(raw: Any) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        try:
            n = int(str(k).upper().replace("ADR-", ""))
        except ValueError:
            continue
        if isinstance(v, dict):
            out[n] = dict(v)
    return out


def load_allowlist(root: Path) -> Allowlist:
    path = Path(root) / AUDIT_REL
    if not path.is_file():
        return Allowlist()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Allowlist(path=path)
    if not isinstance(data, dict):
        return Allowlist(path=path)
    skip = data.get("skip_prefixes")
    return Allowlist(
        adr_refs=_numbered(data.get("adr_refs")),
        context_edges=_numbered(data.get("context_edges")),
        state_grace=data.get("state_grace") if isinstance(data.get("state_grace"), dict) else None,
        skip_prefixes=tuple(str(s) for s in skip) if isinstance(skip, list) else DEFAULT_SKIP_PREFIXES,
        path=path,
    )


def expired(entry: dict[str, Any], today: date) -> bool:
    """A malformed entry (no ticket, no date, bad date) counts as expired."""
    if not str(entry.get("ticket", "")).strip():
        return True
    try:
        return date.fromisoformat(str(entry["expires"])) < today
    except (KeyError, ValueError, TypeError):
        return True


def live(entry: dict[str, Any] | None, today: date) -> bool:
    return bool(entry) and not expired(entry, today)
