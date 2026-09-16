"""Stop: a turn that edited a governed path must name the ADRs.

WHY. "Name the ADR you read" is the visible enforcement of the read rule, and
left to the model it is skipped. This hook checks it: at the end of a turn,
every write since the last human message is mapped through the repo's map;
the final assistant text must mention each required ADR as ``ADR-NNN`` (or
``<alias>-NNN`` for a configured alias). If not, the stop is blocked once
with the list, so the model names them before the turn ends. Evidence goes
to the same ``<session>.jsonl`` as the read gate.

Fails open when the transcript is unreadable. One block per turn (marker
keyed on the transcript line of the last human message), never a loop.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

from ..gate import DIRECT_WRITE_TOOLS, Gate, bash_write_targets, read_payload
from ..govmap import find_repo_root, required_adrs

_PATH_KEYS = ("file_path", "notebook_path", "path", "source", "destination")


def turn_slice(transcript: Path) -> tuple[int, list[dict]]:
    """Return (index_of_last_human_message, messages after it)."""
    msgs: list[dict] = []
    try:
        with open(transcript, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d, dict) and d.get("type") in ("user", "assistant"):
                    msgs.append(d)
    except OSError:
        return -1, []
    last_human = -1
    for i, d in enumerate(msgs):
        if d.get("type") != "user":
            continue
        content = (d.get("message") or {}).get("content")
        if isinstance(content, str):
            last_human = i
        elif isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "text" for b in content):
            last_human = i
    return last_human, msgs[last_human + 1 :] if last_human >= 0 else msgs


def edited_files(msgs: list[dict]) -> list[str]:
    out: list[str] = []
    for d in msgs:
        content = (d.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                continue
            name = b.get("name")
            inp = b.get("input") or {}
            if name in DIRECT_WRITE_TOOLS:
                out.extend(str(inp[k]) for k in _PATH_KEYS if inp.get(k))
            elif name == "Bash":
                cwd = Path(str(d.get("cwd") or os.getcwd()))
                out.extend(str(p) for p in bash_write_targets(str(inp.get("command", "")), cwd))
    return out


def _has_tool_traffic(d: dict) -> bool:
    content = (d.get("message") or {}).get("content")
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") in ("tool_use", "tool_result") for b in content
    )


def final_reply_text(msgs: list[dict]) -> str:
    """Everything the assistant said after its last tool call this turn.

    A long reply can land as several assistant entries. Checking only the
    last one blocked a reply that had named both decisions two paragraphs
    earlier. The trailing run after the last tool call is what the user
    reads, and all of it counts; narration before a tool call does not.
    """
    last_tool = -1
    for i, d in enumerate(msgs):
        if _has_tool_traffic(d):
            last_tool = i
    parts: list[str] = []
    for d in msgs[last_tool + 1 :]:
        if d.get("type") != "assistant":
            continue
        content = (d.get("message") or {}).get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return "\n".join(p for p in parts if p)


last_assistant_text = final_reply_text  # the earlier name; same contract


def missing_names(text: str, needed: set[int], aliases: list[str] | None = None) -> list[int]:
    prefixes = ["ADR", "adr"] + [re.escape(a) for a in (aliases or [])]
    rx = re.compile(r"\b(?:" + "|".join(prefixes) + r")-0*(\d{1,3})\b")
    found = {int(n) for n in rx.findall(text)}
    return sorted(n for n in needed if n not in found)


def decide(payload: dict, gate: Gate | None = None) -> tuple[int, str]:
    if payload.get("stop_hook_active"):
        return 0, ""
    gate = gate or Gate()
    session = str(payload.get("session_id", "no-session"))
    transcript = Path(str(payload.get("transcript_path", "")))
    if not transcript.is_file():
        return 0, ""
    last_human, msgs = turn_slice(transcript)
    files = edited_files(msgs)
    if not files:
        return 0, ""

    needed: set[int] = set()
    for fp in files:
        root = find_repo_root(Path(fp))
        if root is None:
            continue
        try:
            rel = Path(fp).resolve().relative_to(root.resolve()).as_posix()
            needed |= required_adrs(root, rel)
        except (ValueError, OSError, TypeError):
            continue
    if not needed:
        return 0, ""

    text = final_reply_text(msgs)
    missing = missing_names(text, needed, list(gate.config.alias_map()))
    if not missing:
        gate.log_evidence(session, {"status": "named", "adrs": sorted(needed), "files": files[:8]})
        return 0, ""

    key = hashlib.md5(f"{session}:{last_human}".encode()).hexdigest()
    if not gate.mark_once(f"name-check-{key}"):
        gate.log_evidence(session, {"status": "unnamed", "adrs": sorted(needed), "missing": missing})
        return 0, ""
    gate.log_evidence(session, {"status": "blocked_once", "adrs": sorted(needed), "missing": missing})
    msg = (
        "ADR NAME CHECK: this turn edited a governed path and the reply does not name the governing ADRs. "
        "Add one line naming each (as ADR-NNN) and what it decided that applies here, then finish: "
        + ", ".join(f"ADR-{n:03d}" for n in missing)
    )
    return 2, msg


def main(argv: list[str] | None = None) -> int:
    payload = read_payload()
    if not payload:
        return 0
    code, msg = decide(payload)
    if msg:
        print(msg, file=sys.stderr)
    return code
