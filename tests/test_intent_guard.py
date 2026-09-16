"""The intent guard: proof of red and green, and the CLI."""

from __future__ import annotations

import os
import subprocess

from kmem import intent_guard

from conftest import KMEM_BIN


def test_self_test_and_offending_lines():
    assert intent_guard.self_test() == 0
    red = intent_guard.offending_lines(intent_guard.RED_DIFF)
    assert [(p, n) for p, n, _ in red] == [("docs/project_notes/issues.md", 11), ("docs/project_notes/issues.md", 12)]
    assert intent_guard.offending_lines(intent_guard.GREEN_DIFF) == []
    archive = intent_guard.RED_DIFF.replace("docs/project_notes/issues.md", "docs/project_notes/archive/old.md")
    assert intent_guard.offending_lines(archive) == []
    elsewhere = intent_guard.RED_DIFF.replace("docs/project_notes/issues.md", "README.md")
    assert intent_guard.offending_lines(elsewhere) == []


def test_cli_diff_from_stdin():
    env = dict(os.environ)
    r = subprocess.run([str(KMEM_BIN), "intent-guard", "--diff-from-stdin"], input=intent_guard.RED_DIFF, capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 1 and "INTENT GUARD" in r.stderr and "issues.md:11" in r.stderr
    r = subprocess.run([str(KMEM_BIN), "intent-guard", "--diff-from-stdin"], input=intent_guard.GREEN_DIFF, capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0
    r = subprocess.run([str(KMEM_BIN), "intent-guard", "--self-test"], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0 and "OK" in r.stdout
