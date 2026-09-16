"""The handoff mailbox: names, send, inbox, list, archive."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from kmem import handoffs
from kmem.config import Config

from conftest import KMEM_BIN


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-C", str(cwd), *args],
        check=True, capture_output=True, text=True, timeout=30,
    ).stdout


def test_project_names_cover_dir_repo_map_and_config(tmp_path, isolated_env):
    root = tmp_path / "my_app"
    (root / ".claude").mkdir(parents=True)
    (root / ".claude/adr_map.json").write_text(json.dumps({"repo": "named", "rules": []}))
    _git(root, "init", "-q")
    (root / "a").write_text("a")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    wt = tmp_path / "worktrees" / "feat-x"
    _git(root, "worktree", "add", "-q", "-b", "feat-x", str(wt))
    cfg = Config.defaults(isolated_env)
    cfg.repos = {"configured": root}
    assert handoffs.project_names(root, cfg) == ["my_app", "named", "configured"]
    names = handoffs.project_names(wt, cfg)
    assert names[0] == "feat-x" and "my_app" in names and "named" in names
    assert handoffs.project_names(tmp_path / "nowhere", cfg) == ["nowhere"]


def test_send_inbox_list_archive_round_trip(tmp_path, isolated_env):
    cfg = Config.defaults(isolated_env)
    cwd = tmp_path / "target_app"
    cwd.mkdir()
    path = handoffs.send(cfg, "sender_app", "target_app", "Boundary decided", "## State\ndone\n", when=1_800_000_000)
    assert path.parent == cfg.handoffs_dir / "pending" and path.name.endswith("__sender_app__to__target_app.md")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\nfrom: sender_app\nto: target_app\ncreated: ") and "subject: Boundary decided" in text and "## State\ndone" in text
    other = handoffs.send(cfg, "sender_app", "someone_else", "not for you")
    assert "## Ask" in other.read_text(encoding="utf-8")  # empty body gets the template
    assert [p.name for p in handoffs.list_pending(cfg)] == sorted([path.name, other.name])
    box = handoffs.inbox(cwd, cfg)
    assert "HANDOFF INBOX" in box and "(target_app)" in box and path.name in box and other.name not in box
    assert "kmem handoff archive" in box
    moved = handoffs.archive(cfg, path.name)
    assert moved.parent == cfg.handoffs_dir / "archive" and not path.exists()
    assert handoffs.inbox(cwd, cfg) == ""
    with pytest.raises(FileNotFoundError):
        handoffs.archive(cfg, path.name)


def test_cli_handoff_commands(tmp_path, isolated_env):
    cwd = tmp_path / "cli_app"
    cwd.mkdir()
    env = dict(os.environ)
    r = subprocess.run([str(KMEM_BIN), "handoff", "send", "--to", "cli_app", "--subject", "hi"], cwd=str(cwd), input="## State\nx\n", capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0 and "queued" in r.stdout, r.stderr
    r = subprocess.run([str(KMEM_BIN), "handoff", "list"], cwd=str(cwd), capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0 and "to=cli_app" in r.stdout and "from=cli_app" in r.stdout
    r = subprocess.run([str(KMEM_BIN), "handoff", "inbox"], cwd=str(cwd), capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0 and "HANDOFF INBOX" in r.stdout
    name = r.stdout.split("--- ")[1].split(" ---")[0]
    r = subprocess.run([str(KMEM_BIN), "handoff", "archive", name], cwd=str(cwd), capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0 and "archived" in r.stdout
    r = subprocess.run([str(KMEM_BIN), "handoff", "inbox"], cwd=str(cwd), capture_output=True, text=True, env=env, timeout=60)
    assert "no pending handoff" in r.stdout
