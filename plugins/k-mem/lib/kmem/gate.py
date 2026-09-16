"""The read-before-write gate.

WHY. "Read the governing ADR before you edit that subsystem" is a sentence
in a CLAUDE.md. Nothing checks it, so a session can skip the read and still
ship. The gate moves the rule outside the model: a write under a path listed
in ``.claude/adr_map.json`` is DENIED until the session transcript shows the
listed ADRs were read. Reading them and re-issuing the same edit is the only
way through. There is no once-per-session bypass.

Which writes it sees. Write / Edit / MultiEdit / NotebookEdit and the MCP
filesystem write, edit and move tools name their target directly. A Bash
command is parsed for write-shaped operations on a path: ``sed -i``,
``perl -i``, ``awk -i inplace``, ``>`` / ``>>`` / ``&>`` redirects (heredocs
included), ``tee``, ``cp`` / ``mv`` / ``install`` / ``rsync`` / ``ln``
destinations, ``rm`` / ``truncate``, ``git restore|checkout|mv|rm|apply``
targets, and ``open(path, "w"|"a"|"x")`` inside an inline Python script.
Targets resolve against the hook's cwd and against any ``cd <dir>`` in the
command; only a path under a repo that carries a map is considered.
Read-only commands are never gated. A command the parser cannot see through
is the known residual; the PostToolUse sweep logs any governed file that
changed with no read record, so the residual is counted, never silent.

Evidence is written by the hook, not by the model, to
``<evidence_dir>/<session>.jsonl`` (one line per decision: read, denied,
disabled, no_transcript, map_error, shadow, fallback; each carries ``via``:
tool | bash).

Two ADR layouts are first-class: one file per ADR under
``docs/project_notes/decisions/``, or every ADR as a ``## ADR-NNN`` heading
inside one ``docs/project_notes/decisions.md``. A read of a per-file ADR is
any tool_use whose input mentions the file stem or the path shape
``decisions/ADR-NNN-``. A read of a section is any ONE tool_use whose input
names BOTH ``decisions.md`` and ``ADR-NNN``; reading decisions.md without the
number is not evidence for the number. Only completed earlier turns are
visible to a PreToolUse hook, so the read must happen in a turn before the
edit.

Modes. ``shadow`` (default): the map decides; the resolver runs beside it and
is logged. ``enforce`` (``enforce: true`` in the config): the resolver's
mandatory set is unioned into the map's set (it can add, never remove), the
deny message carries the context packet, and read/denied lines carry the
receipt. A resolver failure in enforce mode logs ``fallback`` and the gate
decides from the map: fail-safe, never silently open.

Limits, stated: proves a read happened, not that it was understood; fails
OPEN (allow + log) when the transcript is unreadable or the map is broken,
so a harness fault never blocks all editing; a file named ``DISABLED`` in the
evidence dir (only a human creates it) turns the gate off and every allow is
logged as ``disabled``.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from .config import Config, load_config
from .govmap import adr_location, evidence_groups, find_repo_root, required_adrs, section_read_command
from .layout import DECISIONS_DIR, DECISIONS_MD

#: Tools whose input names the written file directly.
DIRECT_WRITE_TOOLS = {
    "Write", "Edit", "MultiEdit", "NotebookEdit",
    "mcp__filesystem__write_file", "mcp__filesystem__edit_file", "mcp__filesystem__move_file",
}
DISABLED_MARKER = "DISABLED"
SHADOW_BUDGET_SECONDS = 2

# --- Bash command parsing --------------------------------------------------

_SEGMENT_SPLIT = re.compile(r"\s*(?:&&|\|\||;|\||\n)\s*")
_TOKEN = re.compile(r"""'[^']*'|"[^"]*"|\S+""")
_REDIRECT = re.compile(r"""(?:(?<![<>])&>|(?<![<>&])\d?>{1,2}\|?)\s*('[^']*'|"[^"]*"|[^\s;&|<>()]+)""")
_PY_OPEN = re.compile(r"""open\(\s*(?:f?['"])([^'"]+)['"]\s*,\s*['"][wax]""")
_CD = re.compile(r"""(?:^|[;&|]\s*|\s)(?:cd|pushd)\s+('[^']*'|"[^"]*"|[^\s;&|]+)""")
_SED_INPLACE = re.compile(r"^-[a-zA-Z]*i")
_WRAPPERS = {"sudo", "command", "exec", "nohup", "time", "env", "nice", "timeout"}
_COPY_CMDS = {"cp", "mv", "install", "rsync", "ln"}
_REMOVE_CMDS = {"rm", "truncate", "unlink", "shred"}
_GIT_WRITE_SUB = {"restore", "checkout", "mv", "rm", "apply", "stash"}


