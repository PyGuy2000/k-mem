"""Fact-doc staleness and the notes budget.

Fact docs under ``docs/individual_readme_files/`` carry frontmatter linking
them to the code they describe and the intent behind it:

    ---
    source_paths:
      - src/etl/loader.py
      - src/etl/adapters/
    last_synced_sha: a3145f5
    adr:
      - ADR-035
    devflow_tickets:
      - T-1451
    ---

``check`` compares each doc's ``last_synced_sha`` against ``git log`` of its
``source_paths`` and reports which docs drifted, plus any project-notes file
over its budget. It is ADVISORY: it flags, it never edits or blocks.

    kmem docs check [--force]      scan for stale docs and budget overruns
    kmem docs stamp FILE           set a doc's last_synced_sha to HEAD
    kmem docs stamp-all            stamp every enrolled doc
    kmem docs init FILE            add a frontmatter skeleton to a doc
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from .config import Config, load_config
from .context.adapters.facts import parse_frontmatter as _parse_block
from .layout import FACT_DOCS_DIR, NOTES_DIR, STATE_MD

REQUIRED = ("source_paths", "last_synced_sha")
#: bugs.md / issues.md are on-demand reads; they get a loose "time to archive" nudge.
NOTES_NUDGE_TOKENS = 80_000
BYTES_PER_TOKEN = 4

SKELETON = """---
# Keep this file FACT-based. Intent lives in README.md and the ADR.
source_paths:        # code this doc describes; drift here flags the doc stale
  - src/
last_synced_sha:     # set with: kmem docs stamp <this-file>  (after you sync it)
adr:                 # durable intent anchor(s), e.g. ADR-035
  - ADR-
devflow_tickets:     # in-flight work, e.g. T-1123 (optional, transient)
  - T-
---

