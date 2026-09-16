"""The decisions index generator and the notes archiver."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from kmem.notes import archive_old_notes, render_index, write_index
from kmem.notes.decisions_index import END, START


def _notes(tmp_path: Path) -> Path:
    notes = tmp_path / "docs/project_notes"
    (notes / "decisions").mkdir(parents=True)
    (notes / "decisions/ADR-002-two.md").write_text(
        "## ADR-002: Two things\n**Status**: Accepted\n**Date**: 2026-02-02\n\n### ADR-002 addendum\nmore\n", encoding="utf-8"
    )
    (notes / "decisions/ADR-001-one.md").write_text("## ADR-001: One thing\n**Status**: Proposed\n", encoding="utf-8")
    (notes / "decisions/ADR-010-ten.md").write_text("## ADR-010: Ten\n", encoding="utf-8")
    return notes


def test_render_index_rows_sorted_numerically_with_anchors(tmp_path):
    text, n_rows, n_files = render_index(_notes(tmp_path))
    assert (n_rows, n_files) == (4, 3)
    assert text.startswith("# Architectural Decision Records\n\n" + START)
    assert text.rstrip().endswith(END)
    rows = [ln for ln in text.splitlines() if ln.startswith("| [")]
    assert rows[0].startswith("| [ADR-001](decisions/ADR-001-one.md) | One thing | Proposed | - |")
    assert rows[1].startswith("| [ADR-002](decisions/ADR-002-two.md) | Two things | Accepted | 2026-02-02 |")
    assert rows[2].startswith("| [↳ ADR-002 addendum](decisions/ADR-002-two.md#adr-002-addendum) |")
    assert rows[3].startswith("| [ADR-010](decisions/ADR-010-ten.md) | Ten | - | - |")


def test_write_index_keeps_a_custom_preamble(tmp_path):
    notes = _notes(tmp_path)
    write_index(notes)
    index = notes / "decisions.md"
    index.write_text("# My decisions\n\nConventions here.\n\n" + index.read_text(encoding="utf-8").split(START, 1)[1].join([START, ""]), encoding="utf-8")
    write_index(notes)
    text = index.read_text(encoding="utf-8")
    assert text.startswith("# My decisions\n\nConventions here.\n\n" + START)
    assert text.count(START) == 1


def test_render_index_errors_without_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        render_index(tmp_path)
    (tmp_path / "decisions").mkdir()
    with pytest.raises(FileNotFoundError):
        render_index(tmp_path)


BUGS = """# Bugs

Intro line.

## 2026-01-05 old one RESOLVED
detail a

## 2026-09-01 recent one
detail b

## 2026-02-10 older two RESOLVED
detail c
"""


def test_archive_moves_old_sections_and_is_rerunnable(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "bugs.md").write_text(BUGS, encoding="utf-8")
    cutoff = dt.date(2026, 6, 1)
    lines = archive_old_notes(notes, cutoff)
    assert lines[0] == f"cutoff = {cutoff}"
    assert lines[1].startswith("bugs.md: archived 2 sections (2026-01-05 to 2026-02-10); kept 1.")
    assert lines[2] == "issues.md: not present, skipped"
    active = (notes / "bugs.md").read_text(encoding="utf-8")
    assert "recent one" in active and "old one" not in active
    assert "> **Archived history:**" in active and "archive/bugs_archive.md" in active
    archived = (notes / "archive/bugs_archive.md").read_text(encoding="utf-8")
    assert "old one" in archived and "older two" in archived and archived.startswith("# Bugs: archive (pre-2026-06-01)")
    again = archive_old_notes(notes, cutoff)
    assert again[1] == f"bugs.md: nothing older than {cutoff}"
    assert (notes / "bugs.md").read_text(encoding="utf-8").count("> **Archived history:**") == 1