def _unquote(tok: str) -> str:
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "'\"":
        return tok[1:-1]
    return tok


def _plain_args(words: list[str]) -> list[str]:
    """Positional arguments: no flags, no env assignments, no shell noise."""
    out = []
    for w in words:
        if not w or w.startswith("-") or w.startswith("$") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):
            continue
        out.append(w)
    return out


def _command_words(seg: str) -> tuple[str, list[str]]:
    words = [_unquote(t) for t in _TOKEN.findall(seg)]
    while words and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]) or words[0] in _WRAPPERS):
        words.pop(0)
        if words and words[0].startswith("-"):
            words.pop(0)
    if not words:
        return "", []
    return Path(words[0]).name, words[1:]


def bash_write_candidates(command: str) -> list[str]:
    """Path-shaped tokens in write positions of ``command`` (unresolved, may include junk)."""
    cands: list[str] = []
    for m in _REDIRECT.finditer(command):
        cands.append(_unquote(m.group(1)))
    cands.extend(_PY_OPEN.findall(command))
    for seg in _SEGMENT_SPLIT.split(command):
        cmd, rest = _command_words(seg)
        if not cmd:
            continue
        args = _plain_args(rest)
        if cmd == "sed" and any(_SED_INPLACE.match(w) for w in rest):
            cands.extend(args)
        elif cmd == "perl" and any(w.startswith("-") and "i" in w for w in rest):
            cands.extend(args)
        elif cmd in ("awk", "gawk") and "inplace" in seg:
            cands.extend(args)
        elif cmd == "tee":
            cands.extend(args)
        elif cmd in _COPY_CMDS and len(args) >= 2:
            dest, srcs = args[-1], args[:-1]
            cands.append(dest)
            cands.extend(f"{dest.rstrip('/')}/{Path(s).name}" for s in srcs)
        elif cmd in _REMOVE_CMDS:
            cands.extend(args)
        elif cmd == "git" and args and args[0] in _GIT_WRITE_SUB:
            cands.extend(args[1:])
    seen: set[str] = set()
    out: list[str] = []
    for c in cands:
        c = c.strip()
        if not c or c in seen or c.startswith("-") or c.startswith("$") or c.startswith("&") or c.isdigit():
            continue
        seen.add(c)
        out.append(c)
    return out


def bash_write_targets(command: str, cwd: Path) -> list[Path]:
    """Absolute GOVERNED paths a Bash command writes, resolved against cwd and any ``cd`` in it.

    A candidate survives only when it sits under a repo that carries a map
    AND a rule of that map matches it; junk tokens (a sed script, /dev/null,
    an ungoverned file) never reach the evidence log.
    """
    bases: list[Path] = [Path(cwd)]
    for m in _CD.finditer(command):
        target = Path(os.path.expanduser(_unquote(m.group(1))))
        base = target if target.is_absolute() else bases[-1] / target
        bases.append(Path(os.path.normpath(base)))
    targets: list[Path] = []
    seen: set[str] = set()
    for cand in bash_write_candidates(command):
        cand = os.path.expanduser(cand)
        for base in bases:
            p = Path(cand) if os.path.isabs(cand) else base / cand
            p = Path(os.path.normpath(p))
            if str(p) in seen:
                continue
            seen.add(str(p))
            root = find_repo_root(p)
            if root is None:
                continue
            try:
                rel = p.relative_to(root.resolve()).as_posix() if p.is_absolute() else p.as_posix()
                governed = bool(required_adrs(root, rel))
            except (OSError, ValueError, TypeError):
                governed = False
            if governed:
                targets.append(p)
    return targets


def write_targets(payload: dict) -> list[tuple[Path, str]]:
    """(absolute target, via) pairs for any tool call that writes a file."""
    tool = str(payload.get("tool_name", ""))
    ti = payload.get("tool_input") or {}
    if tool == "Bash":
        cwd = Path(str(payload.get("cwd") or os.getcwd()))
        return [(p, "bash") for p in bash_write_targets(str(ti.get("command", "")), cwd)]
    out: list[tuple[Path, str]] = []
    for key in ("file_path", "path", "notebook_path", "source", "destination"):
        v = ti.get(key)
        if v:
            out.append((Path(str(v)), "tool"))
    return out