"""


# --- git ---------------------------------------------------------------------


def git(repo: Path | str, *args: str) -> tuple[int, str, str]:
    try:
        out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=15)
        return out.returncode, out.stdout.strip(), out.stderr.strip()
    except (OSError, subprocess.SubprocessError):
        return 1, "", "git-failed"


def git_root(start: Path | str) -> Path | None:
    code, out, _ = git(start, "rev-parse", "--show-toplevel")
    return Path(out) if code == 0 and out else None


def head_sha(repo: Path | str) -> str | None:
    code, out, _ = git(repo, "rev-parse", "HEAD")
    return out if code == 0 and out else None


# --- frontmatter -----------------------------------------------------------------


def split_frontmatter(text: str) -> tuple[str | None, str]:
    if not text.startswith("---"):
        return None, text
    parts = text.split("\n")
    if parts[0].strip() != "---":
        return None, text
    for i in range(1, len(parts)):
        if parts[i].strip() == "---":
            return "\n".join(parts[1:i]), "\n".join(parts[i + 1 :])
    return None, text


def parse_frontmatter(raw: str | None) -> dict:
    if raw is None:
        return {}
    data, _ = _parse_block("---\n" + raw + "\n---\n")
    return data


def as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def enrolled_docs(root: Path) -> list[Path]:
    base = root / FACT_DOCS_DIR
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.md") if p.is_file())


def doc_meta(path: Path) -> dict:
    try:
        raw, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        return parse_frontmatter(raw)
    except OSError:
        return {}


# --- budget ----------------------------------------------------------------------


def _est_tokens(path: Path) -> int | None:
    try:
        return path.stat().st_size // BYTES_PER_TOKEN
    except OSError:
        return None


def budget_lines(root: Path, config: Config) -> list[str]:
    """Advisory lines when project-notes files are over budget. Inert without STATE.md."""
    state = root / STATE_MD
    if not state.is_file():
        return []
    out: list[str] = []
    tok = _est_tokens(state)
    budget = int(config.state_budget_tokens)
    if tok is not None and tok > budget:
        out.append(f"   - STATE.md ~{tok:,} tokens > {budget:,} budget. Prune superseded state; git holds the history.")
    for name in ("bugs.md", "issues.md"):
        tok = _est_tokens(root / NOTES_DIR / name)
        if tok is not None and tok > NOTES_NUDGE_TOKENS:
            out.append(
                f"   - {name} ~{tok:,} tokens > {NOTES_NUDGE_TOKENS:,} nudge; run `kmem notes archive` "
                "to move closed entries past the 90-day cutoff into archive/."
            )
    return out


# --- check -----------------------------------------------------------------------


def cache_path(config: Config, root: Path) -> Path:
    h = hashlib.sha1(str(root).encode()).hexdigest()[:16]
    return config.base / "cache" / f"docsync-{h}"


def drift_for_doc(root: Path, meta: dict) -> tuple[bool | str | None, int]:
    """(stale, n_commits). None when not enrolled, "error" when the sha does not resolve."""
    raw_sha = meta.get("last_synced_sha")
    sha = "" if raw_sha in (None, "", []) else str(raw_sha).strip()
    paths = [str(p).strip() for p in as_list(meta.get("source_paths")) if str(p).strip()]
    if not sha or not paths:
        return None, 0
    code, out, _ = git(root, "log", "--oneline", f"{sha}..HEAD", "--", *paths)
    if code != 0:
        # A doc that CLAIMS enrollment but whose sha is broken must warn, not
        # skip: a silent skip reads as "clean" and defeats the detector.
        return "error", 0
    n = len([line for line in out.split("\n") if line.strip()])
    return (n > 0), n


def check(start: Path, config: Config | None = None, force: bool = False) -> list[str]:
    config = config or load_config()
    root = git_root(start)
    if root is None:
        return []
    enrolled = (root / FACT_DOCS_DIR).is_dir()
    has_state = (root / STATE_MD).is_file()
    if not enrolled and not has_state:
        return []
    head = head_sha(root)
    cp = cache_path(config, root)
    if head and not force:
        try:
            if cp.read_text(encoding="utf-8").strip() == head:
                return []
        except OSError:
            pass
    stale: list[tuple[str, int]] = []
    broken: list[str] = []
    if enrolled:
        for path in enrolled_docs(root):
            is_stale, n = drift_for_doc(root, doc_meta(path))
            rel = path.relative_to(root).as_posix()
            if is_stale == "error":
                broken.append(rel)
            elif is_stale:
                stale.append((rel, n))
    budget = budget_lines(root, config)
    if head:
        try:
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_text(head, encoding="utf-8")
        except OSError:
            pass
    out: list[str] = []
    if broken:
        out.append("docs check: enrolled docs with an UNRESOLVABLE last_synced_sha (staleness cannot be checked; fix the sha with `kmem docs stamp <file>` after verifying the doc):")
        out += [f"   - {rel}" for rel in broken]
    if stale:
        out.append("docs check: fact docs may be stale (source changed since last_synced_sha):")
        out += [f"   - {rel}  ({n} commit{'s' if n != 1 else ''} to its source since sync)" for rel, n in stale]
        out.append("   Review and re-sync them, then `kmem docs stamp <file>`.")
    if budget:
        out.append("docs check: project notes over budget:")
        out += budget
        out.append("   The mandatory session-start load must stay small; prune, do not annotate.")
    return out


# --- stamp / init ------------------------------------------------------------------


def set_frontmatter_field(path: Path, field: str, value: str) -> None:
    text = path.read_text(encoding="utf-8")
    raw, body = split_frontmatter(text)
    if raw is None:
        raise ValueError(f"{path} has no frontmatter (run `kmem docs init` first)")
    lines = raw.split("\n")
    replaced = False
    for i, line in enumerate(lines):
        if line.split(":", 1)[0].strip() == field and not line.startswith((" ", "\t")):
            lines[i] = f"{field}: {value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{field}: {value}")
    path.write_text("---\n" + "\n".join(lines) + "\n---\n" + body, encoding="utf-8")


def stamp(path: Path) -> str:
    path = Path(path)
    root = git_root(path.resolve().parent)
    if root is None:
        raise ValueError("not inside a git repo")
    head = head_sha(root)
    if not head:
        raise ValueError("cannot resolve HEAD")
    set_frontmatter_field(path, "last_synced_sha", head)
    return f"stamped {path} -> {head[:12]}"


def stamp_all(start: Path) -> str:
    root = git_root(start)
    if root is None:
        raise ValueError("not inside a git repo")
    n = 0
    for path in enrolled_docs(root):
        meta = doc_meta(path)
        if all(meta.get(k) for k in REQUIRED):
            stamp(path)
            n += 1
    return f"stamped {n} enrolled doc(s)"


def init(path: Path) -> str:
    path = Path(path)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        raw, _ = split_frontmatter(existing)
        if raw is not None:
            raise ValueError(f"{path} already has frontmatter")
        path.write_text(SKELETON + existing, encoding="utf-8")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SKELETON, encoding="utf-8")
    return f"added frontmatter skeleton to {path}"


__all__ = ["check", "stamp", "stamp_all", "init", "enrolled_docs", "doc_meta", "budget_lines", "SKELETON", "os"]
