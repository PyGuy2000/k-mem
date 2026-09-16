"""Disposable SQLite index.

Authority flows one way: authored files -> compiler -> this store. Deleting
the file and rebuilding must yield the same packets, which the tests assert.
Nothing writes here except the compiler.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .models import ContextRecord, GovernedPath, Relationship

SCHEMA = """
CREATE TABLE IF NOT EXISTS records(
    record_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
    title TEXT NOT NULL,
    repo TEXT,
    path TEXT,
    status TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    provenance_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS relationships(
    source_id TEXT NOT NULL,
    relationship TEXT NOT NULL,
    target_id TEXT NOT NULL,
    provenance_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(source_id, relationship, target_id)
);
CREATE INDEX IF NOT EXISTS ix_rel_target ON relationships(target_id);
CREATE TABLE IF NOT EXISTS governed_paths(
    path_pattern TEXT NOT NULL,
    record_id TEXT NOT NULL,
    repo TEXT NOT NULL,
    provenance_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(path_pattern, record_id)
);
CREATE TABLE IF NOT EXISTS meta(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _row_to_record(row: sqlite3.Row) -> ContextRecord:
    return ContextRecord(
        record_id=row["record_id"],
        record_type=row["record_type"],
        title=row["title"],
        repo=row["repo"],
        path=row["path"],
        status=row["status"],
        metadata=json.loads(row["metadata_json"] or "{}"),
        provenance=json.loads(row["provenance_json"] or "{}"),
    )


class SQLiteStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._pattern_cache: dict[str, re.Pattern[str]] = {}

    def close(self) -> None:
        self.conn.close()

    # --- write (compiler only) ------------------------------------------------

    def replace_all(
        self,
        records: Iterable[ContextRecord],
        relationships: Iterable[Relationship],
        governed: Iterable[GovernedPath],
        meta: dict[str, str],
    ) -> None:
        cur = self.conn.cursor()
        cur.execute("BEGIN")
        cur.execute("DELETE FROM relationships")
        cur.execute("DELETE FROM governed_paths")
        cur.execute("DELETE FROM records")
        cur.execute("DELETE FROM meta")
        cur.executemany(
            "INSERT OR REPLACE INTO records VALUES(?,?,?,?,?,?,?,?)",
            [
                (
                    r.record_id, r.record_type, r.title, r.repo, r.path, r.status,
                    json.dumps(r.metadata, sort_keys=True), json.dumps(r.provenance, sort_keys=True),
                )
                for r in records
            ],
        )
        cur.executemany(
            "INSERT OR REPLACE INTO relationships VALUES(?,?,?,?)",
            [(e.source_id, e.relationship, e.target_id, json.dumps(e.provenance, sort_keys=True)) for e in relationships],
        )
        cur.executemany(
            "INSERT OR REPLACE INTO governed_paths VALUES(?,?,?,?)",
            [(g.path_pattern, g.record_id, g.repo, json.dumps(g.provenance, sort_keys=True)) for g in governed],
        )
        cur.executemany("INSERT OR REPLACE INTO meta VALUES(?,?)", list(meta.items()))
        self.conn.commit()
        self._pattern_cache.clear()

    # --- read -------------------------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def get_record(self, record_id: str) -> ContextRecord | None:
        row = self.conn.execute("SELECT * FROM records WHERE record_id=?", (record_id,)).fetchone()
        return _row_to_record(row) if row else None

    def all_records(self, record_type: str | None = None) -> list[ContextRecord]:
        if record_type:
            rows = self.conn.execute("SELECT * FROM records WHERE record_type=? ORDER BY record_id", (record_type,))
        else:
            rows = self.conn.execute("SELECT * FROM records ORDER BY record_id")
        return [_row_to_record(r) for r in rows]

    def all_relationships(self) -> list[Relationship]:
        rows = self.conn.execute("SELECT * FROM relationships ORDER BY source_id, relationship, target_id")
        return [
            Relationship(r["source_id"], r["relationship"], r["target_id"], json.loads(r["provenance_json"] or "{}"))
            for r in rows
        ]

    def all_governed(self) -> list[GovernedPath]:
        rows = self.conn.execute("SELECT * FROM governed_paths ORDER BY path_pattern, record_id")
        return [GovernedPath(r["path_pattern"], r["record_id"], r["repo"], json.loads(r["provenance_json"] or "{}")) for r in rows]

    def governed_for_target(
        self, target: str, repo: str | None, matcher: Callable[[str], re.Pattern[str]]
    ) -> list[tuple[ContextRecord, dict[str, Any]]]:
        """Records whose pattern matches ``target``; provenance of the governing row alongside."""
        out: list[tuple[ContextRecord, dict[str, Any]]] = []
        for g in self.all_governed():
            if repo and g.repo != repo:
                continue
            rx = self._pattern_cache.get(g.path_pattern)
            if rx is None:
                rx = matcher(g.path_pattern)
                self._pattern_cache[g.path_pattern] = rx
            if rx.match(target):
                rec = self.get_record(g.record_id)
                if rec:
                    out.append((rec, g.provenance))
        return out

    def related_from(self, source_id: str) -> list[tuple[str, ContextRecord, dict[str, Any]]]:
        rows = self.conn.execute(
            "SELECT relationship, target_id, provenance_json FROM relationships WHERE source_id=? ORDER BY relationship, target_id",
            (source_id,),
        ).fetchall()
        out = []
        for row in rows:
            rec = self.get_record(row["target_id"])
            if rec:
                out.append((row["relationship"], rec, json.loads(row["provenance_json"] or "{}")))
        return out

    def related_to(self, target_id: str) -> list[tuple[str, ContextRecord, dict[str, Any]]]:
        rows = self.conn.execute(
            "SELECT relationship, source_id, provenance_json FROM relationships WHERE target_id=? ORDER BY relationship, source_id",
            (target_id,),
        ).fetchall()
        out = []
        for row in rows:
            rec = self.get_record(row["source_id"])
            if rec:
                out.append((row["relationship"], rec, json.loads(row["provenance_json"] or "{}")))
        return out

    def unresolved_edges(self) -> list[Relationship]:
        rows = self.conn.execute(
            """SELECT r.* FROM relationships r
               LEFT JOIN records t ON t.record_id = r.target_id
               WHERE t.record_id IS NULL ORDER BY r.source_id, r.target_id"""
        ).fetchall()
        return [
            Relationship(r["source_id"], r["relationship"], r["target_id"], json.loads(r["provenance_json"] or "{}"))
            for r in rows
        ]
