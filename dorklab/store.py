"""Cronologia e dork salvati, su SQLite."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from .paths import data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS saved (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    query      TEXT NOT NULL,
    tokens     TEXT,
    note       TEXT DEFAULT '',
    favorite   INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    query      TEXT NOT NULL,
    provider   TEXT NOT NULL,
    hits       INTEGER DEFAULT 0,
    context    TEXT DEFAULT 'ricerca',
    error      TEXT DEFAULT '',
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
"""


@dataclass
class SavedDork:
    id: int
    name: str
    query: str
    tokens: dict
    note: str
    favorite: bool
    created_at: float


@dataclass
class RunRecord:
    id: int
    query: str
    provider: str
    hits: int
    context: str
    error: str
    created_at: float


class Store:
    """Accesso al database locale della cronologia."""

    def __init__(self, path: str | None = None) -> None:
        if path is None:
            data_dir().mkdir(parents=True, exist_ok=True)
            path = str(data_dir() / "dorklab.db")
        self.path = path
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------ dork salvati
    def save_dork(self, name: str, query: str, tokens: dict | None = None,
                  note: str = "", favorite: bool = False) -> int:
        cursor = self._conn.execute(
            "INSERT INTO saved (name, query, tokens, note, favorite, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (name, query, json.dumps(tokens or {}), note, int(favorite), time.time()),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def saved_dorks(self) -> list[SavedDork]:
        rows = self._conn.execute(
            "SELECT * FROM saved ORDER BY favorite DESC, created_at DESC"
        ).fetchall()
        return [self._to_saved(row) for row in rows]

    def delete_saved(self, saved_id: int) -> None:
        self._conn.execute("DELETE FROM saved WHERE id = ?", (saved_id,))
        self._conn.commit()

    def toggle_favorite(self, saved_id: int) -> None:
        self._conn.execute(
            "UPDATE saved SET favorite = 1 - favorite WHERE id = ?", (saved_id,))
        self._conn.commit()

    @staticmethod
    def _to_saved(row: sqlite3.Row) -> SavedDork:
        try:
            tokens = json.loads(row["tokens"] or "{}")
        except json.JSONDecodeError:
            tokens = {}
        return SavedDork(row["id"], row["name"], row["query"], tokens,
                         row["note"] or "", bool(row["favorite"]), row["created_at"])

    # ------------------------------------------------------------- esecuzioni
    def log_run(self, query: str, provider: str, hits: int = 0,
                context: str = "ricerca", error: str = "") -> int:
        cursor = self._conn.execute(
            "INSERT INTO runs (query, provider, hits, context, error, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (query, provider, hits, context, error, time.time()),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def runs(self, limit: int = 300) -> list[RunRecord]:
        rows = self._conn.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [RunRecord(r["id"], r["query"], r["provider"], r["hits"],
                          r["context"], r["error"] or "", r["created_at"]) for r in rows]

    def clear_runs(self) -> None:
        self._conn.execute("DELETE FROM runs")
        self._conn.commit()

    def stats(self) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(hits), 0) AS hits FROM runs"
        ).fetchone()
        saved = self._conn.execute("SELECT COUNT(*) AS n FROM saved").fetchone()
        return {"esecuzioni": row["n"], "risultati": row["hits"], "salvati": saved["n"]}
