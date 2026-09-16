"""The scrub: no private name, host, path or ticket id anywhere in the tree."""

from __future__ import annotations

import os
import subprocess
import sys

from conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "release_check.py"


def test_tree_is_clean():
    r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout


def test_a_leak_is_caught(tmp_path):
    (tmp_path / "a.md").write_text("fine line\nsee the notes at /ho" + "me/someone/x\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("ticket = 'T-" + "837'\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), "--root", str(tmp_path)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 1
    assert "a.md:2: home path" in r.stdout and "b.py:1: private ticket id" in r.stdout


def test_private_patterns_load_from_a_file_outside_the_repo(tmp_path):
    (tmp_path / "a.md").write_text("mentions Acme Corp here\n", encoding="utf-8")
    patterns = tmp_path / "private.txt"
    patterns.write_text("# comment\n\nacme corp\n", encoding="utf-8")
    env = {**os.environ, "KMEM_RELEASE_CHECK_PATTERNS": str(patterns)}
    r = subprocess.run([sys.executable, str(SCRIPT), "--root", str(tmp_path)], capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 1 and "a.md:1: private pattern 3" in r.stdout and "1 private patterns" in r.stderr
    env["KMEM_RELEASE_CHECK_PATTERNS"] = str(tmp_path / "missing.txt")
    r = subprocess.run([sys.executable, str(SCRIPT), "--root", str(tmp_path)], capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0 and "0 private patterns" in r.stderr


def test_gitignored_files_are_not_scanned(tmp_path):
    """A derived cache git never publishes must not fail the check; a tracked file still does."""
    root = tmp_path / "repo"
    (root / "build").mkdir(parents=True)
    (root / ".gitignore").write_text("build/\n", encoding="utf-8")
    (root / "build" / "index.txt").write_text("cached /ho" + "me/someone/x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, timeout=30)
    r = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout
    (root / "shipped.md").write_text("see /ho" + "me/someone/x\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "shipped.md:1: home path" in r.stdout


def test_four_digit_ticket_ids_are_not_flagged(tmp_path):
    (tmp_path / "a.md").write_text("T-1042 is fine; KazzerLabs is the display name\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), "--root", str(tmp_path)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout
