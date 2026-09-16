"""Adapters: each reads ONE authored source the project already keeps and
emits records, edges and governed paths with provenance.

None of them owns a schema. They parse what is there; a change to the source
format is a change here, never a new file to maintain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..models import ContextRecord, GovernedPath, Relationship


@dataclass
class Emit:
    records: list[ContextRecord] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    governed: list[GovernedPath] = field(default_factory=list)
    sources: list[Path] = field(default_factory=list)

    def extend(self, other: "Emit") -> None:
        self.records.extend(other.records)
        self.relationships.extend(other.relationships)
        self.governed.extend(other.governed)
        self.sources.extend(other.sources)


def rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)
