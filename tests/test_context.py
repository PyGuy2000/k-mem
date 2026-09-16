"""The context resolver, on fixture repos built in ``tmp_path``.

Ported from the original suite with every repo name replaced by fixture
names and the alias table supplied through a ``Config``. The Phase-1 parity
pin stays: for every governed path the resolver's mandatory set is exactly
what ``govmap.required_adrs`` returns.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from kmem.config import Config, load_config
from kmem.context import ContextResolutionService
from kmem.context.compiler import detect_repo_name
from kmem.context.discovery import Coverage, SearchResult, SearchSpan
from kmem.context.ids import adr_id, canonical_repo_name, find_adr_refs, find_ticket_refs
from kmem.govmap import glob_to_regex, load_map, required_adrs

# --- fixture repo ---------------------------------------------------------------

ALIASES = {"app": "my_app", "other": "other_app"}

ADR_001 = """## ADR-001: First decision (app-001)
**Date**: 2026-01-01
**Status**: Accepted
**Depends on**: ADR-002 (the second)
**Ref**: T-1100; extends other ADR-104

### Context
Body prose that mentions ADR-003 and must NOT become an edge.
"""

ADR_002 = """## ADR-002: Second decision (app-002) [SUPERSEDED]
**Date**: 2026-01-02
**Status**: Superseded by ADR-003
**Ref**: T-1101

### Context
"""

ADR_003 = """## ADR-003: Third decision (app-003)
**Date**: 2026-01-03
**Status**: Accepted
**Supersedes**: ADR-002

### Context
"""

CONTRACTS = """---
adr: [ADR-001]
---
# Contracts

## C1 — `foo.table` schema
- **Producer:** plugins/foo (the foo plugin)
- **Consumers:** `src/gateway/bar.py`
- **Change rule:** cross-repo event
- **Compatibility:** backward
See ADR-001.
"""

PLANS = """| ID | Plan | Window | Status | ADRs | Deferred |
|---|---|---|---|---|---|
| P-01 | The first plan | 01-01 → 01-02 | PARKED | app-1..2 (Ph5) | T-1100 parked |
| P-02 | The second plan | 01-03 | LIVE | app-3; other-104 | none |
"""

README = """---
# docssync
source_paths:
  - src/gateway/
adr:
  - app-001
devflow_tickets: [T-1100]
---

