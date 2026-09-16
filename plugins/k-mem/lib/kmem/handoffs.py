"""Handoff notes between sessions: a mailbox outside every repo.

Notes live in ``<handoffs_dir>/pending/`` and move to ``archive/`` once acted
on. A note is addressed with a ``to:`` frontmatter line; the SessionStart
hook delivers every pending note addressed to the project it opens in.

A checkout answers to several names: its directory basename, the real
repository name resolved through the git common dir (a worktree's folder is
named after its branch), the ``repo`` its map names, and its configured
name. Matching any of them keeps notes addressed to a worktree name working
while letting repo-addressed notes reach worktree sessions.

    kmem handoff inbox                              what is waiting for this project
    kmem handoff send --to NAME --subject S [--body-file F]
    kmem handoff list
    kmem handoff archive NAME
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from .config import Config, load_config
from .govmap import find_repo_root, map_repo_name

MAX_NOTE_BYTES = 8000
_FIELD = re.compile(r"^(from|to|created|subject):\s*(.+?)\s*$", re.I)

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


def inbox(cwd: Path, config: Config | None = None) -> str:
    """The delivery text for every pending note addressed to this project, or ""."""
    config = config or load_config()
    names = project_names(cwd, config)
    primary = names[-1] if names else "?"
    blocks: list[str] = []
    for path in list_pending(config):
        to = parse_note(path).get("to", "")
        if to not in names:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:MAX_NOTE_BYTES]
        except OSError:
            continue
        blocks.append(f"--- {path.name} ---\n{text.rstrip()}\n")
    if not blocks:
        return ""
    return "\n".join(
        [
            f"=== HANDOFF INBOX: pending notes addressed to this project ({primary}) ===",
            *blocks,
            "=== END HANDOFF INBOX ===",
            "Instruction to Claude: incorporate these notes into your working context now.",
            "After acting on a note (or confirming it is stale), archive it with:",
            "  kmem handoff archive <file>",
            "Mention to the user that handoff notes were received and from where.",
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


def archive(config: Config, name: str) -> Path:
    src = pending_dir(config) / Path(name).name
    if not src.is_file():
        raise FileNotFoundError(f"no pending note named {Path(name).name}")
    dst_dir = archive_dir(config)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    src.replace(dst)
    return dst
