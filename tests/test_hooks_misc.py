"""hooks.json, the launchers, the write guard, the session-end guard, the session start and the docs check."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from kmem.config import Config, load_config
from kmem.hooks.outbox_guard import MESSAGE as OUTBOX_MESSAGE
from kmem.hooks.write_guard import CHECKLIST

from conftest import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "k-mem"
HOOKS = PLUGIN / "hooks"


def _run(script: str, payload: dict | None, evidence_home: Path, extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "KMEM_EVIDENCE_DIR": str(evidence_home), **(extra or {})}
    return subprocess.run([sys.executable, str(HOOKS / script)], input=json.dumps(payload) if payload is not None else "", capture_output=True, text=True, env=env, timeout=60)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-C", str(cwd), *args],
        check=True, capture_output=True, text=True, timeout=30,
    ).stdout


# --- hooks.json and the launchers ------------------------------------------------


def test_hooks_json_wires_every_launcher_that_exists():
    doc = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
    hooks = doc["hooks"]
    assert set(hooks) == {"PreToolUse", "PostToolUse", "SessionStart", "Stop"}
    referenced: set[str] = set()
    for event, entries in hooks.items():
        for entry in entries:
            for h in entry["hooks"]:
                assert h["type"] == "command"
                assert h["command"].startswith('python3 "${CLAUDE_PLUGIN_ROOT}/hooks/')
                name = h["command"].split("/hooks/")[1].rstrip('"')
                assert (HOOKS / name).is_file(), name
                referenced.add(name)
                assert "timeout" in h
    launchers = {p.name for p in HOOKS.glob("*.py")}
    assert referenced == launchers
    pre = hooks["PreToolUse"]
    assert any("mcp__filesystem__write_file" in e["matcher"] and "NotebookEdit" in e["matcher"] for e in pre)
    assert any(e["matcher"] == "Bash" for e in pre)
    assert hooks["PostToolUse"][0]["matcher"] == "Bash"
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "k-mem" and manifest["hooks"] == "./hooks/hooks.json"


def test_every_launcher_exits_zero_on_empty_stdin(tmp_path):
    for p in sorted(HOOKS.glob("*.py")):
        r = _run(p.name, None, tmp_path / "ev")
        assert r.returncode == 0, (p.name, r.stderr)


def test_kmem_hook_subcommand_dispatches(tmp_path):
    kmem = PLUGIN / "bin" / "kmem"
    r = subprocess.run([str(kmem), "hook", "write-guard"], input="{}", capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    r = subprocess.run([str(kmem), "hook", "nope"], input="{}", capture_output=True, text=True, timeout=30)
    assert r.returncode == 2 and "unknown hook" in r.stderr


# --- write guard -----------------------------------------------------------------------


def test_write_guard_fires_once_per_file_and_session(tmp_path):
    ev = tmp_path / "ev"
    payload = {"session_id": "s1", "tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "docs/project_notes/decisions/ADR-001-x.md")}}
    r = _run("write_guard.py", payload, ev)
    assert r.returncode == 2 and r.stderr.strip() == CHECKLIST.strip()
    assert _run("write_guard.py", payload, ev).returncode == 0
    other = {"session_id": "s1", "tool_name": "mcp__filesystem__write_file", "tool_input": {"path": str(tmp_path / "docs/project_notes/decisions.md")}}
    assert _run("write_guard.py", other, ev).returncode == 2
    plain = {"session_id": "s1", "tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "src/x.py")}}
    assert _run("write_guard.py", plain, ev).returncode == 0
    assert "kmem notes index" in CHECKLIST


# --- session-end guard -------------------------------------------------------------------


def _dirty_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.txt").write_text("a\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    (root / "a.txt").write_text("changed\n")
    return root


def test_outbox_guard_fires_once_on_a_long_dirty_session(tmp_path, isolated_env):
    root = _dirty_repo(tmp_path)
    big = tmp_path / "big.jsonl"
    big.write_text("x" * 900_000)
    ev = tmp_path / "ev"
    payload = {"session_id": "s-out", "transcript_path": str(big), "cwd": str(root)}
    r = _run("outbox_guard.py", payload, ev)
    assert r.returncode == 2 and r.stderr.strip() == OUTBOX_MESSAGE.strip()
    assert _run("outbox_guard.py", payload, ev).returncode == 0  # once per session
    assert _run("outbox_guard.py", {**payload, "session_id": "s-out2", "stop_hook_active": True}, ev).returncode == 0


def test_outbox_guard_stays_quiet_on_short_or_clean_sessions_or_with_a_fresh_handoff(tmp_path, isolated_env):
    root = _dirty_repo(tmp_path)
    ev = tmp_path / "ev"
    small = tmp_path / "small.jsonl"
    small.write_text("x" * 100)
    assert _run("outbox_guard.py", {"session_id": "a", "transcript_path": str(small), "cwd": str(root)}, ev).returncode == 0
    big = tmp_path / "big.jsonl"
    big.write_text("x" * 900_000)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "clean")
    assert _run("outbox_guard.py", {"session_id": "b", "transcript_path": str(big), "cwd": str(root)}, ev).returncode == 0
    (root / "a.txt").write_text("dirty again\n")
    pending = load_config().handoffs_dir / "pending"
    pending.mkdir(parents=True)
    (pending / "20260916T100000__repo__to__other.md").write_text("---\nto: other\n---\n")
    assert _run("outbox_guard.py", {"session_id": "c", "transcript_path": str(big), "cwd": str(root)}, ev).returncode == 0


# --- session start ---------------------------------------------------------------------------


def _governed_repo(tmp_path: Path) -> Path:
    root = tmp_path / "gov"
    (root / ".claude").mkdir(parents=True)
    (root / "docs/project_notes/decisions").mkdir(parents=True)
    (root / "docs/project_notes/decisions/ADR-001-x.md").write_text("## ADR-001: X [ACCEPTED]\n**Status**: Accepted\n")
    (root / "docs/project_notes/STATE.md").write_text("# STATE\n")
    (root / "src").mkdir()
    (root / "src/a.py").write_text("x = 1\n")
    (root / ".claude/adr_map.json").write_text(json.dumps({"repo": "gov", "rules": [{"paths": ["src/**"], "adrs": [1]}]}))
    (root / "CLAUDE.md").write_text("# gov\n\n<!-- k-mem:start -->\nblock\n<!-- k-mem:end -->\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def test_session_start_creates_config_and_prints_inbox_packet_and_inventory(tmp_path, isolated_env):
    root = _governed_repo(tmp_path)
    (root / "src/a.py").write_text("x = 2\n")  # a dirty governed file -> packet
    cfg = Config.defaults(isolated_env)
    pending = cfg.handoffs_dir / "pending"
    pending.mkdir(parents=True)
    (pending / "20260916T100000__other__to__gov.md").write_text("---\nfrom: other\nto: gov\nsubject: hello\n---\n\nbody\n")
    (pending / "20260916T100001__other__to__someone_else.md").write_text("---\nto: someone_else\n---\n")
    r = _run("session_start.py", {"session_id": "s-start", "cwd": str(root), "source": "startup"}, tmp_path / "ev")
    assert r.returncode == 0, r.stderr
    assert "K-mem: created" in r.stdout and (isolated_env / "config.json").is_file()
    inbox_text = r.stdout.split("=== HANDOFF INBOX")[1].split("=== END HANDOFF INBOX ===")[0]
    assert "20260916T100000__other__to__gov.md" in inbox_text and "someone_else" not in inbox_text
    assert "Context packet" in r.stdout and "src/a.py -> read: docs/project_notes/decisions/ADR-001-x.md" in r.stdout
    assert "# Knowledge inventory" in r.stdout and "**gov** (1 ADRs)" in r.stdout
    cfg = load_config()
    assert cfg.repos == {"gov": root.resolve()}
    r2 = _run("session_start.py", {"session_id": "s-start", "cwd": str(root), "source": "compact"}, tmp_path / "ev")
    assert "Knowledge inventory" not in r2.stdout and "K-mem: created" not in r2.stdout and "HANDOFF INBOX" in r2.stdout


def test_session_start_respects_config_flags_and_never_fails(tmp_path, isolated_env, write_config):
    root = _governed_repo(tmp_path)
    write_config(repos={"gov": str(root)}, session_start={"inventory": False, "packet": False, "inbox": False, "stale_guard": False})
    (root / "src/a.py").write_text("x = 2\n")
    r = _run("session_start.py", {"session_id": "s", "cwd": str(root)}, tmp_path / "ev")
    assert r.returncode == 0 and r.stdout.strip() == ""
    r = _run("session_start.py", {"session_id": "s", "cwd": str(tmp_path)}, tmp_path / "ev")  # not a repo at all
    assert r.returncode == 0


def test_session_start_warns_on_a_stale_checkout(tmp_path, isolated_env):
    root = _governed_repo(tmp_path)
    base = _git(root, "branch", "--show-current").strip()
    _git(root, "checkout", "-q", "-b", "old-branch")
    (root / "docs/project_notes/STATE.md").unlink()
    (root / "CLAUDE.md").write_text("# gov, old contract\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "old")
    r = _run("session_start.py", {"session_id": "s-stale", "cwd": str(root)}, tmp_path / "ev")
    assert r.returncode == 0
    assert "STALE CHECKOUT WARNING" in r.stdout and base in r.stdout and "STATE.md" in r.stdout and "K-mem block" in r.stdout


# --- docs check -------------------------------------------------------------------------------


def test_docs_check_hook_reports_budget_overrun(tmp_path, isolated_env, write_config):
    root = tmp_path / "repo"
    (root / "docs/project_notes").mkdir(parents=True)
    (root / "docs/project_notes/STATE.md").write_text("x" * 4_000)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    write_config(state_budget_tokens=100)
    r = _run("docs_check.py", {"session_id": "s", "cwd": str(root)}, tmp_path / "ev")
    assert r.returncode == 0 and "over budget" in r.stdout and "STATE.md" in r.stdout
    r2 = _run("docs_check.py", {"session_id": "s", "cwd": str(root)}, tmp_path / "ev")
    assert r2.stdout == ""  # cached per HEAD
