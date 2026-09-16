"""Record ids and reference parsing.

Every ADR-bearing repo restarts at ADR-001, so an unqualified ``ADR-042``
names several decisions. Ids here are ``<repo>:ADR-042``. The prose forms
``app-042``, ``app ADR-042`` and ``app_ADR-042`` all normalise to that when
``app`` is a configured alias (or a repo's own name). Tickets are global:
``T-1042``.

The alias table comes from the config file (``Config.alias_map()``); this
module never hardcodes a repo.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Mapping

_BARE_ADR = r"(?<![\w-])ADR-"
_TICKET_REF = re.compile(r"\bT-(\d{3,4})\b")


def canonical_repo_name(dir_name: str, known: set[str] | frozenset[str] | None = None) -> str:
    """Repo id from a checkout directory name.

    A hosted repo is often named with hyphens while the local checkout uses
    underscores; ids must not depend on which one a machine happened to
    clone into. ``known`` is the set of configured repo names.
    """
    known = set(known or ())
    if dir_name in known:
        return dir_name
    if dir_name.replace("-", "_") in known:
        return dir_name.replace("-", "_")
    if dir_name.replace("_", "-") in known:
        return dir_name.replace("_", "-")
    return dir_name


@lru_cache(maxsize=32)
def _adr_ref_regex(qualifiers: tuple[str, ...]) -> re.Pattern[str]:
    """``ADR-042``, ``app ADR-104``, ``app-042``; a trailing ``/115`` chain
    (``ADR-114/115``, ``app-092/102``) is picked up separately. Long
    qualifiers first so the alternation prefers them."""
    if qualifiers:
        qual = "|".join(re.escape(q) for q in sorted(qualifiers, key=len, reverse=True))
        head = rf"(?:(?<![\w-])(?P<qual>{qual})[\s_'’-]*(?:ADR-?)?|{_BARE_ADR})"
    else:
        head = rf"(?:(?P<qual>(?!x)x)|{_BARE_ADR})"  # a group that never matches keeps the API uniform
    return re.compile(head + r"(?P<num>\d{1,3})(?P<chain>(?:/\d{1,3})*)\b")


def adr_id(repo: str, num: int | str) -> str:
    return f"{repo}:ADR-{int(num):03d}"


def contract_id(repo: str, num: int | str) -> str:
    return f"{repo}:C{int(num)}"


def plan_id(repo: str, pid: str) -> str:
    return f"{repo}:{pid}"


def fact_id(repo: str, stem: str) -> str:
    return f"{repo}:DOC-{stem}"


def ticket_id(num: int | str) -> str:
    return f"T-{int(num):03d}"


def split_id(record_id: str) -> tuple[str | None, str]:
    """``my_app:ADR-042`` -> (repo, ``ADR-042``); ``T-1042`` -> (None, ``T-1042``)."""
    if ":" in record_id:
        repo, _, local = record_id.partition(":")
        return repo, local
    return None, record_id


def adr_number(record_id: str) -> int | None:
    _, local = split_id(record_id)
    m = re.fullmatch(r"ADR-(\d+)", local)
    return int(m.group(1)) if m else None


def find_adr_refs(
    text: str, default_repo: str, aliases: Mapping[str, str] | None = None
) -> list[tuple[str, int, int]]:
    """Every ADR reference in ``text`` as (qualified_id, start, end).

    An unqualified ``ADR-NNN`` belongs to ``default_repo``. A qualifier that
    is a key of ``aliases`` selects that repo. Chains (``ADR-114/115``)
    yield one entry per number.
    """
    aliases = dict(aliases or {})
    rx = _adr_ref_regex(tuple(sorted(aliases)))
    out: list[tuple[str, int, int]] = []
    for m in rx.finditer(text):
        qual = m.group("qual")
        repo = aliases.get(qual, default_repo) if qual else default_repo
        out.append((adr_id(repo, m.group("num")), m.start(), m.end()))
        for extra in m.group("chain").strip("/").split("/") if m.group("chain") else []:
            if extra:
                out.append((adr_id(repo, extra), m.start(), m.end()))
    return out


def find_ticket_refs(text: str) -> list[str]:
    seen: list[str] = []
    for m in _TICKET_REF.finditer(text):
        tid = ticket_id(m.group(1))
        if tid not in seen:
            seen.append(tid)
    return seen
