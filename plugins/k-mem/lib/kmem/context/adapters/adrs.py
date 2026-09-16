"""ADR records and header-block edges.

Per-file layout: one file each under ``docs/project_notes/decisions/``. The
header block is the heading plus the ``**Field**:`` lines that follow it;
only that block is parsed for edges, because body prose mentions every ADR
in the neighbourhood and would make the graph useless.

Single-file layout: every ADR is a ``## ADR-NNN`` heading inside one
``decisions.md``. Each section is parsed the same way.

Other configured repos are registered by id and title only, so a cross-repo
citation resolves to a real record.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from ...layout import DECISIONS_DIR, DECISIONS_MD
from ..ids import adr_id, find_adr_refs, find_ticket_refs
from ..models import ContextRecord, Relationship
from . import Emit, rel

HEADING = re.compile(r"^#{2,3}\s+ADR-(?P<num>\d+)\s*[:.]?\s*(?P<title>.*?)\s*$")
FIELD = re.compile(r"^\*\*(?P<name>[^*]+?)\s*:?\*\*\s*:?\s*(?P<val>.*)$")
STATUS_TAG = re.compile(r"\[(ACCEPTED|PROPOSED|REJECTED|SUPERSEDED|DEPRECATED)\]", re.I)
#: A trailing ``(alias-NNN)`` short id on a heading is not part of the title.
_TRAILING_SHORT_ID = re.compile(r"\([A-Za-z][\w-]*-\d+\)\s*$")
_VERB_BEFORE = re.compile(r"(amends|supersedes|replaces|extends|applies|implements)\s*$", re.I)
_VERB_WINDOW = 24
_NON_EDGE_FIELDS = ("status", "date", "goals", "layer", "domain")


def _clean_title(title: str) -> str:
    title = STATUS_TAG.sub("", title)
    title = _TRAILING_SHORT_ID.sub("", title)
    return title.strip(" —-:")


def _status(heading: str, status_field: str | None) -> str:
    tag = STATUS_TAG.search(heading)
    text = (tag.group(1) if tag else (status_field or "")).lower()
    for word in ("superseded", "rejected", "deprecated", "proposed", "accepted"):
        if word in text:
            return word
    return "unknown"


def _relation_for(field_name: str, text: str, start: int) -> str:
    name = field_name.lower()
    if name.startswith("depends"):
        return "depends_on"
    if name.startswith("supersedes"):
        return "supersedes"
    if name.startswith("superseded"):
        return "superseded_by"
    window = text[max(0, start - _VERB_WINDOW):start]
    m = _VERB_BEFORE.search(window)
    if m:
        verb = m.group(1).lower()
        if verb in ("supersedes", "replaces"):
            return "supersedes"
        if verb == "amends":
            return "amends"
    return "refs"


def parse_header(text: str) -> tuple[dict[str, str], int, str] | None:
    """Return ({field: value}, heading_line_no, heading_text) for the first ADR heading."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        h = HEADING.match(line)
        if not h:
            continue
        fields: dict[str, str] = {"__num__": h.group("num"), "__title__": h.group("title")}
        seen_field = False
        for raw in lines[i + 1 : i + 20]:
            if raw.startswith("#"):
                break
            f = FIELD.match(raw.strip())
            if f:
                fields[f.group("name").strip()] = f.group("val").strip()
                seen_field = True
                continue
            if seen_field and not raw.strip():
                break
        return fields, i + 1, line
    return None


def _edges_from_header(
    source_id: str, repo: str, fields: dict[str, str], prov: dict, aliases: Mapping[str, str]
) -> list[Relationship]:
    edges: list[Relationship] = []
    for name, val in fields.items():
        if name.startswith("__") or name.lower() in _NON_EDGE_FIELDS:
            continue
        for qid, start, _ in find_adr_refs(val, repo, aliases):
            if qid == source_id:
                continue
            relation = _relation_for(name, val, start)
            if relation == "superseded_by":
                edges.append(Relationship(qid, "supersedes", source_id, dict(prov, field=name)))
            else:
                edges.append(Relationship(source_id, relation, qid, dict(prov, field=name)))
        for tid in find_ticket_refs(val):
            edges.append(Relationship(source_id, "tracked_by", tid, dict(prov, field=name)))
    return edges


