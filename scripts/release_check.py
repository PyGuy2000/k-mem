#!/usr/bin/env python3
"""Fail on any private name, host, path or ticket id in the tree.

    python3 scripts/release_check.py            # whole repo
    python3 scripts/release_check.py plugins/   # a subtree
    python3 scripts/release_check.py --history  # every commit's message and diff

The package must carry nothing that belongs to its author's projects. The
patterns in this file are structural (home paths, private-network hosts,
ticket ids, short decision ids, the private package prefix). Names that must
not appear even in a scrub list live outside the repo: one regex per line in
``$KMEM_RELEASE_CHECK_PATTERNS`` or ``~/.config/k-mem/release_check_patterns.txt``,
loaded when the file exists. Exit 1 on any hit, with file:line and the class.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"kazzer(?!labs)", re.I), "private package prefix"),
    (re.compile(r"192\.168\."), "private host"),
    (re.compile(r"\bT-\d{3}\b"), "private ticket id (3 digits)"),
    (re.compile(r"\b(?:pk|etl)-\d{3}\b"), "private short decision id"),
    (re.compile(r"/home/"), "home path"),
    (re.compile(r"/mnt/nas"), "NAS path"),
]

PRIVATE_PATTERNS_FILE = Path(os.environ.get("KMEM_RELEASE_CHECK_PATTERNS") or Path.home() / ".config" / "k-mem" / "release_check_patterns.txt")

EXCLUDE_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", ".venv"}
EXCLUDE_FILES: set[str] = set()
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".sqlite", ".pyc", ".zip", ".gz"}


def load_private_patterns(path: Path = PRIVATE_PATTERNS_FILE) -> list[tuple[re.Pattern[str], str]]:
    """Extra regexes, one per line, ``#`` comments allowed. Absent file: no extras."""
    out: list[tuple[re.Pattern[str], str]] = []
    if not path.is_file():
        return out
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            out.append((re.compile(line, re.I), f"private pattern {n}"))
        except re.error as exc:
            print(f"release-check: bad pattern on line {n} of {path}: {exc}", file=sys.stderr)
    return out


def all_patterns() -> list[tuple[re.Pattern[str], str]]:
    return PATTERNS + load_private_patterns()


def publishable_files(root: Path) -> list[Path] | None:
    """What a push would publish: tracked plus untracked-not-ignored.

    Scanning the whole working tree flags derived caches that git never
    publishes (a code index, a build directory). Returns None outside a git
    checkout, and the caller walks the tree instead.
    """
    import subprocess

    try:
        r = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return [root / line for line in r.stdout.splitlines() if line.strip()]


def iter_files(root: Path, paths: list[str]) -> list[Path]:
    known = publishable_files(root)
    if known is not None:
        out = [p for p in known if p.is_file() and p.suffix.lower() not in BINARY_SUFFIXES]
        if paths:
            wanted = [(root / p).resolve() for p in paths]
            out = [p for p in out if any(p.resolve() == w or w in p.resolve().parents for w in wanted)]
        return sorted(out)
    starts = [root / p for p in paths] if paths else [root]
    out = []
    for start in starts:
        if start.is_file():
            out.append(start)
            continue
        for p in sorted(start.rglob("*")):
            if not p.is_file() or EXCLUDE_DIRS & set(p.relative_to(root).parts):
                continue
            if p.suffix.lower() in BINARY_SUFFIXES:
                continue
            out.append(p)
    return out


def scan(root: Path, paths: list[str] | None = None) -> list[tuple[str, int, str, str]]:
    root = root.resolve()
    self_path = Path(__file__).resolve()
    patterns = all_patterns()
    hits: list[tuple[str, int, str, str]] = []
    for path in iter_files(root, paths or []):
        rel = path.relative_to(root).as_posix()
        if path.resolve() == self_path or rel in EXCLUDE_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for rx, why in patterns:
                if rx.search(line):
                    hits.append((rel, n, why, line.strip()[:120]))
    return hits


def scan_history(root: Path) -> list[tuple[str, int, str, str]]:
    """Every commit's message and diff. A hit here survives a clean tree; squash before the public push."""
    import subprocess

    try:
        log = subprocess.run(
            ["git", "-C", str(root), "log", "-p", "--all", "--format=commit %H%n%B"],
            capture_output=True, text=True, timeout=120,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    patterns = all_patterns()
    try:
        # This script's own diff holds the patterns; tree mode skips it too.
        self_rel = Path(__file__).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        self_rel = ""  # scanning another repo: nothing of ours to skip
    hits: list[tuple[str, int, str, str]] = []
    commit = "?"
    in_self = False
    for n, line in enumerate(log.splitlines(), 1):
        if line.startswith("commit ") and len(line) >= 47:
            commit = line[7:14]
            in_self = False
        elif line.startswith("diff --git "):
            in_self = bool(self_rel) and line.endswith(f" b/{self_rel}")
        if in_self:
            continue
        for rx, why in patterns:
            if rx.search(line):
                hits.append((f"git:{commit}", n, why, line.strip()[:120]))
    return hits


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("paths", nargs="*", help="subtrees or files to scan (default: the whole repo)")
    p.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    p.add_argument("--history", action="store_true", help="scan every commit's message and diff instead of the tree")
    args = p.parse_args(argv)
    extra = len(load_private_patterns())
    hits = scan_history(Path(args.root)) if args.history else scan(Path(args.root), args.paths)
    for rel, n, why, line in hits:
        print(f"{rel}:{n}: {why}: {line}")
    where = " in git history" if args.history else ""
    print(f"release-check: {len(hits)} hit(s){where} ({len(PATTERNS)} built-in + {extra} private patterns)", file=sys.stderr)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
