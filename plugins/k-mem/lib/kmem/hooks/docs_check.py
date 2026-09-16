"""Stop: the docs staleness and notes-budget check (advisory).

Runs ``kmem docs check`` against the cwd repo: fact docs whose sources
changed since they were last synced, and project-notes files over budget.
Prints to stdout and exits 0. It flags; it never edits or blocks.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from ..config import load_config
from ..docsync import check
from ..gate import read_payload


def main(argv: list[str] | None = None) -> int:
    payload = read_payload()
    cwd = Path(str(payload.get("cwd") or os.getcwd()))
    try:
        lines = check(cwd, load_config(), force=False)
    except Exception:  # noqa: BLE001
        return 0
    if lines:
        sys.stdout.write("\n".join(lines) + "\n")
    return 0
