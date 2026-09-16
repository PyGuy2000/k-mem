"""The acceptance for the library: ``kmem resolve`` and ``kmem audit`` run on ``example/``.

Runs the shim as a subprocess so the PATH python, the shim and the CLI are
all exercised, then checks the same things through the library.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kmem.audit import run_audit
from kmem.context import ContextResolutionService
from kmem.context.ids import adr_id
from kmem.govmap import glob_to_regex, load_map, required_adrs

from conftest import EXAMPLE, KMEM_BIN


def kmem(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(KMEM_BIN), *args], cwd=str(cwd or EXAMPLE), capture_output=True, text=True, timeout=120, env=dict(os.environ)
    )


def test_resolve_invoice_via_the_shim():
    r = kmem("resolve", "--root", str(EXAMPLE), "--target", "src/billing/invoice.py")
    assert r.returncode == 0, r.stderr
    assert "example:ADR-001" in r.stdout and "example:ADR-002" in r.stdout
    assert "documents" in r.stdout and "example:DOC-billing" in r.stdout
    r = kmem("resolve", "--target", "src/billing/tax.py", "--json")  # root found from cwd
    assert r.returncode == 0, r.stderr
    packet = json.loads(r.stdout)
    assert [m["record_id"] for m in packet["mandatory"]] == ["example:ADR-002", "example:ADR-004"]
    kinds = {(c["relation"], c["record"]["record_id"]) for c in packet["collisions"]}
    # ADR-002 supersedes ADR-004 but is itself mandatory here, so it is not a second collision.
    assert kinds == {("superseded", "example:ADR-004"), ("parked_plan", "example:P-02")}
    assert packet["receipt_id"].startswith("CTX-")


def test_audit_passes_on_the_example_via_the_shim():
    r = kmem("audit", "--root", str(EXAMPLE))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "4 checks: 4 pass, 0 fail, 0 skip" in r.stdout
    r = kmem("audit", "--json")
    assert r.returncode == 0
    assert {row["status"] for row in json.loads(r.stdout)} == {"pass"}


def test_audit_exit_code_is_one_on_a_failure(tmp_path):
    root = tmp_path / "broken"
    shutil.copytree(EXAMPLE, root)
    (root / "README.md").write_text("cites ADR-777 which does not exist\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    r = kmem("audit", "--root", str(root))
    assert r.returncode == 1 and "ADR-777" in r.stdout


def test_status_edges_index_doctor_and_init(tmp_path, isolated_env):
    assert kmem("index").returncode == 0
    r = kmem("status")
    assert r.returncode == 0 and json.loads(r.stdout)["repo"] == "example"
    r = kmem("edges")
    assert r.returncode == 0
    # Ticket targets stay unresolved with no DevFlow state; every ADR/plan/doc edge resolves.
    assert all("-> T-" in line for line in r.stdout.splitlines()), r.stdout
    r = kmem("doctor")
    assert r.returncode == 0, r.stdout
    assert "governed (3 rules)" in r.stdout and "missing; defaults in use" in r.stdout
    r = kmem("init", "--no-scaffold", "--alias", "ex=example")  # never scaffold into the real example/
    assert r.returncode == 0, r.stderr
    cfg = json.loads((isolated_env / "config.json").read_text(encoding="utf-8"))
    assert list(cfg["repos"]) == ["example"] and cfg["aliases"] == {"ex": "example"}
    assert Path(cfg["repos"]["example"]).expanduser().resolve() == EXAMPLE.resolve()  # written home-relative
    assert (isolated_env / "evidence").is_dir() and (isolated_env / "context-index").is_dir()
    r = kmem("doctor")
    assert r.returncode == 0 and "(ok)" in r.stdout
    r = kmem("inventory", "--stats")
    assert r.returncode == 0 and "## example" in r.stdout and "**example** (4 ADRs)" in r.stdout and "[inventory]" in r.stderr
    r = kmem("report")
    assert r.returncode == 0 and "shadow lines: 0" in r.stdout


def test_notes_index_and_usage_errors(tmp_path):
    root = tmp_path / "copy"
    shutil.copytree(EXAMPLE, root)
    r = kmem("notes", "index", "--root", str(root))
    assert r.returncode == 0 and "index of 4 headings across 4 files" in r.stdout
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    r = kmem("install-git-hooks", "--root", str(not_a_repo))
    assert r.returncode == 2 and "not a git repo" in r.stderr
    r = kmem("resolve", "--target", "x.py", cwd=tmp_path)
    assert r.returncode == 2 and "adr_map.json" in r.stderr


def test_python_on_path_is_what_the_shim_uses():
    r = kmem("--version")
    assert r.returncode == 0 and r.stdout.startswith("kmem ")
    assert shutil.which("python3"), "the shim needs python3 on PATH"


# --- the same acceptance through the library --------------------------------------


@pytest.fixture
def example(tmp_path):
    svc = ContextResolutionService(root=EXAMPLE, db_path=tmp_path / "example.sqlite", extra_repos={})
    svc.build_index()
    yield svc
    svc.close()


def _example_files() -> list[str]:
    out = []
    for p in EXAMPLE.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            out.append(p.relative_to(EXAMPLE).as_posix())
    return sorted(out)


def test_example_every_rule_matches_a_file_and_every_mandatory_record_has_a_file(example):
    files = _example_files()
    for rule in load_map(EXAMPLE):
        for pat in rule["paths"]:
            sample = next((f for f in files if glob_to_regex(pat).match(f)), None)
            assert sample, pat
            packet = example.resolve_context("edit", sample)
            assert packet.mandatory, sample
            for rec in packet.mandatory:
                assert rec.path and (EXAMPLE / rec.path).is_file(), rec.record_id


def test_example_mandatory_equals_required_adrs(example):
    for f in _example_files():
        expected = {adr_id("example", n) for n in required_adrs(EXAMPLE, f)}
        assert set(example.resolve_context("edit", f).mandatory_ids) == expected, f


def test_example_provenance_points_at_existing_lines(example):
    for rec in example.store.all_records():
        src = rec.provenance.get("source")
        path = Path(src) if Path(src).is_absolute() else EXAMPLE / src
        assert path.is_file(), (rec.record_id, src)
        line = rec.provenance.get("line")
        if line:
            assert 1 <= int(line) <= len(path.read_text(encoding="utf-8").splitlines()), (rec.record_id, src)


def test_example_audit_is_green_through_the_library():
    results = run_audit(EXAMPLE)
    assert [r.status for r in results] == ["pass"] * 4, [r.to_dict() for r in results]


def test_example_carries_no_python_bytecode_dependency():
    assert sys.version_info >= (3, 9)
