"""Advisory discovery seam, kept as a null backend.

Search backends (a BM25 index, a code graph, a session memory) already exist
as MCP tools; this package does not build one. The Protocol stays so that a
facade over such a tool has a typed place to land, and so the test
``test_semantic_result_never_becomes_mandatory`` has something to fake.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol


@dataclass
class SearchSpan:
    path: str
    start_line: int | None = None
    end_line: int | None = None
    text: str | None = None
    why: str | None = None
    score: float | None = None

    def to_dict(self):
        return asdict(self)


@dataclass
class Coverage:
    structural: float | None = None
    semantic: float | None = None
    structurally_complete: bool | None = None
    semantically_sufficient: bool | None = None

    def to_dict(self):
        return asdict(self)


@dataclass
class SearchResult:
    intent: str
    scope: str
    spans: list[SearchSpan] = field(default_factory=list)
    coverage: Coverage = field(default_factory=Coverage)
    index_revision: str | None = None

    def to_dict(self):
        return {
            "intent": self.intent,
            "scope": self.scope,
            "spans": [s.to_dict() for s in self.spans],
            "coverage": self.coverage.to_dict(),
            "index_revision": self.index_revision,
        }


class DiscoveryBackend(Protocol):
    """Advisory only. Its output never reaches ``ContextPacket.mandatory``."""

    def find_context(self, intent: str, scope: str = "repo", k: int = 8) -> SearchResult: ...


class NullDiscoveryBackend:
    def find_context(self, intent: str, scope: str = "repo", k: int = 8) -> SearchResult:
        return SearchResult(
            intent=intent,
            scope=scope,
            spans=[],
            coverage=Coverage(structural=None, semantic=0.0, structurally_complete=None, semantically_sufficient=False),
        )
