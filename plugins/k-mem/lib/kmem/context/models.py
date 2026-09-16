"""Data shapes for the resolver. Stdlib only."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContextRecord:
    """One retrievable unit: an ADR, a contract, a plan row, a fact doc, a ticket.

    ``record_id`` is repo-qualified (``my_app:ADR-042``) except for tickets,
    which are global (``T-1042``). ``provenance`` says where the record was
    read from: at least ``source`` (repo-relative or absolute path) and,
    where known, ``line``.
    """

    record_id: str
    record_type: str  # adr | contract | plan | fact | ticket
    title: str
    repo: str | None = None
    path: str | None = None
    status: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Relationship:
    source_id: str
    relationship: str
    target_id: str
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GovernedPath:
    """A glob (the map's dialect: ``**``, ``*``, ``?``) that a record governs."""

    path_pattern: str
    record_id: str
    repo: str
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolutionRequest:
    operation: str
    target: str
    repo: str | None = None


@dataclass
class AdvisoryRecord:
    relation: str
    record: ContextRecord
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"relation": self.relation, "record": self.record.to_dict(), "provenance": self.provenance}


@dataclass
class ContextPacket:
    request: ResolutionRequest
    mandatory: list[ContextRecord] = field(default_factory=list)
    advisory: list[AdvisoryRecord] = field(default_factory=list)
    collisions: list[AdvisoryRecord] = field(default_factory=list)
    receipt_id: str | None = None
    source_revision: str | None = None
    index_revision: str | None = None

    @property
    def mandatory_ids(self) -> list[str]:
        return [r.record_id for r in self.mandatory]

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.request.operation,
            "target": self.request.target,
            "repo": self.request.repo,
            "mandatory": [r.to_dict() for r in self.mandatory],
            "advisory": [a.to_dict() for a in self.advisory],
            "collisions": [c.to_dict() for c in self.collisions],
            "receipt_id": self.receipt_id,
            "source_revision": self.source_revision,
            "index_revision": self.index_revision,
        }
