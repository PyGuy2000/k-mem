"""Proof of red for the four docs checks.

Each check is driven against a fixture tree where the violation is present
and must FAIL, then against a clean tree and must PASS. A check that cannot
go red here is not a check.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

from kmem.audit import (
    DOCS_CHECKS,
    check_adr_index_fresh,
    check_adr_refs_resolve,
    check_context_index_edges_resolve,
    check_state_budget,
    run_audit,
)
from kmem.audit.allowlist import Allowlist, expired, load_allowlist
from kmem.config import Config
from kmem.notes import write_index

ADR = "docs/project_notes/decisions/ADR-102-desk-feeds.md"
TODAY = date(2026, 9, 16)


def _git_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    return root


def _cfg(tmp_path: Path, **extra) -> Config:
    cfg = Config.defaults(tmp_path / "kmem-data")
    cfg.aliases = {"other": "other_app", "svc": "svc"}
    for k, v in extra.items():
        setattr(cfg, k, v)
    return cfg.apply_env()


def _allow(root: Path, **doc) -> None:
    (root / ".claude").mkdir(exist_ok=True)
    (root / ".claude/kmem_audit.json").write_text(json.dumps(doc), encoding="utf-8")


# --- 1. ADR refs resolve -------------------------------------------------------


def test_red_bare_citation_with_no_file_fails(tmp_path):
    root = _git_repo(tmp_path, {ADR: "## ADR-102\n", "README.md": "see ADR-042 for the data bus\n"})
    r = check_adr_refs_resolve(root, _cfg(tmp_path), today=TODAY)
    assert r.status == "fail" and "ADR-042" in r.detail and "README.md" in r.detail


def test_green_qualified_and_resolving_citations_pass(tmp_path):
    root = _git_repo(
        tmp_path,
        {ADR: "## ADR-102\n", "README.md": "see ADR-102, and other ADR-104 (another repo), svc ADR-042\n"},
    )
    r = check_adr_refs_resolve(root, _cfg(tmp_path), today=TODAY)
    assert r.status == "pass", r.detail


def test_red_unknown_qualifier_still_counts_as_local(tmp_path):
    root = _git_repo(tmp_path, {ADR: "## ADR-102\n", "README.md": "see nobody ADR-042\n"})
    assert check_adr_refs_resolve(root, _cfg(tmp_path), today=TODAY).status == "fail"


def test_red_allowlist_entry_stops_protecting_after_expiry(tmp_path):
    root = _git_repo(tmp_path, {ADR: "## ADR-102\n", "README.md": "see ADR-097\n"})
    _allow(root, adr_refs={"97": {"ticket": "T-1043", "expires": "2026-10-15"}})
    cfg = _cfg(tmp_path)
    assert check_adr_refs_resolve(root, cfg, today=date(2026, 10, 1)).status == "pass"
    assert check_adr_refs_resolve(root, cfg, today=date(2026, 10, 16)).status == "fail"


def test_red_allowlist_entry_without_ticket_never_protects(tmp_path):
    root = _git_repo(tmp_path, {ADR: "## ADR-102\n", "README.md": "see ADR-097\n"})
    _allow(root, adr_refs={"97": {"expires": "2099-01-01"}})
    assert check_adr_refs_resolve(root, _cfg(tmp_path), today=TODAY).status == "fail"
    assert expired({"ticket": "T-1000"}, TODAY) and expired({"ticket": "", "expires": "2099-01-01"}, TODAY)


def test_skip_prefixes_and_untracked_files_are_seen(tmp_path):
    root = _git_repo(tmp_path, {ADR: "## ADR-102\n", "tests/test_x.py": "# cites ADR-999 on purpose\n"})
    assert check_adr_refs_resolve(root, _cfg(tmp_path), today=TODAY).status == "pass"
    (root / "notes.md").write_text("see ADR-500\n", encoding="utf-8")  # untracked, not yet added
    assert check_adr_refs_resolve(root, _cfg(tmp_path), today=TODAY).status == "fail"


def test_skip_when_no_decisions_dir(tmp_path):
    root = _git_repo(tmp_path, {"README.md": "see ADR-042\n"})
    assert check_adr_refs_resolve(root, _cfg(tmp_path), today=TODAY).status == "skip"


# --- 2. index fresh -------------------------------------------------------------


def _notes_repo(tmp_path: Path) -> Path:
    root = _git_repo(
        tmp_path,
        {
            "docs/project_notes/decisions/ADR-001-one.md": "## ADR-001: One\n**Status**: Accepted\n**Date**: 2026-01-01\n",
            "docs/project_notes/decisions/ADR-002-two.md": "## ADR-002: Two\n**Status**: Proposed\n",
        },
    )
    write_index(root / "docs/project_notes")
    return root


def test_green_index_fresh(tmp_path):
    r = check_adr_index_fresh(_notes_repo(tmp_path), _cfg(tmp_path))
    assert r.status == "pass", r.detail


def test_red_index_stale_after_an_adr_is_added(tmp_path):
    root = _notes_repo(tmp_path)
    ghost = "ADR-" + "999"  # built at run time so this file never cites a number with no ADR
    (root / f"docs/project_notes/decisions/{ghost}-new.md").write_text(f"## {ghost}: New [ACCEPTED]\n", encoding="utf-8")
    r = check_adr_index_fresh(root, _cfg(tmp_path))
    assert r.status == "fail" and "stale" in r.detail


def test_red_index_missing(tmp_path):
    root = _notes_repo(tmp_path)
    (root / "docs/project_notes/decisions.md").unlink()
    r = check_adr_index_fresh(root, _cfg(tmp_path))
    assert r.status == "fail" and "missing" in r.detail


def test_skip_index_in_single_file_layout(tmp_path):
    root = _git_repo(tmp_path, {"docs/project_notes/decisions.md": "## ADR-001: One\n"})
    assert check_adr_index_fresh(root, _cfg(tmp_path)).status == "skip"


# --- 3. STATE budget -------------------------------------------------------------


def test_red_state_over_budget_and_no_grace_fails(tmp_path):
    root = _git_repo(tmp_path, {"docs/project_notes/STATE.md": "x" * (4 * 19_000)})
    assert check_state_budget(root, _cfg(tmp_path), today=TODAY).status == "fail"


def test_green_state_within_grace_until_expiry(tmp_path):
    root = _git_repo(tmp_path, {"docs/project_notes/STATE.md": "x" * (4 * 16_000)})
    _allow(root, state_grace={"ceiling_tokens": 18_000, "ticket": "T-1044", "expires": "2026-09-30"})
    cfg = _cfg(tmp_path)
    assert check_state_budget(root, cfg, today=date(2026, 9, 20)).status == "pass"
    assert check_state_budget(root, cfg, today=date(2026, 10, 1)).status == "fail"


def test_green_state_under_budget_and_budget_from_config(tmp_path):
    root = _git_repo(tmp_path, {"docs/project_notes/STATE.md": "x" * 4_000})
    assert check_state_budget(root, _cfg(tmp_path), today=TODAY).status == "pass"
    assert check_state_budget(root, _cfg(tmp_path, state_budget_tokens=500), today=TODAY).status == "fail"


def test_skip_state_when_absent(tmp_path):
    assert check_state_budget(_git_repo(tmp_path, {"README.md": ""}), _cfg(tmp_path)).status == "skip"


# --- 4. context index edges resolve ----------------------------------------------


def test_red_header_edge_to_a_missing_adr_fails(tmp_path):
    root = _git_repo(
        tmp_path,
        {"docs/project_notes/decisions/ADR-001-x.md": "## ADR-001: x\n**Status**: Accepted\n**Depends on**: ADR-009 (never written)\n"},
    )
    r = check_context_index_edges_resolve(root, _cfg(tmp_path), today=TODAY)
    assert r.status == "fail" and "ADR-009" in r.detail


def test_green_edges_resolve_and_cross_repo_and_tickets_are_exempt(tmp_path):
    root = _git_repo(
        tmp_path,
        {
            "docs/project_notes/decisions/ADR-001-x.md": (
                "## ADR-001: x\n**Status**: Accepted\n**Depends on**: ADR-002; other ADR-104\n**Ref**: T-1100\n"
            ),
            "docs/project_notes/decisions/ADR-002-y.md": "## ADR-002: y\n**Status**: Accepted\n",
            "docs/project_notes/plans.md": "| ID | P | W | S | ADRs | T |\n|-|-|-|-|-|-|\n| P-01 | p | w | LIVE | 1..2 | T-1100 |\n",
        },
    )
    r = check_context_index_edges_resolve(root, _cfg(tmp_path), today=TODAY)
    assert r.status == "pass", r.detail


def test_red_edges_tolerated_until_expiry(tmp_path):
    root = _git_repo(
        tmp_path,
        {"docs/project_notes/decisions/ADR-001-x.md": "## ADR-001: x\n**Status**: Accepted\n**Depends on**: ADR-009\n"},
    )
    _allow(root, context_edges={"9": {"ticket": "T-1043", "expires": "2026-10-15"}})
    cfg = _cfg(tmp_path)
    assert check_context_index_edges_resolve(root, cfg, today=date(2026, 10, 1)).status == "pass"
    assert check_context_index_edges_resolve(root, cfg, today=date(2026, 10, 16)).status == "fail"


def test_skip_edges_without_any_decisions(tmp_path):
    assert check_context_index_edges_resolve(_git_repo(tmp_path, {"README.md": ""}), _cfg(tmp_path)).status == "skip"


# --- the whole audit ----------------------------------------------------------------


def test_run_audit_returns_every_check_in_order(tmp_path):
    root = _notes_repo(tmp_path)
    (root / "docs/project_notes/STATE.md").write_text("# STATE\n", encoding="utf-8")
    results = run_audit(root, _cfg(tmp_path), today=TODAY)
    assert [r.key for r in results] == [
        "docs_adr_refs_resolve",
        "docs_adr_index_fresh",
        "docs_state_budget",
        "context_index_edges_resolve",
    ]
    assert len(DOCS_CHECKS) == 4
    assert all(r.status == "pass" for r in results), [r.to_dict() for r in results]


def test_allowlist_loads_defaults_and_bad_json(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    a = load_allowlist(root)
    assert isinstance(a, Allowlist) and a.adr_refs == {} and "tests/" in a.skip_prefixes
    _allow(root, adr_refs={"ADR-042": {"ticket": "T-1000", "expires": "2099-01-01"}}, skip_prefixes=["vendor/"])
    a = load_allowlist(root)
    assert 42 in a.adr_refs and a.skip_prefixes == ("vendor/",)
    (root / ".claude/kmem_audit.json").write_text("{bad", encoding="utf-8")
    assert load_allowlist(root).adr_refs == {}
