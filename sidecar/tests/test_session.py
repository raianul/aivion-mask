import time
import pytest
from aivion_mask_sidecar.session import (
    init_db, get_token, next_index, save_token,
    get_all_mappings, delete_session, cleanup_expired,
)

@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "test.db")
    yield c
    c.close()

def test_init_creates_schema(conn):
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    assert ("sessions",) in tables

def test_save_and_get_token(conn):
    save_token(conn, "s1", "__P1__", "secret", 1, ttl_hours=8)
    assert get_token(conn, "s1", "secret") == "__P1__"

def test_get_token_unknown_returns_none(conn):
    assert get_token(conn, "s1", "unknown") is None

def test_get_token_different_session_returns_none(conn):
    save_token(conn, "s1", "__P1__", "secret", 1, ttl_hours=8)
    assert get_token(conn, "s2", "secret") is None

def test_next_index_starts_at_one(conn):
    assert next_index(conn, "s1") == 1

def test_next_index_increments(conn):
    save_token(conn, "s1", "__P1__", "val1", 1, ttl_hours=8)
    save_token(conn, "s1", "__P2__", "val2", 2, ttl_hours=8)
    assert next_index(conn, "s1") == 3

def test_get_all_mappings(conn):
    save_token(conn, "s1", "__P1__", "val1", 1, ttl_hours=8)
    save_token(conn, "s1", "__P2__", "val2", 2, ttl_hours=8)
    mappings = get_all_mappings(conn, "s1")
    assert mappings == {"__P1__": "val1", "__P2__": "val2"}

def test_delete_session(conn):
    save_token(conn, "s1", "__P1__", "val1", 1, ttl_hours=8)
    delete_session(conn, "s1")
    assert get_token(conn, "s1", "val1") is None

def test_cleanup_expired(conn):
    now = int(time.time())
    conn.execute(
        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
        ("s1", "__P1__", "val1", 1, now - 10, now - 1),
    )
    conn.commit()
    count = cleanup_expired(conn)
    assert count == 1
    assert get_token(conn, "s1", "val1") is None

def test_expired_token_not_returned(conn):
    now = int(time.time())
    conn.execute(
        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
        ("s1", "__P1__", "val1", 1, now - 10, now - 1),
    )
    conn.commit()
    assert get_token(conn, "s1", "val1") is None
