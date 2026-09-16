"""``kmem init`` in a repo, ``kmem notes adr``, and ``kmem install-git-hooks``."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from kmem.scaffold import CLAUDE_MARKER

from conftest import EXAMPLE, KMEM_BIN


def kmem(*args: str, cwd: Path, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([str(KMEM_BIN), *args], cwd=str(cwd), input=stdin, capture_output=True, text=True, timeout=120, env=dict(os.environ))


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-C", str(cwd), *args],
        capture_output=True, text=True, timeout=30,
    )


def _fresh_repo(tmp_path: Path, name: str = "fresh_app") -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / "README.md").write_text("# fresh\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def test_init_scaffolds_a_fresh_repo_and_audit_passes(tmp_path, isolated_env):
    root = _fresh_repo(tmp_path)
    r = kmem("init", cwd=root)
    assert r.returncode == 0, r.stderr
    for name in ("STATE.md", "plans.md", "decisions.md", "key_facts.md", "bugs.md", "issues.md", "goals.md"):
        assert (root / "docs/project_notes" / name).is_file(), name
        assert "created docs/project_notes/" + name in r.stdout
    assert (root / "docs/project_notes/decisions/.gitkeep").is_file()
    assert (root / ".claude/adr_map.json").is_file()
    assert "fresh_app" in (root / "docs/project_notes/STATE.md").read_text(encoding="utf-8")
    claude = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude.startswith("# fresh_app") and CLAUDE_MARKER in claude and "kmem resolve" in claude
    cfg = json.loads((isolated_env / "config.json").read_text(encoding="utf-8"))
    assert list(cfg["repos"]) == ["fresh_app"]
    r = kmem("audit", cwd=root)
    assert r.returncode == 0, r.stdout
    assert "SKIP  docs_adr_index_fresh" in r.stdout  # no ADR files yet


def test_init_is_idempotent_and_appends_the_block_once(tmp_path, isolated_env):
    root = _fresh_repo(tmp_path)
    (root / "CLAUDE.md").write_text("# mine\n\nKeep this.\n")
    (root / "docs/project_notes").mkdir(parents=True)
    (root / "docs/project_notes/STATE.md").write_text("# my own state\n")
    assert kmem("init", cwd=root).returncode == 0
    r = kmem("init", cwd=root)
    assert r.returncode == 0 and "kept    docs/project_notes/STATE.md" in r.stdout and "kept    CLAUDE.md (block present)" in r.stdout
    assert (root / "docs/project_notes/STATE.md").read_text(encoding="utf-8") == "# my own state\n"
    claude = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude.startswith("# mine\n\nKeep this.\n") and claude.count(CLAUDE_MARKER) == 1


def test_init_no_scaffold_only_writes_config(tmp_path, isolated_env):
    root = _fresh_repo(tmp_path)
    r = kmem("init", "--no-scaffold", "--name", "custom", cwd=root)
    assert r.returncode == 0 and not (root / "docs").exists()
    cfg = json.loads((isolated_env / "config.json").read_text(encoding="utf-8"))
    assert list(cfg["repos"]) == ["custom"]


def test_notes_adr_creates_the_next_number_and_refreshes_the_index(tmp_path):
    root = _fresh_repo(tmp_path)
    assert kmem("init", cwd=root).returncode == 0
    r = kmem("notes", "adr", "Invoices round half-up", cwd=root)
    assert r.returncode == 0, r.stderr
    path = root / "docs/project_notes/decisions/ADR-001-invoices-round-half-up.md"
    assert path.is_file() and "created docs/project_notes/decisions/ADR-001-invoices-round-half-up.md" in r.stdout
    text = path.read_text(encoding="utf-8")
    assert text.startswith("## ADR-001: Invoices round half-up [PROPOSED]") and "**Date**:" in text
    index = (root / "docs/project_notes/decisions.md").read_text(encoding="utf-8")
    assert "[ADR-001](decisions/ADR-001-invoices-round-half-up.md)" in index
    r = kmem("notes", "adr", "Second: with punctuation!", cwd=root)
    assert r.returncode == 0 and (root / "docs/project_notes/decisions/ADR-002-second-with-punctuation.md").is_file()
    assert kmem("audit", cwd=root).returncode == 0


def test_notes_adr_numbers_after_the_example(tmp_path):
    import shutil

    root = tmp_path / "copy"
    shutil.copytree(EXAMPLE, root)
    r = kmem("notes", "adr", "Fifth", cwd=root)
    assert r.returncode == 0 and (root / "docs/project_notes/decisions/ADR-005-fifth.md").is_file()


def test_install_git_hooks_writes_a_working_pre_commit(tmp_path):
    root = _fresh_repo(tmp_path)
    assert kmem("init", cwd=root).returncode == 0
    r = kmem("install-git-hooks", cwd=root)
    assert r.returncode == 0 and "installed" in r.stdout
    hook = root / ".git/hooks/pre-commit"
    assert hook.is_file() and os.access(hook, os.X_OK)
    text = hook.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3") and "kmem install-git-hooks" in text and "import kmem" not in text
    r = kmem("install-git-hooks", cwd=root)
    assert r.returncode == 0 and "kept" in r.stdout
    # red: an intent line with no ticket is refused
    issues = root / "docs/project_notes/issues.md"
    issues.write_text(issues.read_text(encoding="utf-8") + "\n## 2026-09-16 Thing\n\n- next step: wire the widget\n", encoding="utf-8")
    _git(root, "add", "-A")
    c = _git(root, "commit", "-q", "-m", "intent")
    assert c.returncode != 0 and "INTENT GUARD" in c.stderr
    # green: with a ticket id on the line
    issues.write_text(issues.read_text(encoding="utf-8").replace("- next step: wire the widget", "- next step: wire the widget (T-1042)"), encoding="utf-8")
    _git(root, "add", "-A")
    c = _git(root, "commit", "-q", "-m", "intent with ticket")
    assert c.returncode == 0, c.stderr


def test_install_git_hooks_refuses_to_clobber_a_foreign_hook(tmp_path):
    root = _fresh_repo(tmp_path)
    hook = root / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\necho mine\n")
    r = kmem("install-git-hooks", cwd=root)
    assert r.returncode == 2 and "not ours" in r.stderr
    r = kmem("install-git-hooks", "--force", cwd=root)
    assert r.returncode == 0 and "kmem install-git-hooks" in hook.read_text(encoding="utf-8")