# Gateway facts
"""

ADR_MAP = {
    "rules": [
        {"paths": ["src/gateway/**"], "adrs": [1], "topic": "gateway"},
        {"paths": ["plugins/foo/**"], "adrs": [2], "topic": "foo"},
    ]
}


def make_repo(tmp_path: Path, name: str = "my_app", adr_map: dict | None = None) -> Path:
    root = tmp_path / name
    (root / "docs/project_notes/decisions").mkdir(parents=True)
    (root / "docs/individual_readme_files").mkdir(parents=True)
    (root / "src/gateway").mkdir(parents=True)
    (root / "plugins/foo").mkdir(parents=True)
    (root / ".claude").mkdir()
    (root / ".claude/adr_map.json").write_text(json.dumps(adr_map or ADR_MAP), encoding="utf-8")
    (root / "docs/project_notes/decisions/ADR-001-first.md").write_text(ADR_001, encoding="utf-8")
    (root / "docs/project_notes/decisions/ADR-002-second.md").write_text(ADR_002, encoding="utf-8")
    (root / "docs/project_notes/decisions/ADR-003-third.md").write_text(ADR_003, encoding="utf-8")
    (root / "docs/individual_readme_files/data-contracts.md").write_text(CONTRACTS, encoding="utf-8")
    (root / "docs/individual_readme_files/gateway.md").write_text(README, encoding="utf-8")
    (root / "docs/project_notes/plans.md").write_text(PLANS, encoding="utf-8")
    (root / "src/gateway/bar.py").write_text("x = 1\n", encoding="utf-8")
    (root / "plugins/foo/plugin.py").write_text("x = 1\n", encoding="utf-8")
    return root


def make_config(tmp_path: Path, **extra) -> Config:
    cfg = Config.defaults(tmp_path / "kmem-data")
    cfg.aliases = dict(ALIASES)
    for k, v in extra.items():
        setattr(cfg, k, v)
    return cfg.apply_env()


@pytest.fixture
def fx(tmp_path):
    root = make_repo(tmp_path)
    svc = ContextResolutionService(root=root, db_path=tmp_path / "idx.sqlite", extra_repos={}, config=make_config(tmp_path))
    svc.build_index()
    yield svc, root
    svc.close()


# --- 1. governed paths resolve governing ADRs ----------------------------------------


def test_governed_path_resolves_governing_adrs(fx):
    svc, _ = fx
    packet = svc.resolve_context("edit", "src/gateway/bar.py")
    assert packet.mandatory_ids == ["my_app:ADR-001"]
    relations = {(a.relation, a.record.record_id) for a in packet.advisory}
    assert ("consumer", "my_app:C1") in relations
    assert ("documents", "my_app:DOC-gateway") in relations
    assert ("depends_on", "my_app:ADR-002") in relations


def test_ungoverned_path_has_no_mandatory(fx):
    svc, _ = fx
    assert svc.resolve_context("edit", "README.md").mandatory == []


# --- 2. parity with the map ----------------------------------------------------------


def test_mandatory_equals_required_adrs_for_every_rule(fx):
    svc, root = fx
    samples = {"src/gateway/bar.py", "plugins/foo/plugin.py", "README.md"}
    for rule in load_map(root):
        for pat in rule["paths"]:
            assert any(glob_to_regex(pat).match(s) for s in samples), pat
    for sample in sorted(samples):
        expected = {adr_id("my_app", n) for n in required_adrs(root, sample)}
        assert set(svc.resolve_context("edit", sample).mandatory_ids) == expected, sample


# --- 3. relationship targets resolve ---------------------------------------------------


def test_fixture_edges_all_resolve_except_the_unregistered_repo(fx):
    svc, _ = fx
    unresolved = [e for e in svc.store.unresolved_edges() if not e.target_id.startswith("T-")]
    assert {e.target_id for e in unresolved} == {"other_app:ADR-104"}


def test_body_prose_does_not_become_an_edge(fx):
    svc, _ = fx
    targets = {e.target_id for e in svc.store.all_relationships() if e.source_id == "my_app:ADR-001"}
    assert "my_app:ADR-003" not in targets
    assert "my_app:ADR-002" in targets and "T-1100" in targets


# --- 4. provenance points at real lines ------------------------------------------------


def test_provenance_points_at_existing_lines(fx):
    svc, root = fx
    for rec in svc.store.all_records():
        src = rec.provenance.get("source")
        assert src, rec.record_id
        path = Path(src) if Path(src).is_absolute() else root / src
        assert path.is_file(), (rec.record_id, src)
        line = rec.provenance.get("line")
        if line:
            n_lines = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            assert 1 <= int(line) <= n_lines, (rec.record_id, src, line)


# --- 5 + 8. delete and rebuild gives the same packet -----------------------------------


def test_delete_and_rebuild_gives_identical_packet(fx, tmp_path):
    svc, root = fx
    before = svc.resolve_context("edit", "src/gateway/bar.py").to_dict()
    svc.close()
    (tmp_path / "idx.sqlite").unlink()
    svc2 = ContextResolutionService(root=root, db_path=tmp_path / "idx.sqlite", extra_repos={}, config=make_config(tmp_path))
    try:
        after = svc2.resolve_context("edit", "src/gateway/bar.py").to_dict()
    finally:
        svc2.close()
    assert before == after


# --- 6. stale index is detectable ------------------------------------------------------


def test_stale_index_detected_after_source_change(fx):
    svc, root = fx
    assert svc.compiler.is_stale() is False
    adr = root / "docs/project_notes/decisions/ADR-001-first.md"
    adr.write_text(adr.read_text(encoding="utf-8") + "\nmore prose\n", encoding="utf-8")
    assert svc.compiler.is_stale() is True
    svc.ensure_index()
    assert svc.compiler.is_stale() is False


# --- 7. determinism ------------------------------------------------------------------


def test_same_request_same_revision_same_receipt(fx):
    svc, _ = fx
    a = svc.resolve_context("edit", "src/gateway/bar.py")
    b = svc.resolve_context("edit", "src/gateway/bar.py")
    assert a.receipt_id == b.receipt_id and a.receipt_id.startswith("CTX-")
    assert a.index_revision == svc.build_index()
    assert svc.resolve_context("write", "src/gateway/bar.py").receipt_id != a.receipt_id


# --- 9. cross-repo identities do not collide --------------------------------------------


def test_two_repos_with_adr_001_get_distinct_ids(tmp_path):
    root = make_repo(tmp_path)
    other = tmp_path / "other_app" / "docs" / "project_notes"
    other.mkdir(parents=True)
    (other / "decisions.md").write_text("## ADR-001: An other decision\n**Status**: Accepted\n", encoding="utf-8")
    svc = ContextResolutionService(
        root=root, db_path=tmp_path / "idx.sqlite",
        extra_repos={"other_app": tmp_path / "other_app"}, config=make_config(tmp_path),
    )
    try:
        svc.build_index()
        a = svc.store.get_record("my_app:ADR-001")
        b = svc.store.get_record("other_app:ADR-001")
        assert a and b and a.title != b.title
        assert svc.resolve_context("edit", "src/gateway/bar.py").mandatory_ids == ["my_app:ADR-001"]
    finally:
        svc.close()


def test_config_repos_are_the_default_extra_repos(tmp_path, write_config):
    root = make_repo(tmp_path)
    other = tmp_path / "other_app" / "docs" / "project_notes"
    other.mkdir(parents=True)
    (other / "decisions.md").write_text("## ADR-104: The cited decision\n**Status**: Accepted\n", encoding="utf-8")
    write_config(repos={"my_app": str(root), "other_app": str(tmp_path / "other_app")}, aliases=ALIASES)
    svc = ContextResolutionService(root=root, db_path=tmp_path / "idx.sqlite")
    try:
        svc.build_index()
        assert svc.repo == "my_app"
        assert svc.store.get_record("other_app:ADR-104") is not None
        unresolved = [e for e in svc.store.unresolved_edges() if not e.target_id.startswith("T-")]
        assert unresolved == []
    finally:
        svc.close()


def test_reference_forms_normalise_to_qualified_ids():
    aliases = {"app": "my_app", "other": "other_app", "svc": "svc-repo"}
    got = [q for q, _, _ in find_adr_refs(
        "see ADR-042, app-043, other-085, other ADR-104, ADR-114/115, svc ADR-060, snapp-9", "my_app", aliases
    )]
    assert got == [
        "my_app:ADR-042",
        "my_app:ADR-043",
        "other_app:ADR-085",
        "other_app:ADR-104",
        "my_app:ADR-114",
        "my_app:ADR-115",
        "svc-repo:ADR-060",
    ]
    assert adr_id("my_app", 7) == "my_app:ADR-007"
    assert [q for q, _, _ in find_adr_refs("ADR-001 and app-002", "x")] == ["x:ADR-001"]  # no aliases: bare only
    assert find_ticket_refs("T-1100, T-1100 again, T-12") == ["T-1100"]


def test_checkout_dir_name_does_not_change_ids():
    known = {"my_app", "svc-repo"}
    assert canonical_repo_name("my-app", known) == "my_app"
    assert canonical_repo_name("my_app", known) == "my_app"
    assert canonical_repo_name("svc_repo", known) == "svc-repo"
    assert canonical_repo_name("some-other-repo", known) == "some-other-repo"
    assert canonical_repo_name("some-other-repo") == "some-other-repo"


# --- 10. semantic retrieval cannot determine mandatory context --------------------------


class _PerfectScoreBackend:
    def find_context(self, intent, scope="repo", k=8):
        return SearchResult(
            intent=intent, scope=scope,
            spans=[SearchSpan(path="docs/project_notes/decisions/ADR-003-third.md", score=1.0, why="ADR-003")],
            coverage=Coverage(structural=1.0, semantic=1.0, structurally_complete=True, semantically_sufficient=True),
        )


def test_semantic_result_never_becomes_mandatory(tmp_path):
    root = make_repo(tmp_path)
    svc = ContextResolutionService(
        root=root, db_path=tmp_path / "idx.sqlite", extra_repos={},
        discovery=_PerfectScoreBackend(), config=make_config(tmp_path),
    )
    try:
        svc.build_index()
        found = svc.find_context("everything about the gateway")
        assert found.spans and found.spans[0].score == 1.0
        packet = svc.resolve_context("edit", "src/gateway/bar.py")
        assert packet.mandatory_ids == ["my_app:ADR-001"]
        assert "my_app:ADR-003" not in packet.mandatory_ids
    finally:
        svc.close()


# --- collisions -----------------------------------------------------------------------


def test_superseded_mandatory_and_parked_plan_are_collisions(fx):
    svc, _ = fx
    packet = svc.resolve_context("edit", "plugins/foo/plugin.py")  # governed by ADR-002 (superseded)
    kinds = {(c.relation, c.record.record_id) for c in packet.collisions}
    assert ("superseded", "my_app:ADR-002") in kinds
    assert ("superseded_by", "my_app:ADR-003") in kinds
    assert ("parked_plan", "my_app:P-01") in kinds


def test_shadow_compare_classifications(fx):
    svc, _ = fx
    assert svc.shadow_compare("src/gateway/bar.py", {1})["classification"] == "MATCH"
    assert svc.shadow_compare("src/gateway/bar.py", set())["classification"] == "RESOLVER_EXTRA"
    assert svc.shadow_compare("src/gateway/bar.py", {1, 2})["classification"] == "EXISTING_EXTRA"
    assert svc.shadow_compare("src/gateway/bar.py", {2})["classification"] == "CONFLICT"


# --- the single-file ADR layout: decisions.md sections are first-class records ----------

SINGLE_FILE_DECISIONS = """# Decisions

