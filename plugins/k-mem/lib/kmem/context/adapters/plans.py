"""Plan rows from ``docs/project_notes/plans.md`` (the P-NN collision index).

A row ``| P-14 | title | window | STATUS | app-101, 102, 104; other-99 | ... |``
becomes a plan record with ``covers`` edges to every ADR in its ADRs column
and ``tracks`` edges to the tickets its last column names. A PARKED plan
reached from a mandatory ADR is reported as a collision.

In the ADRs column a prefix names a repo through the alias table and
carries forward to the bare numbers after it; ``1..4`` is a range.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from ...layout import PLANS_MD
from ..ids import adr_id, find_ticket_refs, plan_id
from ..models import ContextRecord, Relationship
from . import Emit

ROW = re.compile(r"^\|\s*(P-[0-9]+[a-z]?)\s*\|")
_CELL_SPLIT = re.compile(r"(?<!\\)\|")
_TOKEN = re.compile(r"(?:(?P<pre>[A-Za-z][\w-]*?)-)?(?P<a>\d+)(?:\.\.(?P<b>\d+))?")
_STATUS_WORDS = ("LIVE", "PARTIAL", "OPEN", "PARKED", "DONE")


def _status(cell: str) -> str:
    up = cell.replace("*", "").upper()
    for w in _STATUS_WORDS:
        if w in up:
            return w.lower()
    return "unknown"


def _adrs_in(cell: str, default_repo: str, aliases: Mapping[str, str]) -> list[str]:
    ids: list[str] = []
    repo = default_repo
    cell = re.sub(r"\([^)]*\)", "", cell)  # drop "(Ph5, Ph6)" / "(... 2026-08-17)" notes BEFORE splitting
    for token in re.split(r"[,;]", cell):
        for m in _TOKEN.finditer(token):
            if m.group("pre"):
                repo = aliases.get(m.group("pre"), default_repo)
            a = int(m.group("a"))
            b = int(m.group("b")) if m.group("b") else a
            for n in range(a, b + 1):
                qid = adr_id(repo, n)
                if qid not in ids:
                    ids.append(qid)
    return ids


def collect(root: Path, repo: str, aliases: Mapping[str, str] | None = None) -> Emit:
    aliases = dict(aliases or {})
    out = Emit()
    path = root / PLANS_MD
    if not path.is_file():
        return out
    out.sources.append(path)
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not ROW.match(line):
            continue
        cells = [c.strip() for c in _CELL_SPLIT.split(line)]
        cells = cells[1:-1] if len(cells) > 2 else cells
        if len(cells) < 5:
            continue
        pid = cells[0]
        rid = plan_id(repo, pid)
        prov = {"source": PLANS_MD.as_posix(), "line": line_no}
        status = _status(cells[3])
        out.records.append(
            ContextRecord(
                record_id=rid,
                record_type="plan",
                title=cells[1],
                repo=repo,
                path=f"{PLANS_MD.as_posix()}#{pid}",
                status=status,
                metadata={"window": cells[2]},
                provenance=prov,
            )
        )
        for qid in _adrs_in(cells[4], repo, aliases):
            out.relationships.append(Relationship(rid, "covers", qid, prov))
        if len(cells) > 5:
            for tid in find_ticket_refs(cells[5]):
                out.relationships.append(Relationship(rid, "tracks", tid, prov))
    return out
