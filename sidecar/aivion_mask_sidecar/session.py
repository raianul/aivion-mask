from __future__ import annotations
import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT NOT NULL,
    token        TEXT NOT NULL,
    original     TEXT NOT NULL,
    token_index  INTEGER NOT NULL,
    created_at   INTEGER NOT NULL,
    expires_at   INTEGER NOT NULL,
    PRIMARY KEY (session_id, token)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_session_original
    ON sessions(session_id, original);
CREATE INDEX IF NOT EXISTS idx_session_expiry
    ON sessions(expires_at);
"""

def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    if db_path is None:
        from .config import AIVION_DIR
        db_path = AIVION_DIR / "sessions.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)  # single asyncio thread shares this conn
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn

def get_token(conn: sqlite3.Connection, session_id: str, original: str) -> str | None:
    row = conn.execute(
        "SELECT token FROM sessions WHERE session_id=? AND original=? AND expires_at>?",
        (session_id, original, int(time.time())),
    ).fetchone()
    return row[0] if row else None

def next_index(conn: sqlite3.Connection, session_id: str) -> int:
    row = conn.execute(
        "SELECT MAX(token_index) FROM sessions WHERE session_id=?",
        (session_id,),
    ).fetchone()
    return (row[0] or 0) + 1

def save_token(
    conn: sqlite3.Connection,
    session_id: str,
    token: str,
    original: str,
    token_index: int,
    ttl_hours: int,
) -> None:
    now = int(time.time())
    conn.execute(
        "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?)",
        (session_id, token, original, token_index, now, now + ttl_hours * 3600),
    )
    conn.commit()

def get_all_mappings(conn: sqlite3.Connection, session_id: str) -> dict[str, str]:
    rows = conn.execute(
        "SELECT token, original FROM sessions WHERE session_id=? AND expires_at>?",
        (session_id, int(time.time())),
    ).fetchall()
    return {row[0]: row[1] for row in rows}

def delete_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
    conn.commit()

def cleanup_expired(conn: sqlite3.Connection) -> int:
    cursor = conn.execute("DELETE FROM sessions WHERE expires_at<?", (int(time.time()),))
    conn.commit()
    return cursor.rowcount