# --- transcript ------------------------------------------------------------


def read_groups_in_transcript(transcript: Path, groups: list[tuple[str, ...]]) -> set[int]:
    """Return the indexes of ``groups`` whose every token appears in a single tool_use input."""
    found: set[int] = set()
    pending = {i for i, g in enumerate(groups) if g}
    tokens = {t for g in groups for t in g}
    try:
        with open(transcript, encoding="utf-8", errors="replace") as f:
            for line in f:
                if not pending:
                    break
                if not any(t in line for t in tokens):
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                msg = d.get("message") or {}
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    blob = json.dumps(block.get("input", {}))
                    for i in list(pending):
                        if all(t in blob for t in groups[i]):
                            found.add(i)
                            pending.discard(i)
    except OSError:
        pass
    return found


def is_decision_record(rel: str) -> bool:
    """Editing an ADR itself is governed by the write guard, not by this gate."""
    return rel.startswith(DECISIONS_DIR.as_posix() + "/") or rel == DECISIONS_MD.as_posix()


def packet_lines(compare: dict, limit: int = 12) -> list[str]:
    """The deny-message rendering of the context packet."""
    if "error" in compare:
        return [f"Context packet: unavailable ({compare['error']}); the map above decided this edit."]
    out = ["Context packet (one explicit hop, advisory: read what is relevant, not required):"]
    adv = list(compare.get("resolver_advisory") or [])
    for a in adv[:limit]:
        out.append(f"  - {a}")
    if len(adv) > limit:
        out.append(f"  - ... {len(adv) - limit} more")
    if not adv:
        out.append("  - (none)")
    cols = list(compare.get("collisions") or [])
    out.append("Collisions: " + (", ".join(cols) if cols else "none"))
    if compare.get("receipt"):
        out.append(f"Receipt: {compare['receipt']}")
    return out


# --- the gate ------------------------------------------------------------------


