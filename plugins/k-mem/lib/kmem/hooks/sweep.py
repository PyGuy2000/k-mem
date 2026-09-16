"""PostToolUse (Bash): the unevidenced-change sweep.

WHY. The read gate fires on the tool call. A change that reaches the disk
through a path the gate cannot parse (an obfuscated Bash command, a script
the command runs, a tool with no hook) leaves no evidence line at all, and
in the report a missing line looks exactly like a clean session. This hook
moves the evidence onto the FILE: after every Bash command it lists the
governed files that are dirty in the repo, and any one that changed in this
session with no ``read`` line in the session's evidence is logged as
``unevidenced`` (once per session and file) and named to the model with the
ADRs it must read. It never blocks: a PostToolUse hook cannot, and the sweep
exists to count the residual, not to hide it.

"Changed in this session" = the file's mtime is later than the session's
first transcript entry (or the first sweep, when the transcript carries no
timestamp). A file left dirty by an earlier session is not this session's
bypass.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from ..gate import Gate, bash_write_targets, is_decision_record, read_payload
from ..govmap import find_repo_root, required_adrs


def git_dirty(root: Path) -> list[str]:
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    out: list[str] = []
    for line in r.stdout.splitlines():
        p = line[3:].strip()
        if " -> " in p:
            p = p.split(" -> ")[-1]
        p = p.strip('"')
        if p:
            out.append(p)
    return out


def session_start_epoch(gate: Gate, transcript: Path, session: str) -> float:
    """Epoch of the session's first transcript entry; else the first sweep's time, remembered beside the evidence."""
    try:
        with open(transcript, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                ts = d.get("timestamp")
                if isinstance(ts, str) and ts:
                    from datetime import datetime

                    try:
                        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    except ValueError:
                        pass
                break
    except OSError:
        pass
    marker = gate.evidence_dir / f"{session}.sweep-start"
    try:
        if marker.exists():
            return float(marker.read_text().strip() or "0")
        gate.evidence_dir.mkdir(parents=True, exist_ok=True)
        now = time.time()
        marker.write_text(str(now))
        return now
    except OSError:
        return time.time()


def session_reads(gate: Gate, session: str) -> tuple[set[str], set[str]]:
    """(files with a ``read`` line, files already logged ``unevidenced``) in this session."""
    reads: set[str] = set()
    logged: set[str] = set()
    for d in gate.session_evidence(session):
        if d.get("status") == "read":
            reads.add(str(d.get("file")))
        elif d.get("status") == "unevidenced":
            logged.add(str(d.get("file")))
    return reads, logged


def sweep(root: Path, start: float, reads: set[str], logged: set[str]) -> list[dict]:
    found: list[dict] = []
    for rel in git_dirty(root):
        if rel in reads or rel in logged or is_decision_record(rel):
            continue
        try:
            needed = required_adrs(root, rel)
        except (OSError, ValueError, TypeError):
            continue
        if not needed:
            continue
        p = root / rel
        try:
            mtime = p.stat().st_mtime if p.exists() else time.time()
        except OSError:
            continue
        if mtime < start:
            continue
        found.append({"file": rel, "adrs": sorted(needed)})
    return found


def run(payload: dict, gate: Gate | None = None) -> list[str]:
    gate = gate or Gate()
    session = str(payload.get("session_id", "no-session"))
    cwd = Path(str(payload.get("cwd") or os.getcwd()))
    transcript = Path(str(payload.get("transcript_path", "")))
    command = str((payload.get("tool_input") or {}).get("command", ""))
    roots: dict[str, Path] = {}
    r0 = find_repo_root(cwd)
    if r0 is not None:
        roots[str(r0)] = r0
    for t in bash_write_targets(command, cwd):
        r = find_repo_root(t)
        if r is not None:
            roots[str(r)] = r
    if not roots:
        return []
    start = session_start_epoch(gate, transcript, session)
    reads, logged = session_reads(gate, session)
    notes: list[str] = []
    for root in roots.values():
        repo = gate.repo_name(root)
        for hit in sweep(root, start, reads, logged):
            gate.log_evidence(session, {"file": hit["file"], "status": "unevidenced", "via": "sweep", "repo": repo, "adrs": hit["adrs"]})
            logged.add(hit["file"])
            reads_needed = ", ".join(f"ADR-{n:03d}" for n in hit["adrs"])
            notes.append(f"  - {hit['file']} (governed by {reads_needed}; changed with no read this session; logged `unevidenced`)")
    return notes


def main(argv: list[str] | None = None) -> int:
    payload = read_payload()
    if not payload:
        return 0
    try:
        notes = run(payload)
    except Exception:  # noqa: BLE001
        return 0
    if notes:
        print("READ GATE (sweep): governed files changed outside the gate. Read their ADRs now and name them in your reply:")
        print("\n".join(notes))
    return 0
