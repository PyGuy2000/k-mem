"""The handoff mailbox: names, send, inbox, list, archive."""

from __future__ import annotations

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
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


def test_inbox_shows_the_subject_and_never_the_body(tmp_path, isolated_env):
    cfg = Config.defaults(isolated_env)
    cwd = tmp_path / "target_app"
    cwd.mkdir()
    handoffs.send(cfg, "sender_app", "target_app", "Boundary decided", "## Ask\nsecret step\n")
    box = handoffs.inbox(cwd, cfg)
    assert "from sender_app: Boundary decided" in box and "kmem handoff claim" in box
    assert "secret step" not in box


def test_claim_gives_a_note_to_one_owner_and_refuses_the_next(tmp_path, isolated_env):
    cfg = Config.defaults(isolated_env)
    cwd = tmp_path / "target_app"
    cwd.mkdir()
    note = handoffs.send(cfg, "sender_app", "target_app", "One job", "## Ask\ndo it\n")
    held = handoffs.claim(cfg, note.name, "worktree-a", when=1_800_000_000)
    assert held.parent == cfg.handoffs_dir / "claimed" and not note.exists()
    meta = handoffs.parse_note(held)
    assert meta["claimed_by"] == "worktree-a" and meta["claimed_at"].startswith("2027-") and meta["to"] == "target_app"
    assert "## Ask\ndo it" in held.read_text(encoding="utf-8")
    assert handoffs.inbox(cwd, cfg) == ""  # gone from every other session's list
    with pytest.raises(FileExistsError, match="already claimed by worktree-a"):
        handoffs.claim(cfg, note.name, "worktree-b")
    with pytest.raises(FileNotFoundError, match="no pending note"):
        handoffs.claim(cfg, "missing.md", "worktree-b")


def test_parallel_claims_have_exactly_one_winner(tmp_path, isolated_env):
    cfg = Config.defaults(isolated_env)
    note = handoffs.send(cfg, "sender_app", "target_app", "Race")

    def attempt(i: int) -> bool:
        try:
            handoffs.claim(cfg, note.name, f"worktree-{i}")
            return True
        except FileExistsError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert results.count(True) == 1


def test_release_returns_the_note_clean_and_archive_takes_a_claimed_note(tmp_path, isolated_env):
    cfg = Config.defaults(isolated_env)
    note = handoffs.send(cfg, "sender_app", "target_app", "Round trip", "## Ask\nx\n")
    original = note.read_text(encoding="utf-8")
    handoffs.claim(cfg, note.name, "worktree-a")
    back = handoffs.release(cfg, note.name)
    assert back == note and note.read_text(encoding="utf-8") == original
    with pytest.raises(FileNotFoundError, match="no claimed note"):
        handoffs.release(cfg, note.name)
    held = handoffs.claim(cfg, note.name, "worktree-b")
    moved = handoffs.archive(cfg, note.name)
    assert moved.parent == cfg.handoffs_dir / "archive" and not held.exists()


def test_cli_claim_prints_the_note_and_a_second_claim_exits_nonzero(tmp_path, isolated_env):
    cwd = tmp_path / "cli_app"
    cwd.mkdir()
    env = dict(os.environ)

    def kmem(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run([str(KMEM_BIN), "handoff", *args], cwd=str(cwd), input=stdin, capture_output=True, text=True, env=env, timeout=60)

    assert kmem("send", "--to", "cli_app", "--subject", "hi", stdin="## Ask\nthe body\n").returncode == 0
    name = kmem("inbox").stdout.split("--- ")[1].split(" ---")[0]
    r = kmem("claim", name, "--by", "worktree-a")
    assert r.returncode == 0 and "the body" in r.stdout and "claimed_by: worktree-a" in r.stdout, r.stderr
    r = kmem("claim", name, "--by", "worktree-b")
    assert r.returncode == 1 and "already claimed by worktree-a" in r.stderr
    assert "claimed_by=worktree-a" in kmem("list").stdout
    assert kmem("release", name).returncode == 0
    assert "HANDOFF INBOX" in kmem("inbox").stdout
    r = kmem("archive", "missing.md")
    assert r.returncode == 1 and "no pending or claimed note" in r.stderr