class Gate:
    def __init__(self, config: Config | None = None):
        self.config = config or load_config()

    @property
    def evidence_dir(self) -> Path:
        return self.config.evidence_dir

    @property
    def markers_dir(self) -> Path:
        return self.evidence_dir / "markers"

    def mode(self) -> str:
        return "enforce" if self.config.enforce else "shadow"

    def disabled(self) -> bool:
        return (self.evidence_dir / DISABLED_MARKER).exists()

    def log_evidence(self, session: str, record: dict) -> None:
        try:
            self.evidence_dir.mkdir(parents=True, exist_ok=True)
            record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "session": session, **record}
            with open(self.evidence_dir / f"{session}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except OSError:
            pass

    def session_evidence(self, session: str) -> list[dict]:
        path = self.evidence_dir / f"{session}.jsonl"
        rows: list[dict] = []
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(d, dict):
                        rows.append(d)
        except OSError:
            pass
        return rows

    def marker(self, name: str) -> Path:
        return self.markers_dir / name

    def mark_once(self, name: str) -> bool:
        """True the first time ``name`` is seen; False after. Unrecordable state counts as seen."""
        m = self.marker(name)
        if m.exists():
            return False
        try:
            m.parent.mkdir(parents=True, exist_ok=True)
            m.touch()
        except OSError:
            return False
        return True

    def repo_name(self, root: Path) -> str:
        from .context.compiler import detect_repo_name

        return detect_repo_name(root, self.config)

    def resolver_compare(self, root: Path, rel: str, needed: set[int]) -> dict:
        """Ask the resolver for the same path; never raise into the gate; bounded in time where the OS allows."""
        import signal

        have_alarm = hasattr(signal, "SIGALRM")

        def _alarm(signum, frame):  # noqa: ARG001
            raise TimeoutError(f"resolver exceeded {SHADOW_BUDGET_SECONDS}s")

        previous = None
        if have_alarm:
            previous = signal.signal(signal.SIGALRM, _alarm)
            signal.alarm(SHADOW_BUDGET_SECONDS)
        try:
            from .context import ContextResolutionService

            svc = ContextResolutionService(root=root, config=self.config)
            try:
                return svc.shadow_compare(rel, set(needed))
            finally:
                svc.close()
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        finally:
            if have_alarm:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, previous)

    # --- decision ------------------------------------------------------------

    def decide_for_target(self, session: str, payload: dict, target: Path, via: str) -> tuple[int, str]:
        """The decision for ONE written path. 0 allows, 2 denies."""
        root = find_repo_root(target)
        if root is None:
            return 0, ""
        try:
            rel = target.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return 0, ""

        if self.disabled():
            self.log_evidence(session, {"file": rel, "status": "disabled", "via": via})
            return 0, ""

        try:
            needed = required_adrs(root, rel)
        except (OSError, ValueError, TypeError) as exc:
            self.log_evidence(session, {"file": rel, "status": "map_error", "via": via, "error": str(exc)[:160]})
            return 0, ""
        if not needed:
            return 0, ""
        if is_decision_record(rel):
            return 0, ""

        mode = self.mode()
        compare = self.resolver_compare(root, rel, needed)
        repo = compare.get("repo") or self.repo_name(root)
        if mode == "enforce":
            if "error" in compare:
                self.log_evidence(
                    session,
                    {"file": rel, "status": "fallback", "via": via, "repo": repo, "adrs": sorted(needed), "error": compare["error"]},
                )
            else:
                # The resolver can add to the map's set, never remove from it.
                needed = set(needed) | {int(n) for n in compare.get("resolver_mandatory", [])}
        self.log_evidence(session, {"file": rel, "status": "shadow", "mode": mode, "via": via, "repo": repo, **compare})

        locations: dict[int, tuple[Path, str]] = {}
        unresolved: list[int] = []
        for n in sorted(needed):
            loc = adr_location(root, n)
            if loc is None:
                unresolved.append(n)
            else:
                locations[n] = loc
        if unresolved:
            self.log_evidence(session, {"file": rel, "status": "map_error", "via": via, "repo": repo, "unresolved_adrs": unresolved})
        if not locations:
            return 0, ""

        transcript = Path(str(payload.get("transcript_path", "")))
        if not transcript.is_file():
            self.log_evidence(session, {"file": rel, "status": "no_transcript", "via": via, "repo": repo, "adrs": sorted(locations)})
            return 0, ""

        groups: list[tuple[str, ...]] = []
        owner: list[int] = []
        for n, (path, kind) in locations.items():
            for g in evidence_groups(n, path, kind):
                groups.append(g)
                owner.append(n)
        hit = read_groups_in_transcript(transcript, groups)
        satisfied = {owner[i] for i in hit}
        missing = [n for n in locations if n not in satisfied]
        receipt = compare.get("receipt")
        if not missing:
            line = {"file": rel, "status": "read", "mode": mode, "via": via, "repo": repo, "adrs": sorted(locations)}
            if receipt:
                line["receipt"] = receipt
            self.log_evidence(session, line)
            return 0, ""

        line = {"file": rel, "status": "denied", "mode": mode, "via": via, "repo": repo, "adrs": sorted(locations), "missing": missing}
        if receipt:
            line["receipt"] = receipt
        self.log_evidence(session, line)
        lines = [
            "READ GATE: this edit is refused until the governing ADRs have been read this session.",
            f"File: {rel}" + ("  (written by the Bash command; the gate parsed it)" if via == "bash" else ""),
            "Read these first, then re-issue the identical edit:",
        ]
        for n in missing:
            path, kind = locations[n]
            if kind == "file":
                lines.append(f"  - {path.relative_to(root).as_posix()}  (Read tool, or sed/cat in Bash)")
            else:
                lines.append(f"  - ADR-{n:03d} is a section of {DECISIONS_MD.as_posix()}; print it with one command that names both:")
                lines.append(f"      {section_read_command(n)}")
        if mode == "enforce":
            lines.extend(packet_lines(compare))
        lines.append("Name each ADR you read in your reply. This gate does not expire; there is no second-attempt bypass.")
        return 2, "\n".join(lines)

    def decide(self, payload: dict) -> tuple[int, str]:
        """Return (exit_code, stderr_message) over every path the tool call writes. 0 allows, 2 denies."""
        session = str(payload.get("session_id", "no-session"))
        messages: list[str] = []
        for target, via in write_targets(payload):
            code, msg = self.decide_for_target(session, payload, target, via)
            if code == 2 and msg:
                messages.append(msg)
        if messages:
            return 2, "\n\n".join(messages)
        return 0, ""


def read_payload() -> dict:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def main(argv: list[str] | None = None) -> int:
    payload = read_payload()
    if not payload:
        return 0
    code, msg = Gate().decide(payload)
    if msg:
        print(msg, file=sys.stderr)
    return code
