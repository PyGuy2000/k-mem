"""The read gate, the name check and the sweep, through the plugin's hook launchers.

Each contract has its proof of red: the deny case IS the red proof, asserted
with the real launcher as a subprocess. Evidence goes to an isolated dir.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from kmem import gate
from kmem.govmap import adr_file, glob_to_regex, load_map, section_read_command
from kmem.hooks.name_check import missing_names

from conftest import EXAMPLE, REPO_ROOT

HOOKS = REPO_ROOT / "plugins" / "k-mem" / "hooks"
GOVERNED = "src/gateway/desk_read.py"


# --- the example map -----------------------------------------------------------


def test_example_map_every_adr_number_resolves_to_a_file():
    rules = load_map(EXAMPLE)
    assert rules
    missing = sorted({n for r in rules for n in r["adrs"] if adr_file(EXAMPLE, int(n)) is None})
    assert not missing


def test_example_map_every_pattern_matches_a_real_path():
    files = [p.relative_to(EXAMPLE).as_posix() for p in EXAMPLE.rglob("*") if p.is_file()]
    dead = [pat for r in load_map(EXAMPLE) for pat in r["paths"] if not any(glob_to_regex(pat).match(f) for f in files)]
    assert not dead


# --- a fake repo + transcript ----------------------------------------------


def _fake_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".claude").mkdir(parents=True)
    (root / "docs/project_notes/decisions").mkdir(parents=True)
    (root / "docs/project_notes/decisions/ADR-102-desk-feeds.md").write_text("## ADR-102\n")
    (root / "src/gateway").mkdir(parents=True)
    (root / "src/gateway/desk_read.py").write_text("x = 1\n")
    (root / ".claude/adr_map.json").write_text(json.dumps({"rules": [{"paths": [GOVERNED], "adrs": [102]}]}))
    return root


def _transcript(tmp_path: Path, tool_uses: list[tuple[str, dict]], assistant_text: str = "") -> Path:
    t = tmp_path / f"session-{len(list(tmp_path.glob('session-*.jsonl')))}.jsonl"  # unique per call
    lines = [json.dumps({"type": "user", "message": {"role": "user", "content": "do the thing"}})]
    for name, inp in tool_uses:
        lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": name, "input": inp}]}}))
    if assistant_text:
        lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": assistant_text}]}}))
    t.write_text("\n".join(lines) + "\n")
    return t


def _run(script: str, payload: dict, evidence_home: Path, extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "KMEM_EVIDENCE_DIR": str(evidence_home), **(extra or {})}
    return subprocess.run([sys.executable, str(HOOKS / script)], input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=60)


def _evidence(evidence_home: Path, session: str) -> list[dict]:
    p = evidence_home / f"{session}.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


def _payload(root: Path, rel: str, transcript: Path, session: str) -> dict:
    return {"session_id": session, "transcript_path": str(transcript), "tool_name": "Edit", "tool_input": {"file_path": str(root / rel)}}


def test_gate_denies_edit_when_adr_was_not_read(tmp_path):
    """PROOF OF RED: the governed edit with no read must be refused (exit 2)."""
    root = _fake_repo(tmp_path)
    transcript = _transcript(tmp_path, [("Bash", {"command": "ls"})])
    payload = _payload(root, GOVERNED, transcript, "s-red")
    r = _run("read_gate.py", payload, tmp_path / "ev")
    assert r.returncode == 2, r.stderr
    assert "ADR-102-desk-feeds.md" in r.stderr and "READ GATE" in r.stderr
    ev = _evidence(tmp_path / "ev", "s-red")
    assert ev and ev[-1]["status"] == "denied" and ev[-1]["missing"] == [102]
    assert _run("read_gate.py", payload, tmp_path / "ev").returncode == 2  # no second-attempt bypass


@pytest.mark.parametrize(
    "tool_use",
    [
        ("Read", {"file_path": "/x/docs/project_notes/decisions/ADR-102-desk-feeds.md"}),
        ("Bash", {"command": "sed -n 1,40p docs/project_notes/decisions/ADR-102-desk-feeds.md"}),
        ("mcp__filesystem__read_text_file", {"path": "/x/decisions/ADR-102-desk-feeds.md"}),
        ("Bash", {"command": "sed -n 14,22p docs/project_notes/decisions/ADR-102-desk*.md | cut -c1-700"}),
    ],
)
def test_gate_allows_edit_after_any_kind_of_read(tmp_path, tool_use):
    root = _fake_repo(tmp_path)
    transcript = _transcript(tmp_path, [tool_use])
    r = _run("read_gate.py", _payload(root, GOVERNED, transcript, "s-green"), tmp_path / "ev")
    assert r.returncode == 0, r.stderr
    ev = _evidence(tmp_path / "ev", "s-green")
    assert ev[-1]["status"] == "read" and ev[-1]["adrs"] == [102]


def test_gate_ignores_ungoverned_paths_and_the_adr_files_themselves(tmp_path):
    root = _fake_repo(tmp_path)
    transcript = _transcript(tmp_path, [])
    for rel in ("README.md", "docs/project_notes/decisions/ADR-102-desk-feeds.md"):
        assert _run("read_gate.py", _payload(root, rel, transcript, "s-skip"), tmp_path / "ev").returncode == 0


def test_gate_fails_open_and_logs_when_transcript_is_missing(tmp_path):
    root = _fake_repo(tmp_path)
    payload = _payload(root, GOVERNED, tmp_path / "nope.jsonl", "s-nt")
    assert _run("read_gate.py", payload, tmp_path / "ev").returncode == 0
    assert _evidence(tmp_path / "ev", "s-nt")[-1]["status"] == "no_transcript"


def test_gate_disabled_file_allows_and_logs(tmp_path):
    root = _fake_repo(tmp_path)
    ev = tmp_path / "ev"
    ev.mkdir()
    (ev / "DISABLED").touch()
    assert _run("read_gate.py", _payload(root, GOVERNED, _transcript(tmp_path, []), "s-off"), ev).returncode == 0
    assert _evidence(ev, "s-off")[-1]["status"] == "disabled"


def test_gate_with_empty_stdin_allows(tmp_path):
    r = subprocess.run([sys.executable, str(HOOKS / "read_gate.py")], input="", capture_output=True, text=True, timeout=30)
    assert r.returncode == 0


# --- the Stop-hook name check ------------------------------------------------


def test_name_check_blocks_once_when_reply_omits_the_adr(tmp_path):
    """PROOF OF RED for the name check: governed edit + reply with no ADR -> exit 2, once."""
    root = _fake_repo(tmp_path)
    edit = ("Edit", {"file_path": str(root / GOVERNED), "old_string": "a", "new_string": "b"})
    transcript = _transcript(tmp_path, [edit], assistant_text="Done. I changed the read layer.")
    payload = {"session_id": "s-name-red", "transcript_path": str(transcript)}
    r = _run("name_check.py", payload, tmp_path / "ev")
    assert r.returncode == 2 and "ADR-102" in r.stderr
    assert _run("name_check.py", payload, tmp_path / "ev").returncode == 0  # never loops
    statuses = [e["status"] for e in _evidence(tmp_path / "ev", "s-name-red")]
    assert statuses == ["blocked_once", "unnamed"]


def test_name_check_passes_when_reply_names_the_adr(tmp_path):
    root = _fake_repo(tmp_path)
    edit = ("Edit", {"file_path": str(root / GOVERNED), "old_string": "a", "new_string": "b"})
    transcript = _transcript(tmp_path, [edit], assistant_text="Done, per ADR-102 (the card test).")
    payload = {"session_id": "s-name-green", "transcript_path": str(transcript)}
    assert _run("name_check.py", payload, tmp_path / "ev").returncode == 0
    assert _evidence(tmp_path / "ev", "s-name-green")[-1]["status"] == "named"


def test_name_check_accepts_alias_prefix():
    assert missing_names("read app-102 and ADR-126", {102, 126}, ["app"]) == []
    assert missing_names("read app-102", {102, 126}, ["app"]) == [126]
    assert missing_names("read app-102", {102}, []) == [102]


def test_name_check_sees_bash_writes(tmp_path):
    root = _fake_repo(tmp_path)
    edit = ("Bash", {"command": f"sed -i 's/a/b/' {root / GOVERNED}"})
    transcript = _transcript(tmp_path, [edit], assistant_text="Done. Changed the read layer.")
    r = _run("name_check.py", {"session_id": "s-name-bash", "transcript_path": str(transcript)}, tmp_path / "ev")
    assert r.returncode == 2 and "ADR-102" in r.stderr


# --- the single-file ADR layout ------------------------------------------------


def _fake_single_file_repo(tmp_path: Path, adrs: list[int] | None = None) -> Path:
    root = tmp_path / "single_repo"
    (root / ".claude").mkdir(parents=True)
    notes = root / "docs/project_notes"
    notes.mkdir(parents=True)
    (notes / "decisions.md").write_text(
        "# Decisions\n\n## ADR-104: Authored semantics store\n**Date**: 2026-08-17\n**Status**: Accepted\n\nbody of 104\n\n"
        "## ADR-105: Endorsement queue reconciled\n**Status**: Accepted\n\nbody of 105\n",
        encoding="utf-8",
    )
    (root / "config").mkdir()
    (root / "config/authored_semantics.yaml").write_text("x: 1\n", encoding="utf-8")
    (root / ".claude/adr_map.json").write_text(json.dumps({"rules": [{"paths": ["config/**"], "adrs": adrs or [104]}]}), encoding="utf-8")
    return root


def test_single_file_layout_denies_until_the_section_is_read(tmp_path):
    root = _fake_single_file_repo(tmp_path)
    ev = tmp_path / "ev"
    rel = "config/authored_semantics.yaml"
    t0 = _transcript(tmp_path, [("Bash", {"command": "ls"})])
    r = _run("read_gate.py", _payload(root, rel, t0, "s-sf-red"), ev)
    assert r.returncode == 2, r.stderr
    assert "docs/project_notes/decisions.md" in r.stderr and "ADR-104" in r.stderr and "awk" in r.stderr
    last = _evidence(ev, "s-sf-red")[-1]
    assert last["status"] == "denied" and last["missing"] == [104] and last["mode"] == "shadow"
    t1 = _transcript(tmp_path, [("Bash", {"command": "sed -n 1,40p docs/project_notes/decisions.md"})])
    assert _run("read_gate.py", _payload(root, rel, t1, "s-sf-whole"), ev).returncode == 2
    t2 = _transcript(tmp_path, [("Bash", {"command": section_read_command(104)})])
    r2 = _run("read_gate.py", _payload(root, rel, t2, "s-sf-green"), ev)
    assert r2.returncode == 0, r2.stderr
    assert _evidence(ev, "s-sf-green")[-1]["status"] == "read" and _evidence(ev, "s-sf-green")[-1]["adrs"] == [104]


@pytest.mark.parametrize(
    "command",
    ['grep -n "^## ADR-104" docs/project_notes/decisions.md', "sed -n '/^## ADR-104/,/^## ADR-105/p' /x/docs/project_notes/decisions.md"],
)
def test_single_file_layout_accepts_any_targeted_read(tmp_path, command):
    root = _fake_single_file_repo(tmp_path)
    t = _transcript(tmp_path, [("Bash", {"command": command})])
    assert _run("read_gate.py", _payload(root, "config/authored_semantics.yaml", t, "s-sf-any"), tmp_path / "ev").returncode == 0


def test_single_file_layout_unknown_number_is_a_map_error_not_a_block(tmp_path):
    root = _fake_single_file_repo(tmp_path, adrs=[999])
    ev = tmp_path / "ev"
    assert _run("read_gate.py", _payload(root, "config/authored_semantics.yaml", _transcript(tmp_path, []), "s-sf-999"), ev).returncode == 0
    assert ("map_error", [999]) in [(e["status"], e.get("unresolved_adrs")) for e in _evidence(ev, "s-sf-999")]


def test_editing_decisions_md_itself_is_not_gated(tmp_path):
    root = _fake_single_file_repo(tmp_path)
    (root / ".claude/adr_map.json").write_text(json.dumps({"rules": [{"paths": ["docs/**"], "adrs": [104]}]}))
    assert _run("read_gate.py", _payload(root, "docs/project_notes/decisions.md", _transcript(tmp_path, []), "s-sf-self"), tmp_path / "ev").returncode == 0


# --- enforce mode ----------------------------------------------------------------


def test_enforce_mode_carries_packet_and_receipt(tmp_path):
    root = _fake_repo(tmp_path)
    ev = tmp_path / "ev"
    env = {"KMEM_ENFORCE": "1", "KMEM_INDEX_DIR": str(tmp_path / "ctx")}
    t0 = _transcript(tmp_path, [("Bash", {"command": "ls"})])
    r = _run("read_gate.py", _payload(root, GOVERNED, t0, "s-enf-red"), ev, env)
    assert r.returncode == 2, r.stderr
    assert "Context packet" in r.stderr and "Receipt: CTX-" in r.stderr
    denied = _evidence(ev, "s-enf-red")[-1]
    assert denied["status"] == "denied" and denied["mode"] == "enforce" and denied["receipt"].startswith("CTX-")
    t1 = _transcript(tmp_path, [("Read", {"file_path": str(root / "docs/project_notes/decisions/ADR-102-desk-feeds.md")})])
    r1 = _run("read_gate.py", _payload(root, GOVERNED, t1, "s-enf-green"), ev, env)
    assert r1.returncode == 0, r1.stderr
    read = _evidence(ev, "s-enf-green")[-1]
    assert read["status"] == "read" and read["mode"] == "enforce" and read["receipt"].startswith("CTX-")
    shadow = [e for e in _evidence(ev, "s-enf-green") if e["status"] == "shadow"][-1]
    assert shadow["classification"] == "MATCH" and shadow["repo"]


def test_enforce_mode_falls_back_to_the_map_when_the_resolver_fails(tmp_path):
    """PROOF OF RED for fail-safe: a broken resolver in enforce mode still DENIES from the map and logs `fallback`."""
    root = _fake_repo(tmp_path)
    ev = tmp_path / "ev"
    not_a_dir = tmp_path / "not-a-dir"
    not_a_dir.write_text("x")
    env = {"KMEM_ENFORCE": "1", "KMEM_INDEX_DIR": str(not_a_dir / "x")}
    r = _run("read_gate.py", _payload(root, GOVERNED, _transcript(tmp_path, [("Bash", {"command": "ls"})]), "s-enf-fb"), ev, env)
    assert r.returncode == 2, r.stderr
    assert "Context packet: unavailable" in r.stderr
    statuses = [e["status"] for e in _evidence(ev, "s-enf-fb")]
    assert "fallback" in statuses and statuses[-1] == "denied"


def test_shadow_mode_deny_message_is_unchanged_by_the_packet(tmp_path):
    root = _fake_repo(tmp_path)
    r = _run("read_gate.py", _payload(root, GOVERNED, _transcript(tmp_path, [("Bash", {"command": "ls"})]), "s-shadow"), tmp_path / "ev")
    assert r.returncode == 2 and "Context packet" not in r.stderr


# --- Bash commands that write a governed path go through the same gate ---------------


def _bash_payload(root: Path, command: str, transcript: Path, session: str, cwd: Path | None = None) -> dict:
    return {"session_id": session, "transcript_path": str(transcript), "tool_name": "Bash", "cwd": str(cwd or root), "tool_input": {"command": command}}


@pytest.mark.parametrize(
    "command",
    [
        f"sed -i 's/x = 1/x = 2/' {GOVERNED}",
        f"sed -i.bak -e 's/a/b/' {GOVERNED}",
        f"echo 'x = 2' > {GOVERNED}",
        f"printf 'y\\n' >> {GOVERNED}",
        f"cat > {GOVERNED} <<'EOF'\nx = 2\nEOF",
        f"cat /dev/null | tee {GOVERNED}",
        f"cp /tmp/other.py {GOVERNED}",
        f"mv /tmp/other.py {GOVERNED}",
        "cp /tmp/desk_read.py src/gateway/",
        f"python3 -c \"open('{GOVERNED}', 'w').write('x = 2')\"",
        f"python3 - <<'EOF'\nwith open(\"{GOVERNED}\", \"a\") as f:\n    f.write('z')\nEOF",
        "cd src && sed -i 's/a/b/' gateway/desk_read.py",
        f"perl -pi -e 's/a/b/' {GOVERNED}",
        f"rm -f {GOVERNED}",
        f"git checkout -- {GOVERNED}",
        f"FOO=1 sudo sed -i 's/a/b/' {GOVERNED} 2>/dev/null",
    ],
)
def test_bash_write_shaped_command_is_denied_without_a_read(tmp_path, command):
    """PROOF OF RED: every write shape on a governed path is refused with no read."""
    root = _fake_repo(tmp_path)
    ev = tmp_path / "ev"
    r = _run("read_gate.py", _bash_payload(root, command, _transcript(tmp_path, [("Bash", {"command": "ls"})]), "s-bash-red"), ev)
    assert r.returncode == 2, (command, r.stderr)
    assert "the gate parsed it" in r.stderr and "ADR-102-desk-feeds.md" in r.stderr
    last = _evidence(ev, "s-bash-red")[-1]
    assert last["status"] == "denied" and last["via"] == "bash" and last["file"] == GOVERNED


@pytest.mark.parametrize(
    "command",
    [
        f"sed -n 1,40p {GOVERNED}",
        f"grep -n 'x' {GOVERNED}",
        f"cat {GOVERNED} | head -5",
        f"python3 -c \"print(open('{GOVERNED}').read())\"",
        "echo hello > /tmp/not-governed.txt",
        "sed -i 's/a/b/' README.md",
        f"ls -la {GOVERNED} 2>&1",
        "git status --short",
    ],
)
def test_bash_read_only_or_ungoverned_command_is_never_gated(tmp_path, command):
    root = _fake_repo(tmp_path)
    (root / "README.md").write_text("r\n")
    ev = tmp_path / "ev"
    r = _run("read_gate.py", _bash_payload(root, command, _transcript(tmp_path, []), "s-bash-ro"), ev)
    assert r.returncode == 0, (command, r.stderr)
    assert not [e for e in _evidence(ev, "s-bash-ro") if e.get("file") == GOVERNED]


def test_bash_write_is_allowed_after_the_read(tmp_path):
    root = _fake_repo(tmp_path)
    ev = tmp_path / "ev"
    t = _transcript(tmp_path, [("Bash", {"command": "sed -n 1,40p docs/project_notes/decisions/ADR-102-desk-feeds.md"})])
    r = _run("read_gate.py", _bash_payload(root, f"sed -i 's/a/b/' {GOVERNED}", t, "s-bash-green"), ev)
    assert r.returncode == 0, r.stderr
    last = _evidence(ev, "s-bash-green")[-1]
    assert last["status"] == "read" and last["via"] == "bash"


def test_bash_write_candidates_parser():
    cands = gate.bash_write_candidates("cd a && sed -i 's/x/y/' b/c.py; echo 1 > d.txt 2>/dev/null | tee -a e.log; cp f g/; rm h")
    assert {"b/c.py", "d.txt", "/dev/null", "e.log", "g/", "g/f", "h"} <= set(cands)
    assert "s/x/y/" in cands  # junk survives here and dies at the repo/map filter
    assert gate.bash_write_candidates("sed -n 1,5p x.py; grep -r foo .; cat y") == []
    assert gate.bash_write_candidates("python3 -c \"open('z.py','w')\"") == ["z.py"]


def test_bash_targets_resolve_against_cd_and_only_under_a_mapped_repo(tmp_path):
    root = _fake_repo(tmp_path)
    assert gate.bash_write_targets("cd src && sed -i 's/a/b/' gateway/desk_read.py", root) == [root / GOVERNED]
    assert gate.bash_write_targets("echo x > /tmp/elsewhere.txt", root) == []


@pytest.mark.parametrize(
    "tool_name,tool_input",
    [
        ("mcp__filesystem__write_file", {"path": "{root}/" + GOVERNED, "content": "x"}),
        ("mcp__filesystem__edit_file", {"path": "{root}/" + GOVERNED, "edits": []}),
        ("mcp__filesystem__move_file", {"source": "{root}/" + GOVERNED, "destination": "{root}/src/gateway/moved.py"}),
        ("NotebookEdit", {"notebook_path": "{root}/" + GOVERNED}),
    ],
)
def test_mcp_and_notebook_writes_are_gated(tmp_path, tool_name, tool_input):
    root = _fake_repo(tmp_path)
    payload = {
        "session_id": "s-mcp",
        "transcript_path": str(_transcript(tmp_path, [])),
        "tool_name": tool_name,
        "tool_input": {k: (v.replace("{root}", str(root)) if isinstance(v, str) else v) for k, v in tool_input.items()},
    }
    r = _run("read_gate.py", payload, tmp_path / "ev")
    assert r.returncode == 2, r.stderr
    assert _evidence(tmp_path / "ev", "s-mcp")[-1]["via"] == "tool"


# --- the sweep logs a governed change that has no read line -----------------------------


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-C", str(cwd), *args],
        check=True, capture_output=True, text=True, timeout=30,
    )


def test_sweep_logs_unevidenced_change_once_and_names_the_adrs(tmp_path):
    """PROOF OF RED: a governed file changed by a command the gate never saw is logged `unevidenced`."""
    root = _fake_repo(tmp_path)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    ev = tmp_path / "ev"
    t = tmp_path / "s.jsonl"
    t.write_text(json.dumps({"type": "user", "timestamp": "2020-01-01T00:00:00Z", "message": {"role": "user", "content": "go"}}) + "\n")
    (root / GOVERNED).write_text("x = 2\n")  # the bypass
    payload = {"session_id": "s-sweep", "transcript_path": str(t), "cwd": str(root), "tool_name": "Bash", "tool_input": {"command": "true"}}
    r = _run("sweep.py", payload, ev)
    assert r.returncode == 0
    assert "unevidenced" in r.stdout and GOVERNED in r.stdout and "ADR-102" in r.stdout
    lines = [e for e in _evidence(ev, "s-sweep") if e["status"] == "unevidenced"]
    assert len(lines) == 1 and lines[0]["file"] == GOVERNED and lines[0]["adrs"] == [102] and lines[0]["via"] == "sweep"
    r2 = _run("sweep.py", payload, ev)
    assert r2.returncode == 0 and r2.stdout == ""
    assert len([e for e in _evidence(ev, "s-sweep") if e["status"] == "unevidenced"]) == 1


def test_sweep_ignores_files_with_a_read_line_and_ungoverned_files(tmp_path):
    root = _fake_repo(tmp_path)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    ev = tmp_path / "ev"
    ev.mkdir()
    (ev / "s-sweep2.jsonl").write_text(json.dumps({"session": "s-sweep2", "file": GOVERNED, "status": "read", "adrs": [102]}) + "\n")
    t = tmp_path / "s.jsonl"
    t.write_text(json.dumps({"type": "user", "timestamp": "2020-01-01T00:00:00Z"}) + "\n")
    (root / GOVERNED).write_text("x = 3\n")
    (root / "README.md").write_text("changed\n")
    payload = {"session_id": "s-sweep2", "transcript_path": str(t), "cwd": str(root), "tool_name": "Bash", "tool_input": {"command": "true"}}
    r = _run("sweep.py", payload, ev)
    assert r.returncode == 0 and r.stdout == ""
    assert not [e for e in _evidence(ev, "s-sweep2") if e["status"] == "unevidenced"]


# --- the acceptance, on example/ -----------------------------------------------------------


def test_acceptance_on_the_example_repo(tmp_path):
    """Unread governed Edit refused; allowed after the read; `sed -i` refused via bash; the sweep logs a bypass."""
    import shutil

    root = tmp_path / "example"
    shutil.copytree(EXAMPLE, root)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    ev = tmp_path / "ev"
    target = "src/billing/invoice.py"
    t0 = _transcript(tmp_path, [("Bash", {"command": "ls"})])
    r = _run("read_gate.py", _payload(root, target, t0, "s-acc"), ev)
    assert r.returncode == 2 and "ADR-001-invoice-rounding.md" in r.stderr and "ADR-002-tax-table-source.md" in r.stderr
    t1 = _transcript(
        tmp_path,
        [
            ("Read", {"file_path": str(root / "docs/project_notes/decisions/ADR-001-invoice-rounding.md")}),
            ("Read", {"file_path": str(root / "docs/project_notes/decisions/ADR-002-tax-table-source.md")}),
        ],
    )
    assert _run("read_gate.py", _payload(root, target, t1, "s-acc"), ev).returncode == 0
    r = _run("read_gate.py", _bash_payload(root, f"sed -i 's/CENT/PENNY/' {target}", t0, "s-acc-bash"), ev)
    assert r.returncode == 2 and _evidence(ev, "s-acc-bash")[-1]["via"] == "bash"
    ts = tmp_path / "sweep.jsonl"
    ts.write_text(json.dumps({"type": "user", "timestamp": "2020-01-01T00:00:00Z"}) + "\n")
    (root / "src/billing/tax.py").write_text("changed = True\n")
    r = _run("sweep.py", {"session_id": "s-acc-sweep", "transcript_path": str(ts), "cwd": str(root), "tool_name": "Bash", "tool_input": {"command": "true"}}, ev)
    assert r.returncode == 0 and "src/billing/tax.py" in r.stdout and "ADR-002" in r.stdout and "ADR-004" in r.stdout
    assert [e for e in _evidence(ev, "s-acc-sweep") if e["status"] == "unevidenced"][0]["file"] == "src/billing/tax.py"
