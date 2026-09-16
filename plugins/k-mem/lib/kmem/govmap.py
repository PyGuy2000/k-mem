"""``.claude/adr_map.json``: which ADRs a path needs, and where each ADR lives.

This module owns the map's meaning. The read gate, the resolver and the
audit all import from here, so they can never disagree about what a pattern
matches or where a number resolves.

The file:

.. code-block:: json

    {
      "repo": "my_app",
      "rules": [
        {"paths": ["src/billing/**"], "adrs": [1, 2], "topic": "billing"}
      ]
    }

``repo`` is optional. It names the repo for qualified ids when the checkout's
own name would be wrong (an example folder inside another repo, say).

Two ADR layouts are first-class: one file per ADR under
``docs/project_notes/decisions/`` (``ADR-NNN-slug.md``), or every ADR as a
``## ADR-NNN`` heading inside one ``docs/project_notes/decisions.md``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .layout import DECISIONS_DIR, DECISIONS_MD, MAP_REL


def find_repo_root(start: Path | None = None) -> Path | None:
    """The nearest ancestor (or ``start`` itself) that carries the map."""
    cur = Path(start or Path.cwd()).resolve()
    cur = cur if cur.is_dir() else cur.parent
    for p in [cur, *cur.parents]:
        if (p / MAP_REL).is_file():
            return p
    return None


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """The map's glob dialect: ``**`` crosses directories, ``*`` and ``?`` do not."""
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def load_map_doc(root: Path) -> dict:
    with open(root / MAP_REL, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def load_map(root: Path) -> list[dict]:
    return list(load_map_doc(root).get("rules", []))


def map_repo_name(root: Path) -> str | None:
    """The ``repo`` the map names for itself, if any."""
    try:
        name = load_map_doc(root).get("repo")
    except (OSError, ValueError):
        return None
    return str(name) if name else None


def required_adrs(root: Path, rel_path: str, rules: list[dict] | None = None) -> set[int]:
    """Every ADR number the first matching rule of each pattern list demands."""
    rules = load_map(root) if rules is None else rules
    needed: set[int] = set()
    for rule in rules:
        for pat in rule.get("paths", []):
            if glob_to_regex(pat).match(rel_path):
                needed.update(int(n) for n in rule.get("adrs", []))
                break
    return needed


def adr_file(root: Path, number: int) -> Path | None:
    """The per-file layout: ``docs/project_notes/decisions/ADR-NNN-*.md``."""
    hits = sorted((root / DECISIONS_DIR).glob(f"ADR-{number:03d}-*.md"))
    return hits[0] if hits else None


def section_heading_re(number: int) -> re.Pattern[str]:
    return re.compile(rf"^#{{2,3}}\s+ADR-0*{number}(?![0-9])")


def adr_section_line(decisions_md: Path, number: int) -> int | None:
    """1-based line of the ``## ADR-NNN`` heading inside a single-file corpus, or None."""
    rx = section_heading_re(number)
    try:
        with open(decisions_md, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                if rx.match(line):
                    return i
    except OSError:
        return None
    return None


def adr_location(root: Path, number: int) -> tuple[Path, str] | None:
    """Where ADR ``number`` lives: (path, "file") or (decisions.md, "section"); None if nowhere."""
    p = adr_file(root, number)
    if p is not None:
        return p, "file"
    dmd = root / DECISIONS_MD
    if dmd.is_file() and adr_section_line(dmd, number) is not None:
        return dmd, "section"
    return None


def section_read_command(number: int) -> str:
    """One Bash command that prints exactly one ADR section and names both tokens the gate looks for."""
    tag = f"ADR-{number:03d}"
    return f"awk '/^##+ {tag}[: ]/{{p=1}} p&&/^##+ ADR-/&&!/{tag}[: ]/{{exit}} p' {DECISIONS_MD.as_posix()}"


def evidence_groups(number: int, path: Path, kind: str) -> list[tuple[str, ...]]:
    """Token groups; a group is satisfied when ONE tool_use input contains every token in it."""
    if kind == "file":
        return [(path.stem,), (f"{DECISIONS_DIR.name}/ADR-{number:03d}-",)]
    groups = [(DECISIONS_MD.name, f"ADR-{number:03d}")]
    if f"ADR-{number}" != f"ADR-{number:03d}":
        groups.append((DECISIONS_MD.name, f"ADR-{number}"))
    return groups
