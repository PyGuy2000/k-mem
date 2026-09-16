"""Deterministic context resolution.

Given an intended operation on a repo-relative path, return the context
packet: the records that must be read first (mandatory), the records one
explicit relation away (advisory, labelled), collisions, provenance, both
revisions and a receipt.

Rules this package keeps:

- mandatory comes only from explicit project relationships: exactly the set
  ``.claude/adr_map.json`` names for the path;
- nothing here is authored: every record and edge compiles from files the
  project already keeps; the SQLite index is disposable;
- standard library only, so a hook can import it from any ``python3``.

Entry point: ``ContextResolutionService`` in ``service.py``; CLI: ``kmem resolve``.
"""

from .models import ContextPacket, ContextRecord, ResolutionRequest
from .service import ContextResolutionService, find_repo_root

__all__ = [
    "ContextPacket",
    "ContextRecord",
    "ContextResolutionService",
    "ResolutionRequest",
    "find_repo_root",
]
