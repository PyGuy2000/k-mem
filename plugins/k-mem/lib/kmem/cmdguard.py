"""``.claude/commands.json``: the commands a repo pins, and the commands whose
whole output is the evidence.

WHY. The read gate covers writes. It cannot cover a wrong conclusion, because
a conclusion makes no tool call. Two reading mistakes are the exception: they
are Bash commands, a PreToolUse hook sees them before they run, and both are
refusable from the command text alone.

1. The wrong interpreter. ``CLAUDE.md`` names the repo's python and the repo's
   own index generator. A session runs the ambient ``python`` and the generic
   command instead, gets a different answer, and reports a green gate as red.
2. Truncated evidence. A listing of thirteen lines piped through ``tail -12``
   is missing one. The missing line then gets reported as absent, and absence
   has many causes.

Both rules are declaration-driven. The hook guesses nothing and reads nothing
but this file:

.. code-block:: json

    {
      "pinned": {
        "python": ".venv/bin/python",
        "pytest": ".venv/bin/python -m pytest",
        "kmem notes index": "python3 scripts/gen_index.py"
      },
      "evidence_commands": ["kmem inventory", "scripts/registry_list.py"]
    }

``pinned`` maps a command to the form this repo requires. A bare key matches
the basename of the first token, so ``python`` catches ``/usr/bin/python`` but
not ``python3``; declare both names if you want both. A key that is a path
matches as a path, so ``scripts/gen_index.py`` catches ``./scripts/gen_index.py``
but not some other ``gen_index.py``. A multi-word key (``kmem notes index``)
matches that token prefix, which is how a subcommand gets pinned without
pinning the whole tool. An invocation that already starts with the pinned
form's own first token is allowed, so the pinned command never refuses itself.

``evidence_commands`` lists commands whose full output is the evidence. One of
them piped into ``head``, ``tail``, ``sed -n`` or ``grep -m`` is refused.

Scope boundary, deliberate: there is NO heuristic over arbitrary commands.
Truncation is only wrong when the output is being read as a complete list, and
that is not visible in the command text. A repo says which commands those are,
or the rule never fires.

Limit, stated: the repo is found from the hook's ``cwd``. A ``cd`` inside the
command is not followed, so a command that changes directory into a declaring
repo is not seen.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from .layout import COMMANDS_REL

#: Stages that drop part of their input whatever the flags.
ALWAYS_TRUNCATING = {"head", "tail"}
#: Stages that truncate only with a flag: basename -> the flag test.
FLAG_TRUNCATING = {"sed": "-n", "grep": "-m", "egrep": "-m", "fgrep": "-m", "rg": "-m"}
#: Leading tokens that wrap the real command.
WRAPPERS = {"sudo", "command", "exec", "nohup", "time", "env", "nice", "timeout", "xargs", "stdbuf"}

_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_NUMBER = re.compile(r"^\d+[a-zA-Z]?$")


# --- splitting -------------------------------------------------------------------


def _split(text: str, seps: tuple[str, ...]) -> list[str]:
    """Split on ``seps`` outside quotes. Longest separator first wins."""
    seps = tuple(sorted(seps, key=len, reverse=True))
    out: list[str] = []
    buf: list[str] = []
    quote = ""
    i = 0
    while i < len(text):
        c = text[i]
        if quote:
            buf.append(c)
            if c == quote:
                quote = ""
            i += 1
            continue
        if c in "'\"":
            quote = c
            buf.append(c)
            i += 1
            continue
        hit = next((s for s in seps if text.startswith(s, i)), None)
        if hit:
            out.append("".join(buf))
            buf = []
            i += len(hit)
            continue
        buf.append(c)
        i += 1
    out.append("".join(buf))
    return [s.strip() for s in out if s.strip()]


def pipelines(command: str) -> list[str]:
    """The command split into pipelines: ``&&``, ``||``, ``;`` and newlines separate them."""
    return _split(command, ("&&", "||", ";", "\n"))


def stages(pipeline: str) -> list[str]:
    """One pipeline split into its piped stages."""
    return _split(pipeline, ("|&", "|"))


def tokens(stage: str) -> list[str]:
    try:
        return shlex.split(stage)
    except ValueError:
        return stage.split()


def command_tokens(stage: str) -> list[str]:
    """Tokens of ``stage`` with env assignments and wrappers stripped from the front."""
    out = tokens(stage)
    while out and (_ENV_ASSIGN.match(out[0]) or out[0] in WRAPPERS):
        out.pop(0)
        while out and (out[0].startswith("-") or _NUMBER.match(out[0])):
            out.pop(0)
    return out


# --- the declaration file ---------------------------------------------------------


def find_commands_root(start: Path | None = None) -> Path | None:
    """The nearest ancestor (or ``start`` itself) that declares its commands."""
    cur = Path(start or Path.cwd())
    try:
        cur = cur.resolve()
    except OSError:
        return None
    cur = cur if cur.is_dir() else cur.parent
    for p in [cur, *cur.parents]:
        if (p / COMMANDS_REL).is_file():
            return p
    return None


def load_commands(root: Path) -> dict | None:
    """``{"pinned": {...}, "evidence_commands": [...]}``, or None when absent or unreadable.

    Unreadable is None, not an error: a broken file must never block a session.
    """
    try:
        data = json.loads((Path(root) / COMMANDS_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    raw_pinned = data.get("pinned")
    raw_evidence = data.get("evidence_commands")
    pinned = {}
    if isinstance(raw_pinned, dict):
        pinned = {str(k).strip(): str(v).strip() for k, v in raw_pinned.items() if str(k).strip() and str(v).strip()}
    evidence = []
    if isinstance(raw_evidence, list):
        evidence = [str(c).strip() for c in raw_evidence if str(c).strip()]
    if not pinned and not evidence:
        return None
    return {"pinned": pinned, "evidence_commands": evidence}


# --- matching ----------------------------------------------------------------------


def _head_match(written: str, want: str) -> bool:
    """Does the first token ``written`` name the declared command ``want``?

    A bare name is matched on the basename, so ``python`` catches
    ``/usr/bin/python``. A declared path is matched as a path, so
    ``scripts/list.py`` catches ``./scripts/list.py`` and an absolute path to
    the same file, but not some other ``list.py`` elsewhere in the tree.
    """
    if "/" not in want:
        return Path(written).name == want
    w = written[2:] if written.startswith("./") else written
    return w == want or w.endswith("/" + want)


def _prefix_match(toks: list[str], phrase: str) -> bool:
    """True when ``toks`` starts with ``phrase``; token 0 is matched by ``_head_match``."""
    want = phrase.split()
    if not want or len(toks) < len(want):
        return False
    if not _head_match(toks[0], want[0]):
        return False
    return toks[1 : len(want)] == want[1:]


def _longest_match(toks: list[str], phrases: list[str]) -> str | None:
    hits = [p for p in phrases if _prefix_match(toks, p)]
    return max(hits, key=lambda p: len(p.split())) if hits else None


def truncating(stage: str) -> str | None:
    """The name of the truncation in ``stage``, or None."""
    toks = command_tokens(stage)
    if not toks:
        return None
    head = Path(toks[0]).name
    if head in ALWAYS_TRUNCATING:
        return head
    flag = FLAG_TRUNCATING.get(head)
    if flag and any(t == flag or (t.startswith(flag) and not t.startswith(flag + "-")) for t in toks[1:]):
        return f"{head} {flag}"
    return None


def pinned_violations(command: str, pinned: dict[str, str]) -> list[tuple[str, str, str]]:
    """``(key, the form written, the form required)`` for each stage calling a pinned tool bare."""
    if not pinned:
        return []
    keys = list(pinned)
    allowed_heads = {tokens(v)[0] for v in pinned.values() if tokens(v)}
    hits: list[tuple[str, str, str]] = []
    for pipeline in pipelines(command):
        for stage in stages(pipeline):
            toks = command_tokens(stage)
            if not toks or toks[0] in allowed_heads:
                continue
            key = _longest_match(toks, keys)
            if key:
                hits.append((key, " ".join(toks[: len(key.split())]), pinned[key]))
    return hits


def truncation_violations(command: str, evidence_commands: list[str]) -> list[tuple[str, str, str]]:
    """``(declared command, the truncation, the pipeline)`` for each truncated evidence command."""
    if not evidence_commands:
        return []
    hits: list[tuple[str, str, str]] = []
    for pipeline in pipelines(command):
        st = stages(pipeline)
        if len(st) < 2:
            continue
        for i, stage in enumerate(st):
            declared = _longest_match(command_tokens(stage), evidence_commands)
            if not declared:
                continue
            for later in st[i + 1 :]:
                cut = truncating(later)
                if cut:
                    hits.append((declared, cut, pipeline))
                    break
            break
    return hits


# --- the refusal ---------------------------------------------------------------------


def message(root: Path, pins: list[tuple[str, str, str]], cuts: list[tuple[str, str, str]]) -> str:
    rel = (Path(root) / COMMANDS_REL).as_posix()
    lines = ["COMMAND GUARD: this command was not run. Re-issue it in the form below."]
    for key, written, required in pins:
        lines += [
            "",
            f"PINNED TOOLING. `{written}` is not the {key} this repo uses.",
            f"  required: {required}",
            "  Declared in " + rel + ". The ambient tool can answer differently from the pinned one,",
            "  which turns a green gate red and a red gate green.",
        ]
    for declared, cut, pipeline in cuts:
        lines += [
            "",
            f"TRUNCATED EVIDENCE. `{declared}` is declared as a command whose whole output is the evidence,",
            f"  and this pipeline drops part of it with `{cut}`:",
            f"    {pipeline}",
            "  Run it untruncated and read the whole output. A missing line in a cut listing is not",
            "  evidence that the line does not exist.",
        ]
    lines += [
        "",
        "This hook ran nothing and changed nothing. Re-issue the corrected command; it will pass.",
    ]
    return "\n".join(lines)
