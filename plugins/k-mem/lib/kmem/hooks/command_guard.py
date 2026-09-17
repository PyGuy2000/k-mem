"""PreToolUse on Bash: refuse the wrong interpreter and truncated evidence.

WHY. See ``kmem.cmdguard``. The gate family covers writes; this covers the two
reading mistakes that leave a tool call behind.

Opting in is declaring ``.claude/commands.json`` in the repo. No file, no rule,
and the hook exits 0 without reading anything else. ``"command_guard": false``
in the user config turns it off everywhere. A ``DISABLED`` marker in the
evidence dir (only a human creates one) turns it off with every would-be
refusal logged instead.

Fails OPEN. An unreadable declaration, a command the splitter cannot parse, or
any other fault allows the command and never breaks the session.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..cmdguard import find_commands_root, load_commands, message, pinned_violations, truncation_violations
from ..gate import Gate, read_payload

#: Tool names whose input carries a shell command.
BASH_TOOLS = {"Bash", "BashOutput"}


def decide(payload: dict, gate: Gate | None = None) -> tuple[int, str]:
    if str(payload.get("tool_name", "")) not in BASH_TOOLS:
        return 0, ""
    command = str((payload.get("tool_input") or {}).get("command", "")).strip()
    if not command:
        return 0, ""
    gate = gate or Gate()
    if not gate.config.command_guard:
        return 0, ""
    root = find_commands_root(Path(str(payload.get("cwd") or ".")))
    if root is None:
        return 0, ""
    declared = load_commands(root)
    if not declared:
        return 0, ""
    pins = pinned_violations(command, declared["pinned"])
    cuts = truncation_violations(command, declared["evidence_commands"])
    if not pins and not cuts:
        return 0, ""
    session = str(payload.get("session_id", "no-session"))
    record = {
        "hook": "command-guard",
        "repo": gate.repo_name(root),
        "pinned": [{"key": k, "written": w, "required": r} for k, w, r in pins],
        "truncated": [{"command": c, "cut": t} for c, t, _ in cuts],
        "command": command[:400],
    }
    if gate.disabled():
        gate.log_evidence(session, {**record, "status": "disabled"})
        return 0, ""
    gate.log_evidence(session, {**record, "status": "refused"})
    return 2, message(root, pins, cuts)


def main(argv: list[str] | None = None) -> int:
    payload = read_payload()
    if not payload:
        return 0
    try:
        code, msg = decide(payload)
    except Exception as exc:  # noqa: BLE001 - a hook fault must never block a session
        print(f"command guard skipped (internal error: {exc})", file=sys.stderr)
        return 0
    if msg:
        print(msg, file=sys.stderr)
    return code
