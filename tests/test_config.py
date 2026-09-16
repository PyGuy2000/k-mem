"""The config file: defaults, expansion, round trip, environment overrides."""

from __future__ import annotations

from pathlib import Path

import pytest

from kmem.config import Config, config_path, data_dir, load_config


def test_data_dir_follows_the_environment(isolated_env, monkeypatch):
    assert data_dir() == isolated_env
    monkeypatch.delenv("KMEM_DATA_DIR")
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(isolated_env / "plugin"))
    assert data_dir() == isolated_env / "plugin"
    assert config_path() == isolated_env / "plugin" / "config.json"


def test_data_dir_matches_the_directory_claude_code_creates(tmp_path, monkeypatch):
    """Inside a session Claude Code sets CLAUDE_PLUGIN_DATA to ~/.claude/plugins/data/<plugin>-<marketplace>.

    A shell has no such variable. The first release defaulted to .../data/k-mem,
    so `kmem report` read an empty directory while the hooks wrote next door.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("KMEM_DATA_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    root = home / ".claude" / "plugins" / "data"
    # nothing created yet: the canonical path, which the first session will create
    assert data_dir() == root / "k-mem-k-mem"
    # installed from a marketplace under another name: the one directory that exists wins
    (root / "k-mem-forked").mkdir(parents=True)
    assert data_dir() == root / "k-mem-forked"
    # the canonical name wins over any other
    (root / "k-mem-k-mem").mkdir()
    assert data_dir() == root / "k-mem-k-mem"
    # inside a session the variable wins over discovery
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "from-session"))
    assert data_dir() == tmp_path / "from-session"


def test_defaults_when_no_file(isolated_env):
    cfg = load_config()
    assert cfg.path is None
    assert cfg.repos == {} and cfg.aliases == {}
    assert cfg.index_dir == isolated_env / "context-index"
    assert cfg.evidence_dir == isolated_env / "evidence"
    assert cfg.handoffs_dir == isolated_env / "handoffs"
    assert cfg.enforce is False
    assert cfg.state_budget_tokens == 15_000


def test_from_dict_expands_data_dir_and_home(isolated_env, tmp_path):
    cfg = Config.from_dict(
        {
            "repos": {"my_app": "~/code/my_app", "other_app": str(tmp_path / "other")},
            "aliases": {"app": "my_app"},
            "index_dir": "${CLAUDE_PLUGIN_DATA}/idx",
            "devflow_state": "${CLAUDE_PLUGIN_DATA}/devflow.json",
            "enforce": True,
            "state_budget_tokens": 9000,
            "inventory": {"sections": {"notes": ["docs/*.md"]}, "line_budget": 100},
        },
        isolated_env,
    )
    assert cfg.repos["my_app"] == Path.home() / "code" / "my_app"
    assert cfg.repos["other_app"] == tmp_path / "other"
    assert cfg.index_dir == isolated_env / "idx"
    assert cfg.devflow_state == isolated_env / "devflow.json"
    assert cfg.enforce is True and cfg.state_budget_tokens == 9000
    assert cfg.inventory_sections == {"notes": ["docs/*.md"]} and cfg.inventory_line_budget == 100
    assert cfg.alias_map() == {"my_app": "my_app", "other_app": "other_app", "app": "my_app"}
    assert cfg.known_repos() == {"my_app", "other_app"}


def test_save_and_load_round_trip(isolated_env, tmp_path):
    cfg = Config.defaults(isolated_env)
    cfg.repos = {"my_app": tmp_path / "my_app"}
    cfg.aliases = {"app": "my_app"}
    path = cfg.save()
    assert path == isolated_env / "config.json"
    text = path.read_text(encoding="utf-8")
    assert "${CLAUDE_PLUGIN_DATA}/context-index" in text  # data-dir paths are written portably
    again = load_config()
    assert again.path == path
    assert again.repos == cfg.repos and again.aliases == cfg.aliases
    assert again.index_dir == cfg.index_dir


def test_environment_overrides_win(write_config, monkeypatch, tmp_path):
    write_config(devflow_state=str(tmp_path / "from-file.json"), enforce=False)
    monkeypatch.setenv("DEVFLOW_STATE_PATH", str(tmp_path / "from-env.json"))
    monkeypatch.setenv("KMEM_INDEX_DIR", str(tmp_path / "idx-env"))
    monkeypatch.setenv("KMEM_ENFORCE", "1")
    cfg = load_config()
    assert cfg.devflow_state == tmp_path / "from-env.json"
    assert cfg.index_dir == tmp_path / "idx-env"
    assert cfg.enforce is True


def test_invalid_json_is_an_error(isolated_env):
    isolated_env.mkdir(parents=True)
    (isolated_env / "config.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config()


def test_repo_for_root_matches_a_configured_checkout(tmp_path, isolated_env):
    root = tmp_path / "my_app"
    root.mkdir()
    cfg = Config.defaults(isolated_env)
    cfg.repos = {"my_app": root}
    assert cfg.repo_for_root(root) == "my_app"
    assert cfg.repo_for_root(tmp_path / "elsewhere") is None
