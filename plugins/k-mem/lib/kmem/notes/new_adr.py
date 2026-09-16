"""``kmem notes adr "Title"``: the next ADR file from the template, index refreshed."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from ..layout import DECISIONS_DIR

_NUM = re.compile(r"^ADR-(\d+)")


def next_number(root: Path) -> int:
    ddir = Path(root) / DECISIONS_DIR
    nums = [int(m.group(1)) for p in ddir.glob("ADR-*.md") if (m := _NUM.match(p.name))] if ddir.is_dir() else []
    return (max(nums) + 1) if nums else 1


def slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:60] or "decision"


def create(root: Path, title: str, template_text: str, today: dt.date | None = None) -> Path:
    root = Path(root)
    n = next_number(root)
    ddir = root / DECISIONS_DIR
    ddir.mkdir(parents=True, exist_ok=True)
    path = ddir / f"ADR-{n:03d}-{slug(title)}.md"
    today = today or dt.date.today()
    text = template_text.replace("{{NUMBER}}", f"{n:03d}").replace("{{TITLE}}", title.strip()).replace("{{DATE}}", today.isoformat())
    path.write_text(text, encoding="utf-8")
    return path