def _emit_adr(
    out: Emit, repo: str, path_rel: str, text: str, aliases: Mapping[str, str], line_offset: int = 0
) -> None:
    """Parse one ADR's text (a file, or one section of decisions.md) into a record + header edges."""
    parsed = parse_header(text)
    if not parsed:
        return
    fields, line_no, heading = parsed
    rid = adr_id(repo, fields["__num__"])
    prov = {"source": path_rel, "line": line_offset + line_no}
    status = _status(heading, fields.get("Status"))
    out.records.append(
        ContextRecord(
            record_id=rid,
            record_type="adr",
            title=_clean_title(fields["__title__"]),
            repo=repo,
            path=path_rel,
            status=status,
            metadata={"date": fields.get("Date", ""), "layer": fields.get("Layer", ""), "domain": fields.get("Domain", "")},
            provenance=prov,
        )
    )
    out.relationships.extend(_edges_from_header(rid, repo, fields, prov, aliases))


def iter_sections(lines: list[str]) -> list[tuple[int, int]]:
    """(start, end) 0-based line spans of every ``## ADR-NNN`` section in a single-file corpus."""
    starts = [i for i, line in enumerate(lines) if HEADING.match(line)]
    return [(s, starts[k + 1] if k + 1 < len(starts) else len(lines)) for k, s in enumerate(starts)]


def collect_current(root: Path, repo: str, aliases: Mapping[str, str] | None = None) -> Emit:
    """The current repo's ADRs with header edges, in either layout.

    Per-file (``decisions/ADR-NNN-*.md``) wins when it has files; otherwise
    every ``## ADR-NNN`` section of ``decisions.md`` is one record whose
    provenance line is the heading's absolute line. The first section for a
    number wins if a corpus repeats one.
    """
    aliases = dict(aliases or {})
    out = Emit()
    ddir = root / DECISIONS_DIR
    files = sorted(ddir.glob("ADR-*.md")) if ddir.is_dir() else []
    if files:
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            out.sources.append(path)
            _emit_adr(out, repo, rel(root, path), text, aliases)
        return out
    dmd = root / DECISIONS_MD
    if not dmd.is_file():
        return out
    try:
        lines = dmd.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    out.sources.append(dmd)
    seen: set[str] = set()
    for start, end in iter_sections(lines):
        h = HEADING.match(lines[start])
        rid = adr_id(repo, h.group("num")) if h else None
        if rid is None or rid in seen:
            continue
        seen.add(rid)
        _emit_adr(out, repo, rel(root, dmd), "\n".join(lines[start:end]), aliases, line_offset=start)
    return out


def collect_other(repo: str, base: Path) -> Emit:
    """Ids + titles for another repo (no edges, no governed paths)."""
    out = Emit()
    candidates: list[Path] = []
    ddir = base / DECISIONS_DIR
    if ddir.is_dir():
        candidates.extend(sorted(ddir.glob("*.md")))
    dmd = base / DECISIONS_MD
    if dmd.is_file():
        candidates.append(dmd)
    seen: set[str] = set()
    for path in candidates:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        out.sources.append(path)
        for i, line in enumerate(lines, 1):
            h = HEADING.match(line)
            if not h:
                continue
            rid = adr_id(repo, h.group("num"))
            if rid in seen:
                continue
            seen.add(rid)
            out.records.append(
                ContextRecord(
                    record_id=rid,
                    record_type="adr",
                    title=_clean_title(h.group("title")),
                    repo=repo,
                    path=str(path),
                    status=_status(line, None),
                    provenance={"source": str(path), "line": i},
                )
            )
    return out
