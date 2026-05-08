from __future__ import annotations
import time
from pathlib import Path

import aiosqlite

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id   TEXT NOT NULL,
        token        TEXT NOT NULL,
        original     TEXT NOT NULL,
        token_index  INTEGER NOT NULL,
        created_at   INTEGER NOT NULL,
        expires_at   INTEGER NOT NULL,
        PRIMARY KEY (session_id, token)
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_session_original
        ON sessions(session_id, original)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_session_expiry
        ON sessions(expires_at)
    """,
]


async def init_db(db_path: Path | None = None) -> aiosqlite.Connection:
    if db_path is None:
        from .config import AIVION_DIR
        db_path = AIVION_DIR / "sessions.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not db_path.exists()
    conn = await aiosqlite.connect(str(db_path))
    if is_new:
        db_path.chmod(0o600)
    await conn.execute("PRAGMA journal_mode=WAL")
    for stmt in _SCHEMA:
        await conn.execute(stmt)
    await conn.commit()
    return conn


async def get_token(conn: aiosqlite.Connection, session_id: str, original: str) -> str | None:
    async with conn.execute(
        "SELECT token FROM sessions WHERE session_id=? AND original=? AND expires_at>?",
        (session_id, original, int(time.time())),
    ) as cursor:
        row = await cursor.fetchone()
    return row[0] if row else None


async def next_index(conn: aiosqlite.Connection, session_id: str, entity_abbrev: str) -> int:
    async with conn.execute(
        "SELECT token FROM sessions WHERE session_id=? AND expires_at>?",
        (session_id, int(time.time())),
    ) as cursor:
        rows = await cursor.fetchall()
    prefix = f"__{entity_abbrev}"
    max_idx = 0
    for (token,) in rows:
        if token.startswith(prefix) and token.endswith("__"):
            try:
                max_idx = max(max_idx, int(token[len(prefix):-2]))
            except ValueError:
                pass
    return max_idx + 1


async def save_token(
    conn: aiosqlite.Connection,
    session_id: str,
    token: str,
    original: str,
    token_index: int,
    ttl_hours: int,
) -> None:
    now = int(time.time())
    await conn.execute(
        "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?)",
        (session_id, token, original, token_index, now, now + ttl_hours * 3600),
    )
    await conn.commit()


async def get_all_mappings(conn: aiosqlite.Connection, session_id: str) -> dict[str, str]:
    async with conn.execute(
        "SELECT token, original FROM sessions WHERE session_id=? AND expires_at>?",
        (session_id, int(time.time())),
    ) as cursor:
        rows = await cursor.fetchall()
    return {row[0]: row[1] for row in rows}


async def delete_session(conn: aiosqlite.Connection, session_id: str) -> None:
    await conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
    await conn.commit()


async def cleanup_expired(conn: aiosqlite.Connection) -> int:
    cursor = await conn.execute(
        "DELETE FROM sessions WHERE expires_at<?", (int(time.time()),)
    )
    count = cursor.rowcount
    await conn.commit()
    return count
