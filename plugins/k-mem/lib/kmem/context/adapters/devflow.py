"""Ticket status from DevFlow's state file, read-only.

Only tickets some edge already points at are registered, so the index stays
small. When the file is absent (CI, another machine) nothing is emitted and
``available`` is False; the edges-resolve audit then ignores ``T-`` targets.
The path comes from the config file (``devflow_state``) or from
``DEVFLOW_STATE_PATH``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ...config import DEFAULT_DEVFLOW_STATE
from ..models import ContextRecord
from . import Emit


def state_path(configured: Path | None = None) -> Path:
    env = os.environ.get("DEVFLOW_STATE_PATH")
    if env:
        return Path(env).expanduser()
    return Path(configured) if configured else Path(DEFAULT_DEVFLOW_STATE).expanduser()


def collect(referenced: set[str], configured: Path | None = None) -> tuple[Emit, bool]:
    out = Emit()
    path = state_path(configured)
    if not path.is_file():
        return out, False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out, False
    tickets = data.get("tickets", [])
    by_id = {t.get("id"): t for t in tickets if isinstance(t, dict)}
    for tid in sorted(referenced):
        t = by_id.get(tid)
        if not t:
            continue
        project = str(t.get("projectId", ""))
        out.records.append(
            ContextRecord(
                record_id=tid,
                record_type="ticket",
                title=str(t.get("title", "")),
                repo=(project[5:] if project.startswith("proj-") else project) or None,
                path=None,
                status=str(t.get("status", "unknown")),
                metadata={"priority": t.get("priority", ""), "blocked_by": list(t.get("blockedBy", []) or [])},
                provenance={"source": str(path), "ticket": tid},
            )
        )
    return out, True
