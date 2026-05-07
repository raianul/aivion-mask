import time
import pytest
from aivion_mask_sidecar.session import (
    init_db, get_token, next_index, save_token,
    get_all_mappings, delete_session, cleanup_expired,
)

@pytest.fixture
async def conn(tmp_path):
    c = await init_db(tmp_path / "test.db")
    yield c
    await c.close()

async def test_init_creates_schema(conn):
    async with conn.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
        tables = await cursor.fetchall()
    assert ("sessions",) in tables

async def test_save_and_get_token(conn):
    await save_token(conn, "s1", "__DB1__", "postgresql://user:pass@host/db", 1, ttl_hours=8)
    assert await get_token(conn, "s1", "postgresql://user:pass@host/db") == "__DB1__"

async def test_get_token_unknown_returns_none(conn):
    assert await get_token(conn, "s1", "unknown") is None

async def test_get_token_different_session_returns_none(conn):
    await save_token(conn, "s1", "__DB1__", "secret", 1, ttl_hours=8)
    assert await get_token(conn, "s2", "secret") is None

async def test_next_index_starts_at_one(conn):
    assert await next_index(conn, "s1", "DB") == 1

async def test_next_index_increments_per_abbrev(conn):
    await save_token(conn, "s1", "__DB1__", "val1", 1, ttl_hours=8)
    await save_token(conn, "s1", "__DB2__", "val2", 2, ttl_hours=8)
    assert await next_index(conn, "s1", "DB") == 3

async def test_next_index_independent_per_abbrev(conn):
    await save_token(conn, "s1", "__GH1__", "ghp_token1", 1, ttl_hours=8)
    await save_token(conn, "s1", "__GH2__", "ghp_token2", 2, ttl_hours=8)
    assert await next_index(conn, "s1", "DB") == 1
    assert await next_index(conn, "s1", "GH") == 3

async def test_get_all_mappings(conn):
    await save_token(conn, "s1", "__GH1__", "ghp_token1", 1, ttl_hours=8)
    await save_token(conn, "s1", "__DB1__", "postgresql://user:pass@host/db", 2, ttl_hours=8)
    mappings = await get_all_mappings(conn, "s1")
    assert mappings == {
        "__GH1__": "ghp_token1",
        "__DB1__": "postgresql://user:pass@host/db",
    }

async def test_delete_session(conn):
    await save_token(conn, "s1", "__DB1__", "val1", 1, ttl_hours=8)
    await delete_session(conn, "s1")
    assert await get_token(conn, "s1", "val1") is None

async def test_cleanup_expired(conn):
    now = int(time.time())
    await conn.execute(
        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
        ("s1", "__DB1__", "val1", 1, now - 10, now - 1),
    )
    await conn.commit()
    count = await cleanup_expired(conn)
    assert count == 1
    assert await get_token(conn, "s1", "val1") is None

async def test_expired_token_not_returned(conn):
    now = int(time.time())
    await conn.execute(
        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
        ("s1", "__DB1__", "val1", 1, now - 10, now - 1),
    )
    await conn.commit()
    assert await get_token(conn, "s1", "val1") is None
