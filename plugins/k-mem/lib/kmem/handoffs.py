"""Handoff notes between sessions: a mailbox outside every repo.

Notes live in ``<handoffs_dir>/pending/`` and move to ``archive/`` once acted
on. A note is addressed with a ``to:`` frontmatter line; the SessionStart
hook lists every pending note addressed to the project it opens in.

Several worktrees of one repo all answer to the repo name, so the inbox shows
a subject line only and a session takes a note with ``claim``: one atomic
rename from ``pending/`` to ``claimed/``, so exactly one session wins and the
others are told who owns it. ``release`` puts a note back for another session.

A checkout answers to several names: its directory basename, the real
repository name resolved through the git common dir (a worktree's folder is
named after its branch), the ``repo`` its map names, and its configured
name. Matching any of them keeps notes addressed to a worktree name working
while letting repo-addressed notes reach worktree sessions.

    kmem handoff inbox                              what is waiting for this project
    kmem handoff send --to NAME --subject S [--body-file F]
    kmem handoff list
    kmem handoff claim NAME [--by WHO]              take a note; prints it
    kmem handoff release NAME                       put a claimed note back
    kmem handoff archive NAME
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from .config import Config, load_config
from .govmap import find_repo_root, map_repo_name

_FIELD = re.compile(r"^(from|to|created|subject|claimed_by|claimed_at):\s*(.+?)\s*$", re.I)
_CLAIM_LINE = re.compile(r"^claimed_(?:by|at):.*\n", re.M)

BODY_TEMPLATE = """## State
What is done, what is in flight (PR numbers, branch names, ticket ids).

## Ask
The specific action requested from the receiving session, or "FYI only".

## References
File paths, tickets, PR URLs. Link, do not paste code.

## Warnings
Anything the receiving session must not do (for example "do not git reset; uncommitted work present").
"""


def pending_dir(config: Config) -> Path:
    return config.handoffs_dir / "pending"


def claimed_dir(config: Config) -> Path:
    return config.handoffs_dir / "claimed"


def archive_dir(config: Config) -> Path:
    return config.handoffs_dir / "archive"


def _git(cwd: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def project_names(cwd: Path, config: Config | None = None) -> list[str]:
    """Every name this checkout answers to, primary (repo name) last."""
    config = config or load_config()
    cwd = Path(cwd)
    names: list[str] = []
    top = _git(cwd, "rev-parse", "--show-toplevel")
    names.append(Path(top).name if top else cwd.name)
    if top:
        common = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if common and Path(common).name == ".git":
            names.append(Path(common).parent.name)
    root = find_repo_root(cwd)
    if root is not None:
        named = map_repo_name(root)
        if named:
            names.append(named)
        configured = config.repo_for_root(root)
        if configured:
            names.append(configured)
    out: list[str] = []
    for n in names:
        if n and n not in out:
            out.append(n)
    return out


def parse_note(path: Path) -> dict[str, str]:
    meta: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i > 12:
                    break
                m = _FIELD.match(line)
                if m:
                    meta.setdefault(m.group(1).lower(), m.group(2))
    except OSError:
        pass
    return meta


def list_pending(config: Config | None = None) -> list[Path]:
    config = config or load_config()
    d = pending_dir(config)
    return sorted(d.glob("*.md")) if d.is_dir() else []


def list_claimed(config: Config | None = None) -> list[Path]:
    config = config or load_config()
    d = claimed_dir(config)
    return sorted(d.glob("*.md")) if d.is_dir() else []


def inbox(cwd: Path, config: Config | None = None) -> str:
    """The subject line of every pending note addressed to this project, or ""."""
    config = config or load_config()
    names = project_names(cwd, config)
    primary = names[-1] if names else "?"
    blocks: list[str] = []
    for path in list_pending(config):
        meta = parse_note(path)
        if meta.get("to", "") not in names:
            continue
        blocks.append(f"--- {path.name} ---\nfrom {meta.get('from', '?')}: {meta.get('subject', '(no subject)')}\n")
    if not blocks:
        return ""
    return "\n".join(
        [
            f"=== HANDOFF INBOX: pending notes addressed to this project ({primary}) ===",
            *blocks,
            "=== END HANDOFF INBOX ===",
            "Instruction to Claude: these are subject lines only. Other sessions of this repo see the same list.",
            "Tell the user what is waiting. Do not act on a note until this session owns it. To take one, run:",
            "  kmem handoff claim <file>",
            "It prints the note. Claim a note only when the user asks for it or this session has no other task.",
            "If the claim is refused, another session owns the note; leave it alone.",
            "When done (or the note is stale): kmem handoff archive <file>",
            "If this session cannot do it: kmem handoff release <file>",
            "",
        ]
    )


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", name.strip()).strip("-") or "unknown"


def note_name(from_: str, to: str, when: float | None = None) -> str:
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(when or time.time()))
    return f"{stamp}__{_slug(from_)}__to__{_slug(to)}.md"


def compose(from_: str, to: str, subject: str, body: str = "", when: float | None = None) -> str:
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(when or time.time()))
    body = body.strip() or BODY_TEMPLATE.strip()
    return f"---\nfrom: {from_}\nto: {to}\ncreated: {created}\nsubject: {subject.strip()}\n---\n\n{body}\n"


def send(config: Config, from_: str, to: str, subject: str, body: str = "", when: float | None = None) -> Path:
    d = pending_dir(config)
    d.mkdir(parents=True, exist_ok=True)
    path = d / note_name(from_, to, when)
    path.write_text(compose(from_, to, subject, body, when), encoding="utf-8")
    return path


def claim(config: Config, name: str, owner: str, when: float | None = None) -> Path:
    """Take a pending note for ``owner``. The rename is the lock: one caller wins."""
    note = Path(name).name
    dst = claimed_dir(config) / note
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(pending_dir(config) / note, dst)
    except FileNotFoundError:
        if dst.is_file():
            raise FileExistsError(f"{note} is already claimed by {parse_note(dst).get('claimed_by', 'another session')}") from None
        raise FileNotFoundError(f"no pending note named {note}") from None
    text = dst.read_text(encoding="utf-8", errors="replace")
    if text.startswith("---\n"):
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(when or time.time()))
        dst.write_text(f"---\nclaimed_by: {owner}\nclaimed_at: {stamp}\n{text[4:]}", encoding="utf-8")
    return dst


def release(config: Config, name: str) -> Path:
    """Put a claimed note back in the inbox, with its owner lines removed."""
    note = Path(name).name
    src = claimed_dir(config) / note
    if not src.is_file():
        raise FileNotFoundError(f"no claimed note named {note}")
    src.write_text(_CLAIM_LINE.sub("", src.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
    dst = pending_dir(config) / note
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dst)
    return dst


def archive(config: Config, name: str) -> Path:
    src = pending_dir(config) / Path(name).name
    if not src.is_file():
        src = claimed_dir(config) / Path(name).name
    if not src.is_file():
        raise FileNotFoundError(f"no pending or claimed note named {Path(name).name}")
    dst_dir = archive_dir(config)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    src.replace(dst)
    return dst
