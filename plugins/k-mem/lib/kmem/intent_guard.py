#!/usr/bin/env python3
"""Intent guard: unfinished intent in the project notes needs a ticket.

WHY. A next step written in prose is a note to self; nothing reads it back.
A next step written as a ticket shows up in every session brief until it is
done.

RULE. Any ADDED line under docs/project_notes/ that signals future work must
carry a ticket id (T-NNNN) on the same line, or the commit is refused.

What counts as future work (case-insensitive, word-boundary): next step(s),
proposed, deferred, not built, not yet built, to be built, todo, follow-up,
follow up, pending, still to do, later:. Lines inside fenced code blocks are
skipped; the archive/ tree is skipped (history, not intent); removed lines
are never checked.

This file has no package imports on purpose: ``kmem install-git-hooks``
copies it verbatim into ``.git/hooks/pre-commit`` so the hook keeps working
when the plugin moves or is uninstalled. ``--self-test`` runs the built-in
proof of red and green.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

INTENT = re.compile(
    r"\b(next\s+steps?|proposed|deferred|not\s+(?:yet\s+)?built|to\s+be\s+built|todo|follow[\s-]?up|pending|still\s+to\s+do|later:)\b",
    re.IGNORECASE,
)
TICKET = re.compile(r"\bT-\d{3,}\b")
WATCHED_PREFIX = "docs/project_notes/"
SKIP_PREFIXES = ("docs/project_notes/archive/",)
#: Not intent: a status tag on an ADR heading, an ADR's own Status line, and
#: words quoted in inline code (vocabulary being explained, not used).
_TAG = re.compile(r"\[[A-Z]+\]")
_INLINE_CODE = re.compile(r"`[^`]*`")
_STATUS_LINE = re.compile(r"^\s*\*\*Status\*\*\s*:", re.IGNORECASE)


def prose(text: str) -> str:
    return _TAG.sub("", _INLINE_CODE.sub("", text))


def offending_lines(diff_text: str) -> list[tuple[str, int, str]]:
    """Return (path, new_line_no, text) for added intent lines with no ticket."""
    out: list[tuple[str, int, str]] = []
    path = ""
    watched = False
    in_fence = False
    new_ln = 0
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            p = raw[4:].strip()
            path = p[2:] if p.startswith("b/") else p
            watched = path.startswith(WATCHED_PREFIX) and not path.startswith(SKIP_PREFIXES)
            in_fence = False
            continue
        if raw.startswith("--- ") or raw.startswith("diff ") or raw.startswith("index "):
            continue
        if raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            new_ln = int(m.group(1)) - 1 if m else 0
            continue
        if not watched:
            continue
        if raw.startswith("-"):
            continue
        new_ln += 1
        text = raw[1:]
        if text.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not raw.startswith("+") or in_fence or _STATUS_LINE.match(text):
            continue
        if INTENT.search(prose(text)) and not TICKET.search(text):
            out.append((path, new_ln, text.strip()))
    return out


def staged_diff(root: str | None = None) -> str:
    cmd = ["git"] + (["-C", root] if root else []) + ["diff", "--cached", "-U0", "--no-color", "--", WATCHED_PREFIX]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout


def report(bad: list[tuple[str, int, str]]) -> str:
    lines = [
        "INTENT GUARD: unfinished intent must carry a ticket id (T-NNNN) on the same line.",
        "Create the ticket and put its id on each line, or drop the line:",
    ]
    for path, ln, text in bad:
        lines.append(f"  {path}:{ln}: {text[:140]}")
    return "\n".join(lines)


# --- proof of red / green --------------------------------------------------

RED_DIFF = """diff --git a/docs/project_notes/issues.md b/docs/project_notes/issues.md
--- a/docs/project_notes/issues.md
+++ b/docs/project_notes/issues.md
@@ -10,0 +11,2 @@
+- **Phase 6**: migration guide and the ADR body in decisions.md; next step
+- DB migration pending: ALTER TABLE datasets ADD COLUMN path
"""

GREEN_DIFF = """diff --git a/docs/project_notes/issues.md b/docs/project_notes/issues.md
--- a/docs/project_notes/issues.md
+++ b/docs/project_notes/issues.md
@@ -10,0 +11,7 @@
+- Next step: write the ADR body (T-1835)
+- Shipped: file dispatch, 30 tests passing
+```
+TODO in a code block is not intent
+```
+## ADR-009: A heading with a status tag [PROPOSED]
+**Status**: Proposed
+- Words being explained (`deferred`, `pending`) are not intent either
"""


def self_test() -> int:
    red = offending_lines(RED_DIFF)
    green = offending_lines(GREEN_DIFF)
    ok = len(red) == 2 and red[0][1] == 11 and red[1][1] == 12 and green == []
    print(f"intent guard self-test: red={len(red)} (want 2) green={len(green)} (want 0) -> {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="unfinished intent in the project notes needs a ticket")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--diff-from-stdin", action="store_true", help="check a unified diff read from stdin")
    ap.add_argument("--root", help="repo root (default: cwd)")
    ap.add_argument("files", nargs="*", help="ignored; pre-commit frameworks pass filenames")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    diff = sys.stdin.read() if a.diff_from_stdin else staged_diff(a.root)
    bad = offending_lines(diff)
    if bad:
        print(report(bad), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
