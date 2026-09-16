"""Cross-repo data contracts from ``docs/individual_readme_files/data-contracts.md``.

One ``## Cn — title`` block per contract. A contract governs the repo-relative
paths its Producer / Owner / Consumers lines name in backticks (a directory
becomes ``dir/**``), plus any bare ``plugins/<name>`` shorthand, and refs the
ADRs its body cites. Contracts are advisory.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from ...layout import CONTRACTS_MD
from ..ids import contract_id, find_adr_refs, find_ticket_refs
from ..models import ContextRecord, GovernedPath, Relationship
from . import Emit

BLOCK = re.compile(r"(?m)^## (C\d+)\b\s*(?:[—–-]+\s*)?(.*)$")
ROLE_LINE = re.compile(r"\*\*(?P<role>Producer|Owner|Consumers?)s?:\*\*\s*(?P<val>.*)", re.I)
PLUGIN_DIR = re.compile(r"plugins/([\w-]+)")
BACKTICK_PATH = re.compile(r"`([\w][\w./-]*?)`")


def _paths_in(root: Path, line: str) -> list[str]:
    found: list[str] = []
    for name in PLUGIN_DIR.findall(line):
        if (root / "plugins" / name).is_dir():
            found.append(f"plugins/{name}/**")
    for p in BACKTICK_PATH.findall(line):
        p = p.rstrip("/")
        if not p or p.startswith("/") or ".." in p.split("/"):
            continue
        if (root / p).is_file():
            found.append(p)
        elif (root / p).is_dir():
            found.append(f"{p}/**")
    return list(dict.fromkeys(found))


def collect(root: Path, repo: str, aliases: Mapping[str, str] | None = None) -> Emit:
    aliases = dict(aliases or {})
    out = Emit()
    path = root / CONTRACTS_MD
    if not path.is_file():
        return out
    out.sources.append(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = list(BLOCK.finditer(text))
    for i, m in enumerate(matches):
        cid = contract_id(repo, m.group(1)[1:])
        line_no = text.count("\n", 0, m.start()) + 1
        body = text[m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        prov = {"source": CONTRACTS_MD.as_posix(), "line": line_no}
        out.records.append(
            ContextRecord(
                record_id=cid,
                record_type="contract",
                title=m.group(2).strip() or m.group(1),
                repo=repo,
                path=f"{CONTRACTS_MD.as_posix()}#{m.group(1)}",
                status="active",
                provenance=prov,
            )
        )
        for role_m in ROLE_LINE.finditer(body):
            role = "producer" if role_m.group("role").lower().startswith(("producer", "owner")) else "consumer"
            for pat in _paths_in(root, role_m.group("val")):
                out.governed.append(GovernedPath(pat, cid, repo, dict(prov, relation=role)))
        for qid, _, _ in find_adr_refs(body, repo, aliases):
            out.relationships.append(Relationship(cid, "refs", qid, prov))
        for tid in find_ticket_refs(body):
            out.relationships.append(Relationship(cid, "tracked_by", tid, prov))
    return out