## ADR-001: First other decision (other-001)
**Date**: 2026-01-01
**Status**: Accepted
**Ref**: T-1100; extends app-107

### Context
Body prose mentioning ADR-002 that must NOT become an edge.

## ADR-002: Second other decision [SUPERSEDED]
**Status**: Superseded by ADR-003

## ADR-003: Third other decision
**Status**: Accepted
**Supersedes**: ADR-002

## ADR-003: A duplicate heading that must be ignored
**Status**: Accepted
"""


def make_single_file_repo(tmp_path: Path, name: str = "other_app") -> Path:
    root = tmp_path / name
    (root / "docs/project_notes").mkdir(parents=True)
    (root / "config").mkdir()
    (root / ".claude").mkdir()
    (root / "config/authored_semantics.yaml").write_text("x: 1\n", encoding="utf-8")
    (root / ".claude/adr_map.json").write_text(
        json.dumps({"rules": [{"paths": ["config/**"], "adrs": [1, 2], "topic": "semantics"}]}), encoding="utf-8"
    )
    (root / "docs/project_notes/decisions.md").write_text(SINGLE_FILE_DECISIONS, encoding="utf-8")
    return root


def test_single_file_decisions_md_is_a_first_class_layout(tmp_path):
    root = make_single_file_repo(tmp_path)
    svc = ContextResolutionService(root=root, db_path=tmp_path / "idx.sqlite", extra_repos={}, config=make_config(tmp_path))
    try:
        svc.build_index()
        rec = svc.store.get_record("other_app:ADR-001")
        assert rec and rec.path == "docs/project_notes/decisions.md"
        assert rec.provenance == {"source": "docs/project_notes/decisions.md", "line": 3}
        assert svc.store.get_record("other_app:ADR-003").provenance["line"] == 14  # first heading wins
        edges = {(e.source_id, e.relationship, e.target_id) for e in svc.store.all_relationships()}
        assert ("other_app:ADR-001", "refs", "my_app:ADR-107") in edges
        assert ("other_app:ADR-001", "tracked_by", "T-1100") in edges
        assert ("other_app:ADR-003", "supersedes", "other_app:ADR-002") in edges
        assert not any(t == "other_app:ADR-002" and s == "other_app:ADR-001" for s, _, t in edges)
        packet = svc.resolve_context("edit", "config/authored_semantics.yaml")
        assert packet.mandatory_ids == ["other_app:ADR-001", "other_app:ADR-002"]
        kinds = {(c.relation, c.record.record_id) for c in packet.collisions}
        assert ("superseded", "other_app:ADR-002") in kinds
        assert ("superseded_by", "other_app:ADR-003") in kinds
        assert svc.shadow_compare("config/authored_semantics.yaml", {1, 2})["classification"] == "MATCH"
        assert svc.shadow_compare("config/authored_semantics.yaml", {1, 2})["repo"] == "other_app"
    finally:
        svc.close()


# --- repo identity --------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-C", str(cwd), *args],
        check=True, capture_output=True, text=True, timeout=30,
    )


def test_worktree_checkout_resolves_to_the_canonical_repo_id(tmp_path):
    """The folder name of a worktree is its branch; the id must still be the repo's."""
    root = make_repo(tmp_path)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    wt = tmp_path / "worktrees" / "t1-worktree"
    _git(root, "worktree", "add", "-q", "-b", "admin/t1-x", str(wt))
    assert wt.name != "my_app"
    svc = ContextResolutionService(root=wt, db_path=tmp_path / "idx.sqlite", extra_repos={}, config=make_config(tmp_path))
    try:
        assert svc.repo == "my_app"
        svc.build_index()
        assert svc.resolve_context("edit", "src/gateway/bar.py").mandatory_ids == ["my_app:ADR-001"]
    finally:
        svc.close()


def test_repo_id_falls_back_to_the_folder_name_without_git(tmp_path):
    cfg = make_config(tmp_path)
    assert detect_repo_name(make_repo(tmp_path), cfg) == "my_app"
    (tmp_path / "my-app" / ".claude").mkdir(parents=True)
    (tmp_path / "my-app" / ".claude/adr_map.json").write_text('{"rules": []}', encoding="utf-8")
    assert detect_repo_name(tmp_path / "my-app", cfg) == "my_app"  # known through the alias table


def test_map_repo_key_and_configured_path_override_detection(tmp_path):
    cfg = make_config(tmp_path)
    root = make_repo(tmp_path, adr_map={"repo": "named", "rules": []})
    assert detect_repo_name(root, cfg) == "named"
    root2 = make_repo(tmp_path / "x")
    cfg.repos = {"configured": root2}
    assert detect_repo_name(root2, cfg) == "configured"


def test_service_without_a_map_above_cwd_is_an_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        ContextResolutionService(config=load_config())
