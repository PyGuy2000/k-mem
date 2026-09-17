"""The command guard, through the plugin's hook launcher.

Every refusal test is its own proof of red: the fixture drives a command that
would otherwise run fine, so the guard has something real to block. The
platform session that produced this ticket tested a gate with an edit that was
going to fail anyway, which left the gate nothing to refuse and made a working
gate look broken. A refusal test that cannot go red is not a test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from kmem import cmdguard, report

from conftest import EXAMPLE, REPO_ROOT

HOOKS = REPO_ROOT / "plugins" / "k-mem" / "hooks"
LAUNCHER = "command_guard.py"


# --- fixtures ------------------------------------------------------------------


def _repo(tmp_path: Path, pinned: dict | None = None, evidence: list | None = None) -> Path:
    """A repo that declares its commands. Both sections default to the realistic case."""
    root = tmp_path / "repo"
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src/app.py").write_text("x = 1\n")
    decl = {
        "pinned": {"python": ".venv/bin/python", "pytest": ".venv/bin/python -m pytest"} if pinned is None else pinned,
        "evidence_commands": ["kmem inventory", "scripts/registry_list.py"] if evidence is None else evidence,
    }
    (root / ".claude/commands.json").write_text(json.dumps(decl))
    return root


def _bare_repo(tmp_path: Path) -> Path:
    """A repo with no declaration: the guard must never touch it."""
    root = tmp_path / "plain"
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src/app.py").write_text("x = 1\n")
    return root


def _payload(root: Path, command: str, session: str = "s1") -> dict:
    return {
        "session_id": session,
        "cwd": str(root),
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def _run(payload: dict, evidence_home: Path, extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "KMEM_EVIDENCE_DIR": str(evidence_home), **(extra or {})}
    return subprocess.run(
        [sys.executable, str(HOOKS / LAUNCHER)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def _evidence(evidence_home: Path, session: str = "s1") -> list[dict]:
    p = evidence_home / f"{session}.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


# --- rule 1: pinned tooling -----------------------------------------------------


def test_bare_interpreter_is_refused(tmp_path):
    """PROOF OF RED: `python src/app.py` runs fine here; only the guard stops it."""
    root = _repo(tmp_path)
    assert subprocess.run([sys.executable, str(root / "src/app.py")], capture_output=True).returncode == 0
    r = _run(_payload(root, "python src/app.py"), tmp_path / "ev")
    assert r.returncode == 2, r.stderr
    assert "COMMAND GUARD" in r.stderr
    assert ".venv/bin/python" in r.stderr


def test_pinned_form_is_allowed(tmp_path):
    root = _repo(tmp_path)
    r = _run(_payload(root, ".venv/bin/python src/app.py"), tmp_path / "ev")
    assert r.returncode == 0, r.stderr
    assert not _evidence(tmp_path / "ev")


def test_pinned_form_of_a_longer_key_is_allowed(tmp_path):
    """`.venv/bin/python -m pytest` satisfies the pytest pin without tripping the python pin."""
    root = _repo(tmp_path)
    r = _run(_payload(root, ".venv/bin/python -m pytest tests/ -q"), tmp_path / "ev")
    assert r.returncode == 0, r.stderr


def test_bare_pytest_is_refused(tmp_path):
    root = _repo(tmp_path)
    r = _run(_payload(root, "pytest tests/ -q"), tmp_path / "ev")
    assert r.returncode == 2, r.stderr
    assert ".venv/bin/python -m pytest" in r.stderr


def test_a_subcommand_can_be_pinned_without_pinning_the_tool(tmp_path):
    root = _repo(tmp_path, pinned={"kmem notes index": "python3 scripts/gen_index.py"}, evidence=[])
    refused = _run(_payload(root, "kmem notes index"), tmp_path / "ev")
    assert refused.returncode == 2, refused.stderr
    assert "scripts/gen_index.py" in refused.stderr
    allowed = _run(_payload(root, "kmem inventory"), tmp_path / "ev")
    assert allowed.returncode == 0, allowed.stderr


def test_a_pinned_name_does_not_catch_a_different_name(tmp_path):
    """`python` is pinned; `python3` is a different declaration and was not made."""
    root = _repo(tmp_path, pinned={"python": ".venv/bin/python"}, evidence=[])
    r = _run(_payload(root, "python3 src/app.py"), tmp_path / "ev")
    assert r.returncode == 0, r.stderr


def test_the_pin_survives_a_wrapper_and_an_env_assignment(tmp_path):
    root = _repo(tmp_path)
    r = _run(_payload(root, "PYTHONPATH=lib env python src/app.py"), tmp_path / "ev")
    assert r.returncode == 2, r.stderr


def test_a_pinned_tool_later_in_a_chain_is_refused(tmp_path):
    root = _repo(tmp_path)
    r = _run(_payload(root, "cd src && python app.py"), tmp_path / "ev")
    assert r.returncode == 2, r.stderr


# --- rule 2: truncated evidence -------------------------------------------------


@pytest.mark.parametrize("cut", ["head -20", "tail -12", "sed -n '1,20p'", "grep -m 3 ADR"])
def test_truncated_evidence_command_is_refused(tmp_path, cut):
    """PROOF OF RED: the pipeline is valid shell; only the guard stops it."""
    root = _repo(tmp_path)
    r = _run(_payload(root, f"kmem inventory | {cut}"), tmp_path / "ev")
    assert r.returncode == 2, r.stderr
    assert "TRUNCATED EVIDENCE" in r.stderr
    assert "kmem inventory" in r.stderr


def test_untruncated_evidence_command_is_allowed(tmp_path):
    root = _repo(tmp_path)
    r = _run(_payload(root, "kmem inventory"), tmp_path / "ev")
    assert r.returncode == 0, r.stderr


def test_a_plain_filter_on_an_evidence_command_is_allowed(tmp_path):
    """grep without -m keeps every match: it selects, it does not truncate."""
    root = _repo(tmp_path)
    r = _run(_payload(root, "kmem inventory | grep ADR-013"), tmp_path / "ev")
    assert r.returncode == 0, r.stderr


def test_truncating_an_undeclared_command_is_allowed(tmp_path):
    """The deliberate scope boundary: no heuristic over arbitrary commands."""
    root = _repo(tmp_path)
    r = _run(_payload(root, "ls -la | tail -5"), tmp_path / "ev")
    assert r.returncode == 0, r.stderr


def test_truncation_is_caught_further_down_the_pipeline(tmp_path):
    root = _repo(tmp_path)
    r = _run(_payload(root, "scripts/registry_list.py | sort | head -12"), tmp_path / "ev")
    assert r.returncode == 2, r.stderr


# --- opting in, opting out ------------------------------------------------------


def test_a_repo_without_the_declaration_is_untouched(tmp_path):
    root = _bare_repo(tmp_path)
    r = _run(_payload(root, "python src/app.py | tail -3"), tmp_path / "ev")
    assert r.returncode == 0, r.stderr
    assert not _evidence(tmp_path / "ev")


def test_an_empty_declaration_fires_no_rule(tmp_path):
    root = _repo(tmp_path, pinned={}, evidence=[])
    r = _run(_payload(root, "python src/app.py"), tmp_path / "ev")
    assert r.returncode == 0, r.stderr


def test_a_broken_declaration_fails_open(tmp_path):
    root = _repo(tmp_path)
    (root / ".claude/commands.json").write_text("{not json")
    r = _run(_payload(root, "python src/app.py"), tmp_path / "ev")
    assert r.returncode == 0, r.stderr


def test_the_config_switch_turns_it_off(tmp_path):
    root = _repo(tmp_path)
    r = _run(_payload(root, "python src/app.py"), tmp_path / "ev", extra={"KMEM_COMMAND_GUARD": "0"})
    assert r.returncode == 0, r.stderr


def test_a_non_bash_tool_is_ignored(tmp_path):
    root = _repo(tmp_path)
    payload = {"session_id": "s1", "cwd": str(root), "tool_name": "Edit", "tool_input": {"file_path": str(root / "src/app.py")}}
    r = _run(payload, tmp_path / "ev")
    assert r.returncode == 0, r.stderr


def test_no_payload_is_allowed(tmp_path):
    env = {**os.environ, "KMEM_EVIDENCE_DIR": str(tmp_path / "ev")}
    r = subprocess.run([sys.executable, str(HOOKS / LAUNCHER)], input="", capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr


# --- evidence -------------------------------------------------------------------


def test_a_refusal_writes_one_evidence_line(tmp_path):
    root = _repo(tmp_path)
    _run(_payload(root, "python src/app.py"), tmp_path / "ev")
    rows = _evidence(tmp_path / "ev")
    assert len(rows) == 1
    row = rows[0]
    assert row["hook"] == "command-guard" and row["status"] == "refused"
    assert row["pinned"][0]["required"] == ".venv/bin/python"
    assert row["command"] == "python src/app.py"
    assert row["ts"] and row["session"] == "s1"


def test_the_disabled_marker_allows_and_still_logs(tmp_path):
    root = _repo(tmp_path)
    ev = tmp_path / "ev"
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "DISABLED").write_text("")
    r = _run(_payload(root, "python src/app.py"), ev)
    assert r.returncode == 0, r.stderr
    assert [row["status"] for row in _evidence(ev)] == ["disabled"]


# --- the parser, directly --------------------------------------------------------


def test_a_pipe_inside_quotes_is_not_a_stage():
    assert cmdguard.stages("grep 'a|b' file") == ["grep 'a|b' file"]


def test_pipelines_split_on_the_shell_operators():
    assert cmdguard.pipelines("a && b || c ; d") == ["a", "b", "c", "d"]


@pytest.mark.parametrize(
    "stage,expected",
    [("head -5", "head"), ("tail -n 3", "tail"), ("sed -n '1,4p'", "sed -n"), ("grep -m2 x", "grep -m"), ("grep x", None), ("sort", None)],
)
def test_truncating_names_the_cut(stage, expected):
    assert cmdguard.truncating(stage) == expected


def test_an_unbalanced_quote_does_not_raise():
    assert cmdguard.pinned_violations("python 'oops", {"python": ".venv/bin/python"})


# --- the example repo -------------------------------------------------------------


def test_the_example_declaration_loads_and_both_rules_fire(tmp_path):
    """The shipped example demonstrates the feature, the way its adr_map.json does."""
    decl = cmdguard.load_commands(EXAMPLE)
    assert decl and decl["pinned"] and decl["evidence_commands"]
    assert cmdguard.pinned_violations("python src/billing/tax.py", decl["pinned"])
    assert not cmdguard.pinned_violations("python3 src/billing/tax.py", decl["pinned"])
    assert cmdguard.truncation_violations("kmem inventory | head -40", decl["evidence_commands"])
    assert not cmdguard.truncation_violations("kmem inventory", decl["evidence_commands"])


def test_a_refusal_shows_up_in_kmem_report(tmp_path):
    """The evidence line is useless if the report cannot see it."""
    root = _repo(tmp_path)
    ev = tmp_path / "ev"
    _run(_payload(root, "python src/app.py"), ev)
    _run(_payload(root, "kmem inventory | tail -12", session="s2"), ev)
    rep = report.build(ev)
    assert len(rep["commands_refused"]) == 2
    text = report.render(rep, ev)
    assert "commands refused (pinned tooling / truncated evidence): 2" in text
    assert "pinned" in text and "truncated" in text
