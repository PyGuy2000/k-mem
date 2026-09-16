"""The harness-neutral boundary.

    svc = ContextResolutionService()            # finds the repo root from cwd
    packet = svc.resolve_context("edit", "src/billing/invoice.py")
    svc.shadow_compare("src/billing/invoice.py", {1, 2})

The index lives at ``<index_dir>/<repo>.sqlite`` (``index_dir`` from the
config file) and is rebuilt when ``Compiler.is_stale()`` says so. Other
repos' ADR titles come from the config's ``repos`` table.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ..config import Config, load_config
from ..govmap import find_repo_root, glob_to_regex
from .compiler import Compiler, detect_repo_name
from .discovery import DiscoveryBackend, NullDiscoveryBackend, SearchResult
from .ids import adr_number, split_id
from .models import ContextPacket, ResolutionRequest
from .resolver import ContextResolver
from .store import SQLiteStore

__all__ = ["ContextResolutionService", "find_repo_root"]


class ContextResolutionService:
    def __init__(
        self,
        root: Path | None = None,
        repo: str | None = None,
        db_path: Path | None = None,
        extra_repos: Mapping[str, Path] | None = None,
        discovery: DiscoveryBackend | None = None,
        config: Config | None = None,
    ):
        self.config = config or load_config()
        found = Path(root) if root else find_repo_root()
        if found is None:
            raise FileNotFoundError("no .claude/adr_map.json above the working directory")
        self.root = found.resolve()
        self.repo = repo or detect_repo_name(self.root, self.config)
        self.db_path = Path(db_path) if db_path else self.config.index_dir / f"{self.repo}.sqlite"
        self.store = SQLiteStore(self.db_path)
        self.compiler = Compiler(
            self.root, self.repo, self.store,
            extra_repos=extra_repos if extra_repos is not None else self.config.repos,
            aliases=self.config.alias_map(),
            devflow_state=self.config.devflow_state,
        )
        self.resolver = ContextResolver(self.store, glob_to_regex)
        self.discovery: DiscoveryBackend = discovery or NullDiscoveryBackend()

    # --- index --------------------------------------------------------------------

    def build_index(self) -> str:
        return self.compiler.build()

    def ensure_index(self, force: bool = False) -> str:
        if force or self.compiler.is_stale():
            return self.compiler.build()
        return self.store.get_meta("index_revision") or self.compiler.build()

    def status(self) -> dict:
        return {
            "repo": self.repo,
            "root": str(self.root),
            "db_path": str(self.db_path),
            "index_revision": self.store.get_meta("index_revision"),
            "source_revision": self.store.get_meta("source_revision"),
            "built_at": self.store.get_meta("built_at"),
            "record_count": self.store.get_meta("record_count"),
            "devflow_available": self.store.get_meta("devflow_available") == "1",
            "stale": self.compiler.is_stale(),
        }

    # --- Path A ------------------------------------------------------------------

    def resolve_context(self, operation: str, target: str, repo: str | None = None) -> ContextPacket:
        self.ensure_index()
        return self.resolver.resolve(ResolutionRequest(operation, target, repo or self.repo))

    def shadow_compare(self, rel_path: str, existing: set[int], operation: str = "edit") -> dict:
        """Compare the read gate's ADR numbers with the resolver's mandatory set."""
        packet = self.resolve_context(operation, rel_path)
        resolved: set[int] = set()
        for rid in packet.mandatory_ids:
            repo, _ = split_id(rid)
            n = adr_number(rid)
            if repo == self.repo and n is not None:
                resolved.add(n)
        existing = set(existing)
        if resolved == existing:
            cls = "MATCH"
        elif existing < resolved:
            cls = "RESOLVER_EXTRA"
        elif resolved < existing:
            cls = "EXISTING_EXTRA"
        else:
            cls = "CONFLICT"
        return {
            "repo": self.repo,
            "existing": sorted(existing),
            "resolver_mandatory": sorted(resolved),
            "resolver_advisory": [f"{a.relation}:{a.record.record_id}" for a in packet.advisory],
            "collisions": [f"{c.relation}:{c.record.record_id}" for c in packet.collisions],
            "classification": cls,
            "receipt": packet.receipt_id,
            "source_revision": packet.source_revision,
            "index_revision": packet.index_revision,
        }

    # --- Path B (advisory, null by default) ---------------------------------------

    def find_context(self, intent: str, scope: str = "repo", k: int = 8) -> SearchResult:
        result = self.discovery.find_context(intent=intent, scope=scope, k=k)
        result.index_revision = self.store.get_meta("index_revision")
        return result

    def close(self) -> None:
        self.store.close()
