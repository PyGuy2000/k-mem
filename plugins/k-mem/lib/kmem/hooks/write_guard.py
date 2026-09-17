"""PreToolUse speed bump for writes into a decisions path.

WHY. A session-start reminder fails at turn 400. A rule that depends on the
model's attention degrades with session length. This hook moves the rule to
the moment of use: the first attempt to write into any decisions path is
DENIED with a checklist on stderr, which Claude Code feeds back to the model.
Re-issuing the same write then passes; the checklist is guaranteed to be the
most recent thing in context while the ADR is being written.

Fires once per (session, file). Markers live beside the evidence, so it never
nags twice and never blocks a retry loop.

Matched paths: anything under ``docs/project_notes/decisions/`` and any file
named ``decisions.md``.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from ..gate import Gate, read_payload

CHECKLIST = """DECISIONS WRITE GUARD: one-time checklist for this file, then re-run the exact same edit.

You are writing to a decisions path. Before re-issuing the write, confirm each line:
1. NUMBER UNIQUE: check the decisions list in the session-start inventory (or run
   `kmem inventory`), and any other worktree of this repo. Two sessions can mint the
   same number on the same day.
2. ABSENCE CLAIMS: if this ADR says something does not exist ("no store for X",
   "nothing holds Y"), cite the inventory section you checked.
3. ALREADY DECIDED: search the inventory's decisions and handoffs sections, the
   handoff archive included, for a prior decision on this topic.
4. NAMES: a new element name is defined in the ADR before it appears in code,
   tickets or docs.
5. TICKETS: outstanding work gets a ticket; a fully implemented ADR gets none.
6. INDEX: after the file lands, refresh decisions.md with whichever generator
   owns it. `kmem notes index` in a k-mem-managed repo; if this repo had its
   own index first, run that script instead (kmem refuses to overwrite it).

This block re-runs nothing and changes nothing. Re-issue the identical write; it will pass now.
"""

_PATH_KEYS = ("file_path", "path", "notebook_path", "destination")


def target_paths(payload: dict) -> list[str]:
    ti = payload.get("tool_input") or {}
    return [str(ti[k]) for k in _PATH_KEYS if ti.get(k)]


def is_decisions_path(file_path: str) -> bool:
    p = Path(file_path)
    return ("decisions" in p.parts and "project_notes" in p.parts) or p.name == "decisions.md"


def decide(payload: dict, gate: Gate | None = None) -> tuple[int, str]:
    hits = [p for p in target_paths(payload) if is_decisions_path(p)]
    if not hits:
        return 0, ""
    gate = gate or Gate()
    session = str(payload.get("session_id", "no-session"))
    for file_path in hits:
        key = hashlib.md5(f"{session}:{file_path}".encode()).hexdigest()
        if gate.mark_once(f"write-guard-{key}"):
            return 2, CHECKLIST
    return 0, ""


def main(argv: list[str] | None = None) -> int:
    payload = read_payload()
    if not payload:
        return 0
    code, msg = decide(payload)
    if msg:
        print(msg, file=sys.stderr)
    return code
