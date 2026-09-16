"""Fact-doc staleness: check, stamp, stamp-all, init, and the notes budget."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from kmem import docsync
from kmem.config import Config


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-C", str(cwd), *args],
        check=True, capture_output=True, text=True, timeout=30,
    ).stdout


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "docs/individual_readme_files").mkdir(parents=True)
    (root / "src/loader.py").write_text("x = 1\n")
    (root / "docs/individual_readme_files/loader.md").write_text("---\nsource_paths:\n  - src/loader.py\nlast_synced_sha: \nadr: [ADR-001]\n---\n\n# Loader\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def _cfg(tmp_path: Path, **extra) -> Config:
    cfg = Config.defaults(tmp_path / "kmem-data")
    for k, v in extra.items():
        setattr(cfg, k, v)
    return cfg


def test_stamp_then_drift_then_stamp_all(tmp_path):
    root = _repo(tmp_path)
    doc = root / "docs/individual_readme_files/loader.md"
    cfg = _cfg(tmp_path)
    assert docsync.check(root, cfg) == []  # not enrolled yet (no sha)
    msg = docsync.stamp(doc)
    assert msg.startswith("stamped") and docsync.doc_meta(doc)["last_synced_sha"]
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "stamp")
    assert docsync.check(root, cfg, force=True) == []
    (root / "src/loader.py").write_text("x = 2\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "change source")
    lines = docsync.check(root, cfg, force=True)
    assert any("may be stale" in line for line in lines)
    assert any("loader.md  (1 commit to its source since sync)" in line for line in lines)
    assert docsync.check(root, cfg) == []  # cached for this HEAD
    assert docsync.stamp_all(root) == "stamped 1 enrolled doc(s)"
    assert docsync.check(root, cfg, force=True) == []


def test_broken_sha_warns_instead_of_skipping(tmp_path):
    root = _repo(tmp_path)
    doc = root / "docs/individual_readme_files/loader.md"
    docsync.set_frontmatter_field(doc, "last_synced_sha", "deadbeefdeadbeef")
    lines = docsync.check(root, _cfg(tmp_path), force=True)
    assert any("UNRESOLVABLE" in line for line in lines) and any("loader.md" in line for line in lines)


def test_init_adds_skeleton_once(tmp_path):
    path = tmp_path / "docs/individual_readme_files/new.md"
    assert docsync.init(path).startswith("added frontmatter skeleton")
    assert path.read_text(encoding="utf-8").startswith("---\n")
    with pytest.raises(ValueError):
        docsync.init(path)
    plain = tmp_path / "plain.md"
    plain.write_text("# Plain\n")
    docsync.init(plain)
    assert plain.read_text(encoding="utf-8").endswith("# Plain\n") and plain.read_text(encoding="utf-8").startswith("---\n")


def test_budget_lines_follow_the_config(tmp_path):
    root = _repo(tmp_path)
    notes = root / "docs/project_notes"
    notes.mkdir()
    (notes / "STATE.md").write_text("x" * 4_000)
    (notes / "bugs.md").write_text("x" * 4 * 90_000)
    assert docsync.budget_lines(root, _cfg(tmp_path)) == [
        "   - bugs.md ~90,000 tokens > 80,000 nudge; run `kmem notes archive` to move closed entries past the 90-day cutoff into archive/."
    ]
    lines = docsync.budget_lines(root, _cfg(tmp_path, state_budget_tokens=500))
    assert len(lines) == 2 and "STATE.md ~1,000 tokens > 500 budget" in lines[0]


def test_stamp_outside_a_repo_is_an_error(tmp_path):
    doc = tmp_path / "x.md"
    doc.write_text("---\nsource_paths: [a]\n---\n")
    with pytest.raises(ValueError):
        docsync.stamp(doc)
