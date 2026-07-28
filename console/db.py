"""SQLite persistence layer for the Agent Console.

Uses the stdlib ``sqlite3`` module (no ORM) to keep dependencies minimal.
The schema is created on first import and is idempotent.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

# DB lives next to this file unless overridden (e.g. a mounted volume in prod).
DB_PATH = os.environ.get(
    "CONSOLE_DB_PATH", str(Path(__file__).resolve().parent / "console.db")
)


def get_conn() -> sqlite3.Connection:
    """Return a connection with row access by column name and FK enforcement."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    email        TEXT UNIQUE NOT NULL,
    name         TEXT NOT NULL,
    password     TEXT NOT NULL,          -- salted hash
    role         TEXT NOT NULL DEFAULT 'agent',  -- admin | supervisor | agent
    status       TEXT NOT NULL DEFAULT 'active', -- active | disabled
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tokens (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);

-- Voice agents used to run campaigns (the "Campaign Agents" in the UI).
CREATE TABLE IF NOT EXISTS campaign_agents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    prompt      TEXT NOT NULL DEFAULT '',
    voice       TEXT NOT NULL DEFAULT 'default',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaigns (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT NOT NULL,
    agent_id             INTEGER REFERENCES campaign_agents(id) ON DELETE SET NULL,
    cps                  INTEGER NOT NULL DEFAULT 1,
    max_concurrent       INTEGER NOT NULL DEFAULT 1,
    timezone             TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    caller_id_strategy   TEXT NOT NULL DEFAULT 'fixed',   -- fixed | round_robin
    caller_id            TEXT NOT NULL DEFAULT '',
    window_enabled       INTEGER NOT NULL DEFAULT 0,
    window_start         TEXT NOT NULL DEFAULT '09:00',
    window_end           TEXT NOT NULL DEFAULT '18:00',
    retry_attempts       INTEGER NOT NULL DEFAULT 0,
    webhook_url          TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'draft',   -- draft|running|paused|completed
    created_by           INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    to_number   TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    vars        TEXT NOT NULL DEFAULT '{}',   -- JSON of extra CSV columns
    status      TEXT NOT NULL DEFAULT 'pending', -- pending|called|failed
    attempts    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

-- Call Detail Records: one row per call attempt (manual + campaign + inbound).
CREATE TABLE IF NOT EXISTS calls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    direction    TEXT NOT NULL DEFAULT 'outbound', -- outbound|inbound|manual
    from_number  TEXT NOT NULL DEFAULT '',
    to_number    TEXT NOT NULL DEFAULT '',
    agent_id     INTEGER,        -- app user (agent) who handled/placed it
    campaign_id  INTEGER,
    status       TEXT NOT NULL DEFAULT 'completed', -- completed|failed|no-answer|busy|voicemail
    disposition  TEXT NOT NULL DEFAULT '',
    duration_sec INTEGER NOT NULL DEFAULT 0,
    recording_url TEXT NOT NULL DEFAULT '',
    notes        TEXT NOT NULL DEFAULT '',
    started_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wa_channels (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name    TEXT NOT NULL,
    phone_number    TEXT NOT NULL,
    phone_number_id TEXT NOT NULL DEFAULT '',
    waba_id         TEXT NOT NULL DEFAULT '',
    provider        TEXT NOT NULL DEFAULT 'meta',  -- meta | twilio | 360dialog
    status          TEXT NOT NULL DEFAULT 'connected', -- connected|pending|disabled
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wa_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id  INTEGER NOT NULL REFERENCES wa_channels(id) ON DELETE CASCADE,
    direction   TEXT NOT NULL DEFAULT 'outbound', -- outbound|inbound
    peer        TEXT NOT NULL DEFAULT '',         -- the other party's number
    body        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'sent',     -- sent|delivered|read|received|failed
    created_at  TEXT NOT NULL
);
"""


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def query(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(sql, tuple(params)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Run an INSERT/UPDATE/DELETE; return lastrowid (for inserts)."""
    conn = get_conn()
    try:
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def executemany(sql: str, seq: Iterable[Iterable[Any]]) -> None:
    conn = get_conn()
    try:
        conn.executemany(sql, [tuple(p) for p in seq])
        conn.commit()
    finally:
        conn.close()
