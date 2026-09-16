"""SessionStart: first-run config, stale-checkout guard, handoff inbox,
context packet, knowledge inventory.

Everything prints to stdout, which Claude Code adds to the session context.
Every step is wrapped so one failure never hides the others, and the whole
hook exits 0: a SessionStart hook must never break a session. Sections can
be turned off in the config (``session_start``). The inventory is skipped
after a compaction (``source == "compact"``) so it is not re-injected.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .. import inventory
from ..config import Config, load_config
from ..gate import Gate, is_decision_record, read_payload
from ..govmap import adr_location, find_repo_root, required_adrs
from ..handoffs import inbox
from ..layout import DECISIONS_MD, STATE_MD
from ..scaffold import CLAUDE_MARKER

MAX_PACKET_FILES = 12


def _safe(fn: Callable[[], list[str]]) -> list[str]:
    """Run one section; a failure yields nothing. ``KMEM_DEBUG=1`` prints the traceback to stderr."""
    try:
        return fn()
    except Exception:  # noqa: BLE001
        if os.environ.get("KMEM_DEBUG"):
            import traceback

            traceback.print_exc()
        return []


# --- first run ----------------------------------------------------------------


def ensure_config(cwd: Path) -> tuple[Config, bool]:
    cfg = load_config()
    if cfg.path is not None:
        return cfg, False
    root = find_repo_root(cwd)
    if root is not None:
        from ..context.compiler import detect_repo_name

        cfg.repos[detect_repo_name(root, cfg)] = root
    for d in (cfg.evidence_dir, cfg.index_dir, cfg.handoffs_dir):
        d.mkdir(parents=True, exist_ok=True)
    cfg.save()
    return cfg, True


# --- stale checkout -------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def base_ref(root: Path) -> str:
    ref = _git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip()
    if ref:
        return ref
    for cand in ("origin/main", "origin/master", "main", "master"):
        if _git(root, "rev-parse", "--verify", "--quiet", cand).strip():
            return cand
    return ""


def stale_checkout_lines(root: Path) -> list[str]:
    """Warn when the default branch carries the notes contract and this checkout does not.

    A session inherits whatever CLAUDE.md the CURRENT BRANCH carries. A
    checkout parked on an old branch silently loads the old contract.
    """
    base = base_ref(root)
    if not base:
        return []
    problems: list[str] = []
    state_on_base = bool(_git(root, "ls-tree", base, STATE_MD.as_posix()).strip())
    if state_on_base and not (root / STATE_MD).is_file():
        problems.append(f"{STATE_MD.as_posix()} exists on {base} but is MISSING here; this branch predates the notes contract.")
    claude_on_base = _git(root, "show", f"{base}:CLAUDE.md")
    if CLAUDE_MARKER in claude_on_base:
        here = root / "CLAUDE.md"
        if not here.is_file() or CLAUDE_MARKER not in here.read_text(encoding="utf-8", errors="replace"):
            problems.append(f"CLAUDE.md on {base} carries the K-mem block and this checkout's does not.")
    if not problems:
        return []
    branch = _git(root, "branch", "--show-current").strip() or "(detached)"
    return [
        "=== STALE CHECKOUT WARNING ===",
        f"  path:   {root}",
        f"  branch: {branch}",
        *[f"  - {p}" for p in problems],
        f"  Context loaded from this branch is NOT the current contract. Do not make structural decisions from it; switch to {base} or work from a checkout that is on it.",
        "",
    ]


# --- context packet ---------------------------------------------------------------


def changed_files(root: Path) -> tuple[list[str], str]:
    base = base_ref(root)
    files: set[str] = set()
    if base:
        files.update(line.strip() for line in _git(root, "diff", "--name-only", f"{base}...HEAD").splitlines() if line.strip())
    for line in _git(root, "status", "--porcelain").splitlines():
        p = line[3:].strip()
        if " -> " in p:
            p = p.split(" -> ")[-1]
        p = p.strip('"')
        if p:
            files.add(p)
    return sorted(files), base


def packet_lines(gate: Gate, root: Path, session: str) -> list[str]:
    rel_files, base = changed_files(root)
    governed = [(f, required_adrs(root, f)) for f in rel_files]
    governed = [(f, n) for f, n in governed if n and not is_decision_record(f)]
    if not governed:
        return []
    branch = _git(root, "branch", "--show-current").strip() or "?"
    lines = [f"# Context packet: governed files changed on {branch} vs {base or '?'}. Read before editing them."]
    for rel, needed in governed[:MAX_PACKET_FILES]:
        reads: list[str] = []
        for n in sorted(needed):
            loc = adr_location(root, n)
            if loc is None:
                reads.append(f"ADR-{n:03d} (no file; map_error)")
            elif loc[1] == "file":
                reads.append(loc[0].relative_to(root).as_posix())
            else:
                reads.append(f"{DECISIONS_MD.as_posix()} section ADR-{n:03d}")
        cmp = gate.resolver_compare(root, rel, needed)
        parts = [f"- {rel} -> read: {', '.join(reads)}"]
        if "error" in cmp:
            parts.append(f"resolver: {cmp['error']}")
        else:
            adv = cmp.get("resolver_advisory") or []
            cols = cmp.get("collisions") or []
            parts.append(f"advisory {len(adv)}")
            if cols:
                parts.append("COLLISIONS: " + ", ".join(cols))
            if cmp.get("receipt"):
                parts.append(f"receipt {cmp['receipt']}")
        lines.append(" | ".join(parts))
    if len(governed) > MAX_PACKET_FILES:
        lines.append(f"- ... {len(governed) - MAX_PACKET_FILES} more governed files changed (run: kmem resolve --target <path>)")
    gate.log_evidence(session, {"status": "session_packet", "repo": gate.repo_name(root), "branch": branch, "files": [f for f, _ in governed][:MAX_PACKET_FILES]})
    lines.append("")
    return lines


# --- entry ----------------------------------------------------------------------------


def run(payload: dict) -> list[str]:
    source = str(payload.get("source") or "startup")
    cwd = Path(str(payload.get("cwd") or os.getcwd()))
    session = str(payload.get("session_id", "no-session"))
    out: list[str] = []
    cfg, created = ensure_config(cwd)
    if created:
        out.append(f"K-mem: created {cfg.path}. Register more repos with `kmem init --repo NAME=PATH`.")
        out.append("")
    flags = cfg.session_start
    root = find_repo_root(cwd)
    gate = Gate(cfg)
    if flags.get("stale_guard", True) and root is not None:
        out += _safe(lambda: stale_checkout_lines(root))
    if flags.get("inbox", True):
        out += _safe(lambda: [text] if (text := inbox(cwd, cfg)) else [])
    if flags.get("packet", True) and root is not None:
        out += _safe(lambda: packet_lines(gate, root, session))
    if flags.get("inventory", True) and source != "compact":
        out += _safe(lambda: inventory.build(cfg))
    return out


def main(argv: list[str] | None = None) -> int:
    payload = read_payload()
    try:
        lines = run(payload)
    except Exception:  # noqa: BLE001
        return 0
    if lines:
        sys.stdout.write("\n".join(lines).rstrip() + "\n")
    return 0
