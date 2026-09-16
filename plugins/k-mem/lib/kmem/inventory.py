"""The knowledge inventory: what exists and where, across every configured repo.

A session starts empty. Nothing loads another repo's notes, so "does this
already exist?" tends to be answered from recollection. This enumerates
instead. It answers one question, WHAT EXISTS AND WHERE, and deliberately
does not summarise contents, because a summary is a second thing to
maintain and it would rot.

Three classes are enumerated: files (per-repo knowledge artifacts, by the
sections the config names), DECISIONS (every ADR identifier + title across
every repo), and HANDOFFS (every note's subject, pending AND archive, since
a recency-limited list is exactly what misses an old decision).

Two properties, do not remove either:

1. Every description is EXTRACTED from the file, never authored here.
2. Output is bounded and deterministic. It is injected at session start, so
   it competes for the same context as the work.

    kmem inventory [--out FILE] [--stats]
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import Config, load_config

_YAML_COMMENT = re.compile(r"^\s*#\s?(.+)$")
_MD_HEADING = re.compile(r"^#{1,3}\s+(.+)$")
_FRONTMATTER_SUBJECT = re.compile(r"^subject:\s*(.+)$", re.I)
_PY_DOCSTRING = re.compile(r'^\s*(?:"""|\'\'\')(.*)$')
_ADR_HEADING = re.compile(r"^#{2,3}\s+(ADR-\d+\S*\s*.*)$")
_SKIP_PARTS = {".git", "node_modules", ".venv", "__pycache__"}
_COLLAPSE_AT = 40


def first_line(path: Path, limit: int = 96) -> str:
    """Extract the file's own one-line self-description.

    YAML: the first comment line. Markdown: frontmatter ``subject:`` if
    present (handoffs), else the first heading. Python: the first docstring
    line. Returns "" when the file does not describe itself.
    """
    try:
        with path.open(encoding="utf-8", errors="ignore") as fh:
            head = [next(fh, "") for _ in range(40)]
    except OSError:
        return ""

    suffix = path.suffix.lower()
    for raw in head:
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        if suffix in {".yaml", ".yml"}:
            m = _YAML_COMMENT.match(line)
            if m:
                return m.group(1).strip()[:limit]
            if not line.startswith("#"):
                return ""
        elif suffix == ".md":
            m = _FRONTMATTER_SUBJECT.match(line)
            if m:
                return m.group(1).strip()[:limit]
            m = _MD_HEADING.match(line)
            if m:
                return m.group(1).strip()[:limit]
        elif suffix == ".py":
            m = _PY_DOCSTRING.match(line)
            if m and m.group(1).strip():
                return m.group(1).strip().removesuffix('"""').removesuffix("'''").strip()[:limit]
    return ""


def _row(repo: str, path: Path, base: Path) -> str:
    rel = path.relative_to(base).as_posix()
    desc = first_line(path)
    return f"- `{repo}/{rel}`{' — ' + desc if desc else ''}"


def _sorted(paths) -> list[Path]:
    return sorted({p for p in paths if not (_SKIP_PARTS & set(p.parts))}, key=lambda p: p.as_posix())


def _repo_sections(repo: str, base: Path, sections: dict[str, list[str]]) -> list[str]:
    body: list[str] = []
    for label, globs in sections.items():
        paths = _sorted(p for g in globs for p in base.glob(g) if p.is_file())
        if not paths:
            continue
        body.append(f"**{label}**")
        if len(paths) > _COLLAPSE_AT:
            body.append(f"- `{repo}/` {label}: {len(paths)} files, listing the first {_COLLAPSE_AT}")
            paths = paths[:_COLLAPSE_AT]
        body += [_row(repo, p, base) for p in paths]
        body.append("")
    return body


def decisions_section(repos: dict[str, Path]) -> list[str]:
    """Every ADR identifier + title, all repos, one line each."""
    out = [
        "## decisions (every ADR, all repos)",
        "",
        "One line per ADR: identifier + its own title. Before writing 'no ADR",
        "covers X' or minting a new ADR number, check this list.",
        "",
    ]
    for repo, base in repos.items():
        rows: list[str] = []
        adr_dir = base / "docs/project_notes/decisions"
        if adr_dir.is_dir():
            for p in _sorted(adr_dir.glob("*.md")):
                title = first_line(p, limit=88)
                rows.append(f"- {title or p.stem}")
        decisions_md = base / "docs/project_notes/decisions.md"
        if not rows and decisions_md.is_file():
            try:
                for line in decisions_md.open(encoding="utf-8", errors="ignore"):
                    m = _ADR_HEADING.match(line)
                    if m:
                        rows.append(f"- {m.group(1).strip()[:88]}")
            except OSError:
                pass
        if rows:
            out += [f"**{repo}** ({len(rows)} ADRs)"] + rows + [""]
    return out


def handoff_section(handoffs: Path) -> list[str]:
    """The cross-repo decision mailbox, pending and archive, listed in full."""
    if not handoffs.is_dir():
        return []
    notes = _sorted(p for d in ("pending", "archive") for p in (handoffs / d).glob("*.md"))
    if not notes:
        return []
    out = [
        "## handoffs (cross-repo decisions)",
        "",
        f"`{handoffs}`: all {len(notes)} notes, pending and archive.",
        "Outside every git repo, so no code index sees it. Listed in full:",
        "a recency-limited list is exactly what misses an old decision.",
        "",
    ]
    for p in sorted(notes, key=lambda q: q.name, reverse=True):
        stamp = p.name.split("__")[0][:8]
        pair = "__".join(p.name.split("__")[1:]).removesuffix(".md").replace("__to__", " -> ")
        subject = first_line(p)
        out.append(f"- {stamp} {pair}{' — ' + subject if subject else ''}")
    out.append("")
    return out


def build(config: Config | None = None) -> list[str]:
    """Build the inventory. Missing repos are skipped, never fatal."""
    config = config or load_config()
    out: list[str] = [
        "# Knowledge inventory (generated)",
        "",
        "What exists and where, across every configured repo. Generated by",
        "`kmem inventory`; descriptions are extracted from each file's own first",
        "line, never written here.",
        "",
        "Use it to answer 'does this already exist?' by reading rather than guessing.",
        "It says what a file IS, not what it CONTAINS; open the file for that.",
        "",
    ]
    present = {name: base for name, base in config.repos.items() if base.is_dir()}
    if not present:
        out += ["_No configured repo is present on this machine. Add one with `kmem init --repo NAME=PATH`._", ""]
    for repo, base in present.items():
        body = _repo_sections(repo, base, config.inventory_sections)
        if body:
            out += [f"## {repo}", ""] + body
    out += decisions_section(present)
    out += handoff_section(config.handoffs_dir)
    return out


def render(config: Config | None = None) -> str:
    return "\n".join(build(config)).rstrip() + "\n"


def stats_line(text: str, line_budget: int) -> str:
    lines = text.count("\n")
    words = len(text.split())
    flag = "OVER BUDGET" if lines > line_budget else "ok"
    return f"[inventory] {lines} lines / ~{words} words / ~{words * 4 // 3} tokens (budget {line_budget} lines): {flag}"
