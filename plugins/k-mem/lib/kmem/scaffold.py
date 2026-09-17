"""``kmem init`` in a repo: the project-notes scaffold, the map, the CLAUDE.md block.

Writes only what is missing. Never overwrites a file that exists. Templates
live under ``plugins/k-mem/templates/`` and take two variables:
``{{PROJECT}}`` and ``{{DATE}}``.

Also ``kmem install-git-hooks``: a self-contained pre-commit hook that runs
the intent guard over the staged diff.
"""

from __future__ import annotations

import datetime as dt
import os
import stat
from pathlib import Path

from . import intent_guard
from .layout import COMMANDS_REL, DECISIONS_DIR, MAP_REL, NOTES_DIR

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
CLAUDE_MARKER = "<!-- k-mem:start -->"
CLAUDE_END = "<!-- k-mem:end -->"
NOTES_FILES = ("STATE.md", "plans.md", "decisions.md", "key_facts.md", "bugs.md", "issues.md", "goals.md")


def render(text: str, project: str, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    return text.replace("{{PROJECT}}", project).replace("{{DATE}}", today.isoformat())


def template(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def claude_block(project: str, today: dt.date | None = None) -> str:
    return render(template("CLAUDE.md.block"), project, today)


def scaffold(root: Path, project: str, today: dt.date | None = None) -> list[str]:
    """Create the missing pieces; return one line per action."""
    root = Path(root)
    out: list[str] = []
    notes = root / NOTES_DIR
    (root / DECISIONS_DIR).mkdir(parents=True, exist_ok=True)
    keep = root / DECISIONS_DIR / ".gitkeep"
    if not any(p for p in (root / DECISIONS_DIR).iterdir() if p.name != ".gitkeep") and not keep.exists():
        keep.write_text("", encoding="utf-8")
        out.append(f"created {DECISIONS_DIR.as_posix()}/")
    for name in NOTES_FILES:
        target = notes / name
        if target.exists():
            out.append(f"kept    {NOTES_DIR.as_posix()}/{name}")
            continue
        target.write_text(render(template(f"project_notes/{name}"), project, today), encoding="utf-8")
        out.append(f"created {NOTES_DIR.as_posix()}/{name}")
    map_path = root / MAP_REL
    if map_path.exists():
        out.append(f"kept    {MAP_REL.as_posix()}")
    else:
        map_path.parent.mkdir(parents=True, exist_ok=True)
        map_path.write_text(render(template("adr_map.json"), project, today), encoding="utf-8")
        out.append(f"created {MAP_REL.as_posix()}")
    commands_path = root / COMMANDS_REL
    if commands_path.exists():
        out.append(f"kept    {COMMANDS_REL.as_posix()}")
    else:
        commands_path.parent.mkdir(parents=True, exist_ok=True)
        commands_path.write_text(render(template("commands.json"), project, today), encoding="utf-8")
        out.append(f"created {COMMANDS_REL.as_posix()} (empty; the command guard fires once you fill it)")
    claude = root / "CLAUDE.md"
    block = claude_block(project, today)
    if claude.exists():
        text = claude.read_text(encoding="utf-8")
        if CLAUDE_MARKER in text:
            out.append("kept    CLAUDE.md (block present)")
        else:
            claude.write_text(text.rstrip("\n") + "\n\n" + block, encoding="utf-8")
            out.append("updated CLAUDE.md (block appended)")
    else:
        claude.write_text(f"# {project}\n\n" + block, encoding="utf-8")
        out.append("created CLAUDE.md")
    out.extend(tracking_warnings(root))
    return out


# --- git hooks -------------------------------------------------------------------


def precommit_script() -> str:
    """The intent guard as a self-contained pre-commit hook."""
    source = Path(intent_guard.__file__).read_text(encoding="utf-8")
    header = "#!/usr/bin/env python3\n# Installed by `kmem install-git-hooks`. Self-contained; safe to keep after uninstalling the plugin.\n"
    body = source.split("\n", 1)[1] if source.startswith("#!") else source
    return header + body


def git_hooks_dir(root: Path) -> Path | None:
    import subprocess

    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-path", "hooks"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    p = Path(r.stdout.strip())
    return p if p.is_absolute() else (Path(root) / p)


def tracking(root: Path, rel: Path) -> str:
    """How git treats ``rel`` in ``root``: tracked | ignored | untracked | no-git | absent.

    WHY. A governance file that git does not carry works on the machine that
    wrote it and is gone from a fresh clone. The gate then allows every edit it
    used to refuse, silently, which is the failure this whole plugin exists to
    stop. Many repos ignore ``.claude/*`` wholesale, so this is the common case,
    not the odd one.
    """
    import subprocess

    path = Path(root) / rel
    if not path.is_file():
        return "absent"
    rel_posix = Path(rel).as_posix()

    def git(*args: str) -> subprocess.CompletedProcess | None:
        try:
            return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return None

    probe = git("rev-parse", "--is-inside-work-tree")
    if probe is None or probe.returncode != 0:
        return "no-git"
    listed = git("ls-files", "--error-unmatch", rel_posix)
    if listed is not None and listed.returncode == 0:
        return "tracked"
    ignored = git("check-ignore", "-q", rel_posix)
    if ignored is not None and ignored.returncode == 0:
        return "ignored"
    return "untracked"


#: The files a governed repo must carry in git for the gates to exist anywhere else.
GOVERNANCE_FILES = (MAP_REL, COMMANDS_REL)

TRACKING_ADVICE = {
    "ignored": "IGNORED by git: this machine only. A fresh clone has no gate. Add an exception to .gitignore and commit it.",
    "untracked": "not tracked by git: this machine only. A fresh clone has no gate. Commit it.",
}


def tracking_warnings(root: Path, states: tuple[str, ...] = ("ignored",)) -> list[str]:
    """One line per governance file git will not carry. Empty when all is well.

    ``kmem init`` passes the default. A file it just wrote is untracked by
    definition, so warning about that would fire every time and mean nothing.
    ``ignored`` is the one the user has to fix, and nothing else will say so.
    """
    out = []
    for rel in GOVERNANCE_FILES:
        state = tracking(root, rel)
        if state in states and state in TRACKING_ADVICE:
            out.append(f"WARNING {rel.as_posix()}: {TRACKING_ADVICE[state]}")
    return out


def install_git_hooks(root: Path, force: bool = False) -> str:
    hooks = git_hooks_dir(root)
    if hooks is None:
        raise ValueError(f"{root} is not a git repo")
    hooks.mkdir(parents=True, exist_ok=True)
    target = hooks / "pre-commit"
    if target.exists() and not force:
        existing = target.read_text(encoding="utf-8", errors="replace")
        if "kmem install-git-hooks" in existing:
            return f"kept {target} (already installed; --force to rewrite)"
        raise ValueError(f"{target} exists and is not ours; pass --force to replace it, or call `kmem intent-guard` from it")
    target.write_text(precommit_script(), encoding="utf-8")
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return f"installed {target} (intent guard over docs/project_notes on every commit)"


__all__ = ["scaffold", "claude_block", "install_git_hooks", "precommit_script", "CLAUDE_MARKER", "CLAUDE_END", "TEMPLATES_DIR", "os"]
