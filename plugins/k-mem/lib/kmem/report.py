"""The gate evidence report.

Reads every ``<session>.jsonl`` under the evidence dir (``evidence_dir`` in
the config), keeps the ``shadow`` lines and the decision lines (``read``,
``denied``, ``fallback``, ``unevidenced``, ``refused``), and prints counts per
classification plus every non-MATCH line.

MATCH is expected by construction when the map is the only source of
mandatory records. A RESOLVER_EXTRA is a promotion candidate, an
EXISTING_EXTRA or CONFLICT is a resolver bug, an error line is a harness
fault. ``via: bash`` marks a Bash command the gate parsed and judged;
``unevidenced`` marks a governed file that changed with no read line (the
parser's residual, counted so it is never silent).

    kmem report [--since YYYY-MM-DD] [--json]
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

DECISION_STATUSES = ("read", "denied", "fallback", "unevidenced", "refused")


def load(evidence_dir: Path, since: str | None = None, statuses: tuple[str, ...] = ("shadow",)) -> list[dict]:
    rows: list[dict] = []
    if not evidence_dir.is_dir():
        return rows
    for path in sorted(evidence_dir.glob("*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict) or d.get("status") not in statuses:
                continue
            if since and str(d.get("ts", ""))[:10] < since:
                continue
            rows.append(d)
    return rows


def summarise(rows: list[dict], decisions: list[dict] | None = None) -> dict:
    """``rows`` are the shadow lines; ``decisions`` the read/denied/fallback/unevidenced lines of the same window."""
    counts: Counter[str] = Counter()
    for d in rows:
        counts["error" if "error" in d else str(d.get("classification", "?"))] += 1
    advisory_hits = sum(1 for d in rows if d.get("resolver_advisory"))
    collisions = [d for d in rows if d.get("collisions")]
    non_match = [d for d in rows if d.get("classification") not in (None, "MATCH")]
    errors = [d for d in rows if "error" in d]
    # A repo with no map produces no line at all, so absence here means "unwatched", never "clean".
    by_repo: Counter[str] = Counter(str(d.get("repo") or "(repo unrecorded)") for d in rows)
    by_mode: Counter[str] = Counter(str(d.get("mode") or "shadow") for d in rows)
    decisions = decisions or []
    fallbacks = [d for d in decisions if d.get("status") == "fallback"]
    receipts = sum(1 for d in decisions if d.get("status") in ("read", "denied") and d.get("receipt"))
    bash_gated = sum(1 for d in decisions if d.get("status") in ("read", "denied") and d.get("via") == "bash")
    unevidenced = [d for d in decisions if d.get("status") == "unevidenced"]
    refused = [d for d in decisions if d.get("status") == "refused" and d.get("hook") == "command-guard"]
    return {
        "shadow_lines": len(rows),
        "sessions": len({d.get("session") for d in rows}),
        "by_classification": dict(sorted(counts.items())),
        "by_repo": dict(sorted(by_repo.items())),
        "by_mode": dict(sorted(by_mode.items())),
        "lines_with_advisory": advisory_hits,
        "lines_with_collisions": len(collisions),
        "non_match": non_match,
        "errors": errors,
        "collisions": collisions,
        "fallbacks": fallbacks,
        "gate_decisions_with_receipt": receipts,
        "bash_commands_gated": bash_gated,
        "unevidenced": unevidenced,
        "commands_refused": refused,
    }


def build(evidence_dir: Path, since: str | None = None) -> dict:
    return summarise(load(evidence_dir, since), load(evidence_dir, since, DECISION_STATUSES))


def render(report: dict, evidence_dir: Path) -> str:
    out: list[str] = []
    out.append(f"shadow lines: {report['shadow_lines']} across {report['sessions']} session(s)  [{evidence_dir}]")
    for k, v in report["by_classification"].items():
        out.append(f"  {k:<16} {v}")
    out.append(f"  with advisory    {report['lines_with_advisory']}")
    out.append(f"  with collisions  {report['lines_with_collisions']}")
    out.append("by repo (a repo with no .claude/adr_map.json logs nothing; absent means unwatched, not clean):")
    for k, v in report["by_repo"].items():
        out.append(f"  {k:<48} {v}")
    out.append("by gate mode (enforce = the config's enforce flag):")
    for k, v in report["by_mode"].items():
        out.append(f"  {k:<16} {v}")
    out.append(f"  gate decisions carrying a receipt: {report['gate_decisions_with_receipt']}")
    out.append(f"  Bash commands the gate parsed and judged: {report['bash_commands_gated']}")
    out.append(f"  unevidenced changes (governed file changed with no read line): {len(report['unevidenced'])}")
    for d in report["unevidenced"]:
        out.append(f"    {d.get('ts')}  {d.get('repo')}  {d.get('file')}  adrs={d.get('adrs')}")
    out.append(f"  commands refused (pinned tooling / truncated evidence): {len(report['commands_refused'])}")
    for d in report["commands_refused"]:
        why = "pinned" if d.get("pinned") else "truncated"
        out.append(f"    {d.get('ts')}  {d.get('repo')}  {why:<9} {d.get('command')}")
    if report["fallbacks"]:
        out.append("")
        out.append("enforce-mode fallbacks (resolver failed; the map decided):")
        for d in report["fallbacks"]:
            out.append(f"  {d.get('ts')}  {d.get('file')}  {d.get('error')}")
    if report["non_match"]:
        out.append("")
        out.append("non-MATCH (review each; EXISTING_EXTRA/CONFLICT = resolver bug, RESOLVER_EXTRA = promotion candidate):")
        for d in report["non_match"]:
            out.append(
                f"  {d.get('ts')}  {str(d.get('classification')):<15} {d.get('file')}  "
                f"existing={d.get('existing')} resolver={d.get('resolver_mandatory')}  {d.get('receipt')}"
            )
    if report["collisions"]:
        out.append("")
        out.append("collisions:")
        for d in report["collisions"]:
            out.append(f"  {d.get('ts')}  {d.get('file')}  {d.get('collisions')}")
    if report["errors"]:
        out.append("")
        out.append("errors (harness faults, never gate decisions):")
        for d in report["errors"]:
            out.append(f"  {d.get('ts')}  {d.get('file')}  {d.get('error')}")
    return "\n".join(out) + "\n"
