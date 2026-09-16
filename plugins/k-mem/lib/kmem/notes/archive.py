"""Archive closed project-notes sections older than a cutoff into ``archive/``.

Re-runnable: partitions ``bugs.md`` / ``issues.md`` ``## <date> ...`` sections
by a date predicate, so out-of-order appended tails are handled correctly
and nothing is deleted. Archived files stay in git and stay searchable, just
out of the on-demand active file.

    kmem notes archive                      # cutoff = today - 90 days
    kmem notes archive --cutoff 2026-05-02  # explicit cutoff
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
DEFAULT_TARGETS: tuple[tuple[str, str], ...] = (("bugs.md", "Bugs"), ("issues.md", "Issues & Work Log"))
DEFAULT_DAYS = 90
_POINTER_PREFIX = "> **Archived history:**"


def default_cutoff(today: dt.date | None = None) -> dt.date:
    return (today or dt.date.today()) - dt.timedelta(days=DEFAULT_DAYS)


def split_sections(text: str) -> tuple[str, list[str]]:
    lines = text.split("\n")
    pre, i = [], 0
    while i < len(lines) and not lines[i].startswith("## "):
        pre.append(lines[i])
        i += 1
    sections: list[list[str]] = []
    cur: list[str] | None = None
    for line in lines[i:]:
        if line.startswith("## "):
            if cur is not None:
                sections.append(cur)
            cur = [line]
        elif cur is not None:
            cur.append(line)
    if cur is not None:
        sections.append(cur)
    return "\n".join(pre), ["\n".join(s) for s in sections]


def section_date(sec: str) -> dt.date | None:
    m = DATE_RE.search(sec.split("\n", 1)[0])
    if not m:
        return None
    try:
        return dt.date(*(int(x) for x in m.groups()))
    except ValueError:
        return None


def archive_file(notes_dir: Path, fname: str, label: str, cutoff: dt.date) -> str:
    """Archive one file's old sections; return a one-line report."""
    notes_dir = Path(notes_dir)
    path = notes_dir / fname
    if not path.is_file():
        return f"{fname}: not present, skipped"
    archive_dir = notes_dir / "archive"
    text = path.read_text(encoding="utf-8")
    preamble, sections = split_sections(text)
    keep, archived = [], []
    for s in sections:
        d = section_date(s)
        (archived if d is not None and d < cutoff else keep).append(s)
    if not archived:
        return f"{fname}: nothing older than {cutoff}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    arc_name = fname.replace(".md", "_archive.md")
    arc_path = archive_dir / arc_name
    dates = sorted(d for d in (section_date(s) for s in archived) if d)
    header = (
        f"# {label}: archive (pre-{cutoff})\n\n"
        f"Sections resolved or closed before {cutoff} ({DEFAULT_DAYS}-day cutoff), moved out of "
        f"the active `{fname}`. In git and searchable; just out of the on-demand active file. "
        f"Range: {dates[0]} to {dates[-1]}, {len(archived)} sections.\n"
    )
    body = "\n".join(archived).rstrip() + "\n"
    if arc_path.is_file():
        prefix = arc_path.read_text(encoding="utf-8").rstrip() + "\n\n"
    else:
        prefix = header + "\n"
    arc_path.write_text(prefix + body, encoding="utf-8")
    pointer = (
        f"{_POINTER_PREFIX} resolved or closed sections older than the {DEFAULT_DAYS}-day "
        f"cutoff live in [`archive/{arc_name}`](archive/{arc_name}). "
        f"Kept out of the active file so on-demand reads stay cheap."
    )
    pre_lines = [ln for ln in preamble.split("\n") if not ln.startswith(_POINTER_PREFIX)]
    new_pre = "\n".join(pre_lines).rstrip()
    new_text = new_pre + "\n\n" + pointer + "\n\n" + "\n".join(keep).rstrip() + "\n"
    path.write_text(new_text, encoding="utf-8")
    return f"{fname}: archived {len(archived)} sections ({dates[0]} to {dates[-1]}); kept {len(keep)}."


def archive_old_notes(
    notes_dir: Path, cutoff: dt.date | None = None, targets: tuple[tuple[str, str], ...] = DEFAULT_TARGETS
) -> list[str]:
    cutoff = cutoff or default_cutoff()
    return [f"cutoff = {cutoff}"] + [archive_file(notes_dir, fname, label, cutoff) for fname, label in targets]
