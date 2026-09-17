"""Test harness: every test runs against an isolated data dir and no DevFlow state.

The library is imported from ``plugins/k-mem/lib`` (also set in pyproject).
``isolated_env`` is autouse so no test ever reads the user's real config,
index or evidence.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LIB = REPO_ROOT / "plugins" / "k-mem" / "lib"
EXAMPLE = REPO_ROOT / "example"
KMEM_BIN = REPO_ROOT / "plugins" / "k-mem" / "bin" / "kmem"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch) -> Path:
    data = tmp_path / "kmem-data"
    monkeypatch.setenv("KMEM_DATA_DIR", str(data))
    for var in ("KMEM_CONFIG", "CLAUDE_PLUGIN_DATA", "KMEM_INDEX_DIR", "KMEM_EVIDENCE_DIR", "KMEM_HANDOFFS_DIR", "KMEM_ENFORCE", "KMEM_COMMAND_GUARD"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DEVFLOW_STATE_PATH", str(tmp_path / "no-devflow.json"))
    return data


@pytest.fixture
def write_config(isolated_env):
    """Write ``config.json`` into the isolated data dir; return its path."""

    def _write(**data):
        isolated_env.mkdir(parents=True, exist_ok=True)
        path = isolated_env / "config.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    return _write
