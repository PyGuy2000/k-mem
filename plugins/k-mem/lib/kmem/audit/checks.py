"""The four docs checks.

1. docs_adr_refs_resolve       every ``ADR-NNN`` cited bare in this repo has a
                               file under ``decisions/``, unless the citation
                               carries a repo qualifier (``other ADR-104``).
2. docs_adr_index_fresh        ``decisions.md`` equals what ``kmem notes index``
                               would render right now.
3. docs_state_budget           ``STATE.md`` stays under the budget the config
                               sets, measured as chars / 4.
4. context_index_edges_resolve every edge the context resolver compiles points
                               at a compiled record; this is the only check
                               that reads inside ADR headers.

Tolerances come from the repo's ``.claude/kmem_audit.json`` (see
``allowlist``) and are self-expiring. Every check takes ``root`` so tests can
point it at a fixture tree; ``today`` is injectable for the expiry tests.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import Iterable

from ..config import Config, load_config
from ..layout import DECISIONS_DIR, DECISIONS_MD, NOTES_DIR, STATE_MD
from ..notes.decisions_index import render_index
from .allowlist import Allowlist, live, load_allowlist
from .result import CheckResult, bad, ok, skip

SCAN_SUFFIXES = (".md", ".py", ".ts", ".tsx", ".js", ".jsx", ".yaml", ".yml", ".json", ".toml", ".txt")
_SKIP_PARTS = ("node_modules/", "/.venv/", "__pycache__/", "/dist/")
_QUALIFIER_WINDOW = 28


def _today() -> date:
    return date.today()


def tracked_files(root: Path) -> list[str]:
    """Tracked AND untracked-but-not-ignored files, so a local run before
    ``git add`` sees what CI will see."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return out.splitlines()


def adr_numbers_with_files(root: Path) -> set[int]:
    return {
        int(m.group(1))
        for p in (root / DECISIONS_DIR).glob("ADR-*.md")
        if (m := re.match(r"ADR-(\d{3})", p.name))
    }


def qualifier_regex(names: Iterable[str]) -> re.Pattern[str] | None:
    """Matches when a known repo name or alias sits just before ``ADR-NNN``."""
    names = sorted({n for n in names if n}, key=len, reverse=True)
    if not names:
        return None
    alt = "|".join(re.escape(n) for n in names)
    return re.compile(rf"(?<![\w-])(?:{alt})[\s_'’-]*$", re.IGNORECASE)


def local_adr_refs(
    root: Path,
    qualifiers: Iterable[str] = (),
    files: list[str] | None = None,
    skip_prefixes: tuple[str, ...] = (),
) -> dict[int, set[str]]:
    """Map ADR number -> files citing it bare (no repo qualifier)."""
    files = tracked_files(root) if files is None else files
    qual = qualifier_regex(qualifiers)
    refs: dict[int, set[str]] = {}
    for rel in files:
        if not rel.endswith(SCAN_SUFFIXES) or rel.startswith(skip_prefixes):
            continue
        if any(part in f"/{rel}" for part in _SKIP_PARTS):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in re.finditer(r"\bADR-(\d{3})\b", text):
            before = text[max(0, m.start() - _QUALIFIER_WINDOW) : m.start()]
            if qual and qual.search(before):
                continue
            refs.setdefault(int(m.group(1)), set()).add(rel)
    return refs


# --- 1. ADR references resolve --------------------------------------------


def check_adr_refs_resolve(
    root: Path, config: Config | None = None, allow: Allowlist | None = None, today: date | None = None
) -> CheckResult:
    key, title = "docs_adr_refs_resolve", "Every bare ADR-NNN citation resolves to a decisions/ file"
    root = Path(root)
    if not (root / DECISIONS_DIR).is_dir():
        return skip(key, title, "decisions/ not present")
    config = config or load_config()
    allow = allow or load_allowlist(root)
    today = today or _today()
    have = adr_numbers_with_files(root)
    refs = local_adr_refs(root, config.alias_map().keys(), skip_prefixes=allow.skip_prefixes)
    missing = sorted(n for n in refs if n not in have)
    unresolved, tolerated = [], []
    for n in missing:
        (tolerated if live(allow.adr_refs.get(n), today) else unresolved).append(n)
    if unresolved:
        where = "; ".join(f"ADR-{n:03d} in {sorted(refs[n])[0]}" for n in unresolved[:6])
        return bad(key, title, f"{len(unresolved)} ADR number(s) cited with no file and no live allowlist entry: {where}")
    if tolerated:
        first = allow.adr_refs[tolerated[0]]
        return ok(
            key, title,
            f"{len(refs)} cited numbers resolve ({len(tolerated)} tolerated under {first['ticket']} until {first['expires']})",
        )
    return ok(key, title, f"{len(refs)} cited numbers resolve")


# --- 2. index fresh ----------------------------------------------------------


