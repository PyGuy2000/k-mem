"""Fact docs: ``docs/individual_readme_files/*.md`` with frontmatter.

Frontmatter fields ``source_paths`` (-> governed paths), ``adr`` (-> refs)
and ``devflow_tickets`` (-> tracked_by) are the three link fields a docs
sync keeps. Parsed with a small stdlib reader, not PyYAML, so a hook can
import this without a virtualenv.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from ...layout import FACT_DOCS_DIR
from ..ids import fact_id, find_adr_refs, find_ticket_refs
from ..models import ContextRecord, GovernedPath, Relationship
from . import Emit, rel

_KEY = re.compile(r"^(?P<key>[A-Za-z_][\w-]*):\s*(?P<val>.*)$")
_ITEM = re.compile(r"^\s+-\s*(?P<val>.+?)\s*$")
#: A YAML comment: ``#`` at the start of the value or after whitespace.
_COMMENT = re.compile(r"(?:^|\s+)#")


def parse_frontmatter(text: str) -> tuple[dict[str, list[str] | str], int]:
    """Minimal YAML: scalars, inline ``[a, b]`` lists, and ``- item`` lists."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, 0
    data: dict[str, list[str] | str] = {}
    key: str | None = None
    end = 0
    for i, raw in enumerate(lines[1:], 1):
        if raw.strip() == "---":
            end = i
            break
        if raw.lstrip().startswith("#"):
            continue
        m = _KEY.match(raw)
        if m and not raw.startswith((" ", "\t")):
            key = m.group("key")
            val = _COMMENT.split(m.group("val").strip(), 1)[0].strip()
            if val.startswith("[") and val.endswith("]"):
                data[key] = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
            elif val:
                data[key] = val.strip("'\"")
            else:
                data[key] = []
            continue
        item = _ITEM.match(raw)
        if item and key is not None and isinstance(data.get(key), list):
            value = _COMMENT.split(item.group("val"), 1)[0].strip().strip("'\"")
            if value:
                data[key].append(value)  # type: ignore[union-attr]
    return data, end


def _title(lines: list[str], start: int, fallback: str) -> str:
    for line in lines[start:start + 40]:
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _pattern(root: Path, p: str) -> str:
    p = p.strip()
    if p.endswith("/") or (root / p).is_dir():
        return f"{p.rstrip('/')}/**"
    return p


def collect(root: Path, repo: str, aliases: Mapping[str, str] | None = None) -> Emit:
    aliases = dict(aliases or {})
    out = Emit()
    ddir = root / FACT_DOCS_DIR
    if not ddir.is_dir():
        return out
    for path in sorted(ddir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.sources.append(path)
        fm, end = parse_frontmatter(text)
        if not fm:
            continue
        rid = fact_id(repo, path.stem)
        rel_path = rel(root, path)
        prov = {"source": rel_path, "line": 1}
        out.records.append(
            ContextRecord(
                record_id=rid,
                record_type="fact",
                title=_title(text.splitlines(), end + 1, path.stem),
                repo=repo,
                path=rel_path,
                status="active",
                metadata={"last_synced_sha": str(fm.get("last_synced_sha", ""))},
                provenance=prov,
            )
        )
        for sp in fm.get("source_paths", []) if isinstance(fm.get("source_paths"), list) else []:
            out.governed.append(GovernedPath(_pattern(root, sp), rid, repo, dict(prov, relation="documents")))
        adrs = fm.get("adr", [])
        for entry in adrs if isinstance(adrs, list) else [adrs]:
            for qid, _, _ in find_adr_refs(str(entry), repo, aliases):
                out.relationships.append(Relationship(rid, "refs", qid, dict(prov, field="adr")))
        tickets = fm.get("devflow_tickets", [])
        for entry in tickets if isinstance(tickets, list) else [tickets]:
            for tid in find_ticket_refs(str(entry)):
                out.relationships.append(Relationship(rid, "tracked_by", tid, dict(prov, field="devflow_tickets")))
    return out
