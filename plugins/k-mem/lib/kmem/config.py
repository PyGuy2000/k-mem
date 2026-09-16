"""Per-user configuration: ``<data dir>/config.json``.

The data dir is, in order: ``$KMEM_DATA_DIR``, ``$CLAUDE_PLUGIN_DATA`` (set
by Claude Code when a plugin hook runs), else ``~/.claude/plugins/data/k-mem``.
``$KMEM_CONFIG`` names a config file directly.

Everything the hooks and the CLI read comes from this file or from the
governed repo's own ``.claude/`` files. No path is hardcoded anywhere else.

.. code-block:: json

    {
      "repos": {"my_app": "~/code/my_app", "other_app": "~/code/other_app"},
      "aliases": {"app": "my_app", "other": "other_app"},
      "evidence_dir": "${CLAUDE_PLUGIN_DATA}/evidence",
      "index_dir": "${CLAUDE_PLUGIN_DATA}/context-index",
      "handoffs_dir": "${CLAUDE_PLUGIN_DATA}/handoffs",
      "devflow_state": "~/.config/devflow-mcp/devflow_state.json",
      "enforce": false,
      "state_budget_tokens": 15000
    }

``repos`` lists every checkout the resolver and the inventory may read.
``aliases`` maps a short prose qualifier to a repo name, so ``app ADR-012``
and ``app-012`` in a record resolve to ``my_app:ADR-012``.

Environment overrides, for tests and one-off runs: ``DEVFLOW_STATE_PATH``,
``KMEM_INDEX_DIR``, ``KMEM_EVIDENCE_DIR``, ``KMEM_HANDOFFS_DIR``,
``KMEM_ENFORCE`` (``1`` or ``0``).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DATA_DIR_VAR = "${CLAUDE_PLUGIN_DATA}"
DEFAULT_DATA_DIR = Path.home() / ".claude" / "plugins" / "data" / "k-mem"
DEFAULT_DEVFLOW_STATE = "~/.config/devflow-mcp/devflow_state.json"
DEFAULT_STATE_BUDGET_TOKENS = 15_000
DEFAULT_INVENTORY_LINE_BUDGET = 800
#: Which SessionStart sections run. Any can be turned off in the config file.
DEFAULT_SESSION_START: dict[str, bool] = {
    "stale_guard": True,
    "inbox": True,
    "packet": True,
    "inventory": True,
}
#: Inventory sections: label -> globs relative to each repo root.
DEFAULT_INVENTORY_SECTIONS: dict[str, list[str]] = {
    "authored config": ["config/**/*.yaml", "config/**/*.yml"],
    "doc guides": ["docs/individual_readme_files/*.md"],
    "guardrails": ["**/CLAUDE.md"],
    "project notes": [
        "docs/project_notes/STATE.md",
        "docs/project_notes/plans.md",
        "docs/project_notes/decisions.md",
        "docs/project_notes/key_facts.md",
        "docs/project_notes/issues.md",
        "docs/project_notes/bugs.md",
    ],
}


def data_dir() -> Path:
    for var in ("KMEM_DATA_DIR", "CLAUDE_PLUGIN_DATA"):
        value = os.environ.get(var)
        if value:
            return Path(value).expanduser()
    return DEFAULT_DATA_DIR


def config_path() -> Path:
    value = os.environ.get("KMEM_CONFIG")
    return Path(value).expanduser() if value else data_dir() / "config.json"


def expand_path(value: str, base: Path) -> Path:
    """``${CLAUDE_PLUGIN_DATA}`` -> the data dir; then ``$VAR`` and ``~``."""
    text = str(value).replace(DATA_DIR_VAR, str(base)).replace("${KMEM_DATA_DIR}", str(base))
    return Path(os.path.expandvars(text)).expanduser()


def compact_path(path: Path, base: Path) -> str:
    """The inverse of ``expand_path`` for writing the file back."""
    try:
        return DATA_DIR_VAR + "/" + path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        pass
    try:
        return "~/" + path.expanduser().resolve().relative_to(Path.home().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


@dataclass
class Config:
    repos: dict[str, Path] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    evidence_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "evidence")
    index_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "context-index")
    handoffs_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "handoffs")
    devflow_state: Path = field(default_factory=lambda: Path(DEFAULT_DEVFLOW_STATE).expanduser())
    enforce: bool = False
    state_budget_tokens: int = DEFAULT_STATE_BUDGET_TOKENS
    inventory_sections: dict[str, list[str]] = field(
        default_factory=lambda: {k: list(v) for k, v in DEFAULT_INVENTORY_SECTIONS.items()}
    )
    inventory_line_budget: int = DEFAULT_INVENTORY_LINE_BUDGET
    session_start: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_SESSION_START))
    #: Where this config was read from; None for defaults.
    path: Path | None = None
    #: The data dir the relative entries expand against.
    base: Path = field(default_factory=data_dir)

    # --- construction -----------------------------------------------------------

    @classmethod
    def defaults(cls, base: Path | None = None) -> "Config":
        base = Path(base) if base else data_dir()
        return cls(
            evidence_dir=base / "evidence",
            index_dir=base / "context-index",
            handoffs_dir=base / "handoffs",
            base=base,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any], base: Path | None = None) -> "Config":
        cfg = cls.defaults(base)
        base = cfg.base
        repos = data.get("repos") or {}
        cfg.repos = {str(k): expand_path(str(v), base) for k, v in repos.items()}
        cfg.aliases = {str(k): str(v) for k, v in (data.get("aliases") or {}).items()}
        for key in ("evidence_dir", "index_dir", "handoffs_dir", "devflow_state"):
            if data.get(key):
                setattr(cfg, key, expand_path(str(data[key]), base))
        cfg.enforce = bool(data.get("enforce", False))
        cfg.state_budget_tokens = int(data.get("state_budget_tokens", DEFAULT_STATE_BUDGET_TOKENS))
        inv = data.get("inventory") or {}
        if isinstance(inv.get("sections"), dict):
            cfg.inventory_sections = {str(k): [str(g) for g in v] for k, v in inv["sections"].items()}
        if inv.get("line_budget"):
            cfg.inventory_line_budget = int(inv["line_budget"])
        ss = data.get("session_start")
        if isinstance(ss, dict):
            cfg.session_start = {k: bool(ss.get(k, v)) for k, v in DEFAULT_SESSION_START.items()}
        return cfg

    def to_dict(self) -> dict[str, Any]:
        return {
            "repos": {k: compact_path(v, self.base) for k, v in self.repos.items()},
            "aliases": dict(self.aliases),
            "evidence_dir": compact_path(self.evidence_dir, self.base),
            "index_dir": compact_path(self.index_dir, self.base),
            "handoffs_dir": compact_path(self.handoffs_dir, self.base),
            "devflow_state": compact_path(self.devflow_state, self.base),
            "enforce": self.enforce,
            "state_budget_tokens": self.state_budget_tokens,
            "inventory": {"sections": self.inventory_sections, "line_budget": self.inventory_line_budget},
            "session_start": dict(self.session_start),
        }

    def save(self, path: Path | None = None) -> Path:
        target = Path(path) if path else (self.path or config_path())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        self.path = target
        return target

    # --- derived ------------------------------------------------------------------

    def alias_map(self) -> dict[str, str]:
        """Every prose qualifier -> repo name: each repo's own name plus ``aliases``."""
        out = {name: name for name in self.repos}
        out.update(self.aliases)
        return out

    def known_repos(self) -> set[str]:
        return set(self.repos) | set(self.aliases.values())

    def repo_for_root(self, root: Path) -> str | None:
        """The configured name of the checkout at ``root``, if any."""
        try:
            resolved = Path(root).resolve()
        except OSError:
            return None
        for name, path in self.repos.items():
            try:
                if path.resolve() == resolved:
                    return name
            except OSError:
                continue
        return None

    def apply_env(self) -> "Config":
        env = os.environ
        if env.get("DEVFLOW_STATE_PATH"):
            self.devflow_state = Path(env["DEVFLOW_STATE_PATH"]).expanduser()
        if env.get("KMEM_INDEX_DIR"):
            self.index_dir = Path(env["KMEM_INDEX_DIR"]).expanduser()
        if env.get("KMEM_EVIDENCE_DIR"):
            self.evidence_dir = Path(env["KMEM_EVIDENCE_DIR"]).expanduser()
        if env.get("KMEM_HANDOFFS_DIR"):
            self.handoffs_dir = Path(env["KMEM_HANDOFFS_DIR"]).expanduser()
        if env.get("KMEM_ENFORCE") in ("0", "1"):
            self.enforce = env["KMEM_ENFORCE"] == "1"
        return self


def load_config(path: Path | None = None) -> Config:
    """The config file if it exists, else defaults; environment overrides last."""
    target = Path(path).expanduser() if path else config_path()
    base = data_dir()
    if target.is_file():
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"config file {target} is not valid JSON: {exc}") from exc
        cfg = Config.from_dict(data if isinstance(data, dict) else {}, base)
        cfg.path = target
    else:
        cfg = Config.defaults(base)
    return cfg.apply_env()