def check_adr_index_fresh(root: Path, config: Config | None = None, allow: Allowlist | None = None, today=None) -> CheckResult:
    key, title = "docs_adr_index_fresh", "decisions.md matches what kmem notes index renders"
    root = Path(root)
    ddir = root / DECISIONS_DIR
    if not ddir.is_dir() or not any(ddir.glob("ADR-*.md")):
        return skip(key, title, "no per-file ADRs under decisions/ (single-file layout or none)")
    try:
        rendered, n_rows, n_files = render_index(root / NOTES_DIR)
    except Exception as exc:  # noqa: BLE001
        return bad(key, title, f"generator failed: {exc}")
    index = root / DECISIONS_MD
    if not index.is_file():
        return bad(key, title, "decisions.md is missing; run kmem notes index")
    if rendered != index.read_text(encoding="utf-8"):
        return bad(key, title, "decisions.md is stale; run kmem notes index")
    return ok(key, title, f"index fresh: {n_rows} headings over {n_files} files")


# --- 3. STATE budget ---------------------------------------------------------


def state_tokens(root: Path) -> int:
    return len((Path(root) / STATE_MD).read_text(encoding="utf-8", errors="replace")) // 4


def check_state_budget(
    root: Path, config: Config | None = None, allow: Allowlist | None = None, today: date | None = None
) -> CheckResult:
    root = Path(root)
    config = config or load_config()
    allow = allow or load_allowlist(root)
    today = today or _today()
    budget = int(config.state_budget_tokens)
    key, title = "docs_state_budget", f"STATE.md under its ~{budget // 1000}K-token budget"
    if not (root / STATE_MD).is_file():
        return skip(key, title, "STATE.md not present")
    tokens = state_tokens(root)
    if tokens <= budget:
        return ok(key, title, f"~{tokens:,} tokens")
    grace = allow.state_grace
    if grace and live(grace, today):
        try:
            ceiling = int(grace.get("ceiling_tokens", 0))
        except (TypeError, ValueError):
            ceiling = 0
        if tokens <= ceiling:
            return ok(
                key, title,
                f"~{tokens:,} tokens, over budget; tolerated under {grace['ticket']} until {grace['expires']}",
            )
    return bad(key, title, f"~{tokens:,} tokens > {budget:,} (prune STATE.md or move detail to key_facts.md)")


# --- 4. context index edges resolve ------------------------------------------


def check_context_index_edges_resolve(
    root: Path, config: Config | None = None, allow: Allowlist | None = None, today: date | None = None
) -> CheckResult:
    """Every relationship the compiler extracts points at a record it also compiled.

    Runs the compiler in-repo only (no other repos, no DevFlow), so the result
    is the same on CI and on a workstation. Cross-repo targets are exempt
    (the other tree is not visible here); ticket targets are exempt.
    """
    from ..context.compiler import Compiler, detect_repo_name
    from ..context.ids import adr_number, split_id
    from ..context.store import SQLiteStore

    key, title = "context_index_edges_resolve", "Every edge the context resolver compiles resolves to a compiled record"
    root = Path(root)
    if not (root / DECISIONS_DIR).is_dir() and not (root / DECISIONS_MD).is_file():
        return skip(key, title, "no decisions/ dir and no decisions.md")
    config = config or load_config()
    allow = allow or load_allowlist(root)
    today = today or _today()
    repo = detect_repo_name(root, config)
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteStore(Path(tmp) / "ctx.sqlite")
        try:
            Compiler(root, repo, store, extra_repos={}, include_devflow=False, aliases=config.alias_map()).build()
            edges = store.unresolved_edges()
            n_edges = len(store.all_relationships())
        finally:
            store.close()
    unresolved: list[str] = []
    tolerated: list[str] = []
    for e in edges:
        target_repo, _ = split_id(e.target_id)
        if e.target_id.startswith("T-") or target_repo != repo:
            continue
        num = adr_number(e.target_id)
        entry = None
        if num is not None:
            entry = allow.context_edges.get(num) or allow.adr_refs.get(num)
        where = f"{e.source_id} -{e.relationship}-> {e.target_id} ({e.provenance.get('source')}:{e.provenance.get('line')})"
        (tolerated if live(entry, today) else unresolved).append(where)
    if unresolved:
        return bad(
            key, title,
            f"{len(unresolved)} edge(s) point at no record and have no live allowlist entry: " + "; ".join(unresolved[:6]),
        )
    return ok(key, title, f"{n_edges} edges resolve" + (f" ({len(tolerated)} tolerated)" if tolerated else ""))


DOCS_CHECKS = [
    check_adr_refs_resolve,
    check_adr_index_fresh,
    check_state_budget,
    check_context_index_edges_resolve,
]


def run_audit(root: Path, config: Config | None = None, today: date | None = None) -> list[CheckResult]:
    root = Path(root)
    config = config or load_config()
    allow = load_allowlist(root)
    return [check(root, config, allow, today) for check in DOCS_CHECKS]
