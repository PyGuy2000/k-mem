"""Path -> governing ADR, read through ``kmem.govmap``.

The map has one meaning, defined in ``govmap``; the read gate uses the same
functions, so the resolver and the gate can never disagree about what a
pattern means. These rows are the ONLY source of mandatory records.
"""

from __future__ import annotations

from pathlib import Path

from ...govmap import load_map
from ...layout import MAP_REL
from ..ids import adr_id
from ..models import GovernedPath
from . import Emit


def collect(root: Path, repo: str) -> Emit:
    out = Emit()
    map_path = root / MAP_REL
    if not map_path.is_file():
        return out
    out.sources.append(map_path)
    for i, rule in enumerate(load_map(root)):
        prov = {"source": MAP_REL.as_posix(), "rule_index": i, "topic": rule.get("topic", "")}
        for pat in rule.get("paths", []):
            for n in rule.get("adrs", []):
                out.governed.append(GovernedPath(pat, adr_id(repo, n), repo, dict(prov, mandatory=True)))
    return out
