"""SQLite schema and small repository functions."""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_cache (
    key TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS game_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    source TEXT NOT NULL,
    is_mock INTEGER NOT NULL,
    match_id TEXT,
    game_time INTEGER,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recommendation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    snapshot_id INTEGER REFERENCES game_snapshots(id),
    item TEXT NOT NULL,
    priority TEXT NOT NULL,
    score REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS match_reports (
    match_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    payload TEXT NOT NULL
);
"""


def cache_get(conn: sqlite3.Connection, key: str, max_age: float) -> Any | None:
    row = conn.execute("SELECT payload, fetched_at FROM api_cache WHERE key = ?", (key,)).fetchone()
    if row is None or time.time() - row["fetched_at"] > max_age:
        return None
    return json.loads(row["payload"])


def cache_put(conn: sqlite3.Connection, key: str, payload: Any) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO api_cache (key, payload, fetched_at) VALUES (?, ?, ?)",
        (key, json.dumps(payload), time.time()),
    )
    conn.commit()


def save_snapshot(conn: sqlite3.Connection, state_json: str, *, source: str, is_mock: bool,
                  match_id: str | None, game_time: int | None) -> int:
    cur = conn.execute(
        "INSERT INTO game_snapshots (created_at, source, is_mock, match_id, game_time, payload)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (time.time(), source, int(is_mock), match_id, game_time, state_json),
    )
    conn.commit()
    return int(cur.lastrowid)


def log_recommendations(conn: sqlite3.Connection, snapshot_id: int, recs: list[tuple[str, str, float]]) -> None:
    conn.executemany(
        "INSERT INTO recommendation_log (created_at, snapshot_id, item, priority, score) VALUES (?, ?, ?, ?, ?)",
        [(time.time(), snapshot_id, item, prio, score) for item, prio, score in recs],
    )
    conn.commit()


def save_report(conn: sqlite3.Connection, match_id: str, report: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO match_reports (match_id, created_at, payload) VALUES (?, ?, ?)",
        (match_id, time.time(), json.dumps(report)),
    )
    conn.commit()


def list_reports(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT payload FROM match_reports ORDER BY created_at DESC").fetchall()
    return [json.loads(r["payload"]) for r in rows]
