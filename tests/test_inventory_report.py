"""The inventory (repos from config) and the evidence report."""

from __future__ import annotations

import json
from pathlib import Path

from kmem import inventory, report
from kmem.config import Config


def _repo(tmp_path: Path, name: str) -> Path:
    base = tmp_path / name
    (base / "config").mkdir(parents=True)
    (base / "config/rules.yaml").write_text("# Rules for the thing\nx: 1\n", encoding="utf-8")
    (base / "docs/project_notes/decisions").mkdir(parents=True)
    (base / "docs/project_notes/STATE.md").write_text("# STATE of the app\n", encoding="utf-8")
    (base / "docs/project_notes/decisions/ADR-001-x.md").write_text("## ADR-001: The first one\n", encoding="utf-8")
    (base / "CLAUDE.md").write_text("# Guardrails\n", encoding="utf-8")
    (base / "node_modules/pkg").mkdir(parents=True)
    (base / "node_modules/pkg/CLAUDE.md").write_text("# not ours\n", encoding="utf-8")
    return base


def test_inventory_lists_configured_repos_decisions_and_handoffs(tmp_path, isolated_env):
    cfg = Config.defaults(isolated_env)
    cfg.repos = {"my_app": _repo(tmp_path, "my_app"), "missing": tmp_path / "missing"}
    handoffs = cfg.handoffs_dir
    (handoffs / "pending").mkdir(parents=True)
    (handoffs / "archive").mkdir(parents=True)
    (handoffs / "pending/20260910-1200__my_app__to__other_app.md").write_text("---\nsubject: Boundary decided\n---\n", encoding="utf-8")
    (handoffs / "archive/20260701-0900__other_app__to__my_app.md").write_text("# Old note\n", encoding="utf-8")
    text = inventory.render(cfg)
    assert "## my_app" in text and "## missing" not in text
    assert "**authored config**" in text and "`my_app/config/rules.yaml` — Rules for the thing" in text
    assert "`my_app/docs/project_notes/STATE.md` — STATE of the app" in text
    assert "`my_app/CLAUDE.md`" in text and "node_modules" not in text
    assert "**my_app** (1 ADRs)" in text and "- ADR-001: The first one" in text
    assert "## handoffs" in text
    assert "20260910 my_app -> other_app — Boundary decided" in text
    assert "20260701 other_app -> my_app — Old note" in text
    assert "ok" in inventory.stats_line(text, cfg.inventory_line_budget)


def test_inventory_with_no_repos_says_so(isolated_env):
    text = inventory.render(Config.defaults(isolated_env))
    assert "No configured repo is present" in text


def _line(**kw) -> str:
    return json.dumps(kw)


def test_report_counts_classifications_decisions_and_bypasses(tmp_path):
    ev = tmp_path / "evidence"
    ev.mkdir()
    (ev / "s1.jsonl").write_text(
        "\n".join(
            [
                _line(ts="2026-09-10T10:00:00", status="shadow", session="s1", repo="my_app", classification="MATCH", receipt="CTX-1"),
                _line(ts="2026-09-11T10:00:00", status="shadow", session="s1", repo="my_app", classification="RESOLVER_EXTRA", file="a.py", existing=[1], resolver_mandatory=[1, 2], resolver_advisory=["x"], collisions=["parked_plan:my_app:P-01"]),
                _line(ts="2026-09-11T10:01:00", status="shadow", session="s1", error="boom", file="b.py"),
                _line(ts="2026-09-11T10:02:00", status="read", session="s1", via="bash", receipt="CTX-2", file="a.py"),
                _line(ts="2026-09-11T10:03:00", status="denied", session="s1", via="tool", receipt="CTX-3", file="a.py"),
                _line(ts="2026-09-11T10:04:00", status="unevidenced", session="s1", repo="my_app", file="c.py", adrs=[3]),
                _line(ts="2026-09-11T10:05:00", status="fallback", session="s1", file="a.py", error="timeout"),
                "not json",
            ]
        ),
        encoding="utf-8",
    )
    rep = report.build(ev)
    assert rep["shadow_lines"] == 3 and rep["sessions"] == 1
    assert rep["by_classification"] == {"MATCH": 1, "RESOLVER_EXTRA": 1, "error": 1}
    assert rep["by_repo"] == {"my_app": 2, "(repo unrecorded)": 1}
    assert rep["lines_with_advisory"] == 1 and rep["lines_with_collisions"] == 1
    assert len(rep["non_match"]) == 1 and len(rep["errors"]) == 1
    assert rep["gate_decisions_with_receipt"] == 2 and rep["bash_commands_gated"] == 1
    assert len(rep["unevidenced"]) == 1 and len(rep["fallbacks"]) == 1
    text = report.render(rep, ev)
    assert "shadow lines: 3" in text and "RESOLVER_EXTRA" in text and "unevidenced changes" in text
    since = report.build(ev, since="2026-09-11")
    assert since["shadow_lines"] == 2
    assert report.build(tmp_path / "nowhere")["shadow_lines"] == 0
