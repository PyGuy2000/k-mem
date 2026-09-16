"""Compile the authored sources into the disposable index.

    adr_map.json + ADR headers + data-contracts.md + plans.md + fact-doc
    frontmatter (+ the DevFlow state file when present)
        -> adapters -> SQLiteStore

``index_revision`` is a content hash of every source file read, so a stale
index is detected by re-hashing (``is_stale``) and two builds over identical
sources give identical revisions on any machine. ``source_revision`` is the
repo's git HEAD.
"""

from __future__ import annotations

import hashlib
import subprocess
import time
from pathlib import Path
from typing import Mapping

from ..config import Config, load_config
from ..govmap import map_repo_name
from .adapters import Emit, adr_map, adrs, contracts, devflow, facts, plans
from .ids import canonical_repo_name
from .store import SQLiteStore


def git_head(root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _git_out(root: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def detect_repo_name(root: Path, config: Config | None = None) -> str:
    """Canonical repo id for a checkout, worktree-safe.

    In order: the ``repo`` the map names for itself; the configured repo
    whose path is this checkout; the parent of the git common dir (a
    worktree's folder is named after its branch, so the folder name is the
    wrong id there); the origin URL basename; the folder name (a fixture
    with no git at all). Each is normalised against the configured names.
    """
    root = Path(root)
    config = config or load_config()
    known = config.known_repos()
    named = map_repo_name(root)
    if named:
        return canonical_repo_name(named, known)
    configured = config.repo_for_root(root)
    if configured:
        return configured
    common = _git_out(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common:
        common_path = Path(common)
        if common_path.name == ".git":
            return canonical_repo_name(common_path.parent.name, known)
    url = _git_out(root, "remote", "get-url", "origin")
    if url:
        name = url.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
        if name.endswith(".git"):
            name = name[:-4]
        if name:
            return canonical_repo_name(name, known)
    return canonical_repo_name(root.name, known)


def fingerprint(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(set(paths), key=str):
        h.update(str(p).encode())
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(b"<missing>")
    return h.hexdigest()[:16]


class Compiler:
    def __init__(
        self,
        root: Path,
        repo: str,
        store: SQLiteStore,
        extra_repos: Mapping[str, Path] | None = None,
        include_devflow: bool = True,
        aliases: Mapping[str, str] | None = None,
        devflow_state: Path | None = None,
    ):
        self.include_devflow = include_devflow
        self.root = Path(root)
        self.repo = repo
        self.store = store
        self.extra_repos = {k: Path(v) for k, v in (extra_repos or {}).items() if k != repo}
        self.aliases = dict(aliases or {})
        self.devflow_state = devflow_state

    def collect(self) -> tuple[Emit, bool]:
        emit = Emit()
        emit.extend(adr_map.collect(self.root, self.repo))
        emit.extend(adrs.collect_current(self.root, self.repo, self.aliases))
        for name, base in sorted(self.extra_repos.items()):
            if base.is_dir():
                emit.extend(adrs.collect_other(name, base))
        emit.extend(contracts.collect(self.root, self.repo, self.aliases))
        emit.extend(plans.collect(self.root, self.repo, self.aliases))
        emit.extend(facts.collect(self.root, self.repo, self.aliases))
        if not self.include_devflow:
            return emit, False
        referenced = {e.target_id for e in emit.relationships if e.target_id.startswith("T-")}
        tickets, available = devflow.collect(referenced, self.devflow_state)
        emit.extend(tickets)
        return emit, available

    def source_files(self) -> list[Path]:
        emit, _ = self.collect()
        return emit.sources

    def build(self) -> str:
        emit, devflow_available = self.collect()
        revision = fingerprint(emit.sources)
        meta = {
            "repo": self.repo,
            "root": str(self.root),
            "index_revision": revision,
            "source_revision": git_head(self.root),
            "devflow_available": "1" if devflow_available else "0",
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "record_count": str(len(emit.records)),
        }
        self.store.replace_all(emit.records, emit.relationships, emit.governed, meta)
        return revision

    def is_stale(self) -> bool:
        current = self.store.get_meta("index_revision")
        if not current:
            return True
        if self.store.get_meta("source_revision") != git_head(self.root):
            return True
        return fingerprint(self.source_files()) != current
