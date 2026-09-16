"""The map: glob dialect, required ADRs, and where an ADR lives."""

from __future__ import annotations

import json

from kmem.govmap import (
    adr_location,
    evidence_groups,
    find_repo_root,
    glob_to_regex,
    load_map,
    map_repo_name,
    required_adrs,
    section_read_command,
)


def test_glob_dialect():
    assert glob_to_regex("src/**").match("src/a/b.py")
    assert glob_to_regex("src/**").match("src/x.py")
    assert glob_to_regex("plugins/*/plugin.py").match("plugins/x/plugin.py")
    assert not glob_to_regex("plugins/*/plugin.py").match("plugins/x/y/plugin.py")
    assert glob_to_regex("**/CLAUDE.md").match("CLAUDE.md")
    assert glob_to_regex("**/CLAUDE.md").match("a/b/CLAUDE.md")
    assert glob_to_regex("src/tenant_*.py").match("src/tenant_login.py")
    assert not glob_to_regex("src/tenant_*.py").match("src/tenant/login.py")
    assert glob_to_regex("a/?.py").match("a/b.py") and not glob_to_regex("a/?.py").match("a/bb.py")
    assert not glob_to_regex("src/x.py").match("src/x.pyc")


def _repo(tmp_path, doc: dict):
    root = tmp_path / "repo"
    (root / ".claude").mkdir(parents=True)
    (root / ".claude/adr_map.json").write_text(json.dumps(doc), encoding="utf-8")
    return root


def test_required_adrs_unions_every_matching_rule_once_per_rule(tmp_path):
    root = _repo(
        tmp_path,
        {
            "rules": [
                {"paths": ["src/**", "src/a.py"], "adrs": [1, 2]},
                {"paths": ["src/a.py"], "adrs": [3]},
                {"paths": ["docs/**"], "adrs": [9]},
            ]
        },
    )
    assert required_adrs(root, "src/a.py") == {1, 2, 3}
    assert required_adrs(root, "src/b.py") == {1, 2}
    assert required_adrs(root, "README.md") == set()
    assert len(load_map(root)) == 3


def test_map_repo_name_is_optional(tmp_path):
    assert map_repo_name(_repo(tmp_path, {"rules": []})) is None
    assert map_repo_name(_repo(tmp_path / "b", {"repo": "named", "rules": []})) == "named"


def test_find_repo_root_walks_up(tmp_path):
    root = _repo(tmp_path, {"rules": []})
    deep = root / "a" / "b"
    deep.mkdir(parents=True)
    assert find_repo_root(deep) == root
    assert find_repo_root(deep / "file.py") == root
    assert find_repo_root(tmp_path) is None


def test_adr_location_in_both_layouts(tmp_path):
    root = tmp_path / "repo"
    (root / "docs/project_notes/decisions").mkdir(parents=True)
    (root / "docs/project_notes/decisions/ADR-007-seven.md").write_text("## ADR-007: seven\n", encoding="utf-8")
    (root / "docs/project_notes/decisions.md").write_text("# D\n\n## ADR-012: twelve\nbody\n## ADR-013: x\n", encoding="utf-8")
    path, kind = adr_location(root, 7)
    assert kind == "file" and path.name == "ADR-007-seven.md"
    path, kind = adr_location(root, 12)
    assert kind == "section" and path.name == "decisions.md"
    assert adr_location(root, 99) is None


def test_evidence_groups_and_read_command():
    from pathlib import Path

    assert evidence_groups(7, Path("docs/project_notes/decisions/ADR-007-seven.md"), "file") == [
        ("ADR-007-seven",),
        ("decisions/ADR-007-",),
    ]
    groups = evidence_groups(7, Path("docs/project_notes/decisions.md"), "section")
    assert ("decisions.md", "ADR-007") in groups and ("decisions.md", "ADR-7") in groups
    cmd = section_read_command(7)
    assert "ADR-007" in cmd and "decisions.md" in cmd
