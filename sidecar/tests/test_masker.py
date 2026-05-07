import pytest
from aivion_mask_sidecar.masker import detect, mask_message, Entity
from aivion_mask_sidecar.session import init_db

# --- detect() ---

def test_detects_aws_key():
    entities = detect("key=AKIA" + "A" * 16)
    assert any(e.entity_type == "AWS_ACCESS_KEY_ID" for e in entities)

def test_detects_github_pat():
    entities = detect("token: ghp_" + "A" * 36)
    assert any(e.entity_type == "GITHUB_TOKEN" for e in entities)

def test_detects_openai_key():
    entities = detect("sk-" + "a" * 48)
    assert any(e.entity_type == "OPENAI_API_KEY" for e in entities)

def test_detects_postgres_url():
    entities = detect("postgresql://user:password123@localhost:5432/mydb")
    assert any(e.entity_type == "DATABASE_URL" for e in entities)

def test_detects_private_ip():
    entities = detect("connect to 192.168.1.100")
    assert any(e.entity_type == "PRIVATE_IP" for e in entities)

def test_detects_jwt():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMTIzIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    entities = detect(jwt)
    assert any(e.entity_type == "JWT_TOKEN" for e in entities)

def test_no_false_positive_plain_text():
    entities = detect("The quick brown fox")
    assert entities == []

def test_no_false_positive_variable_name():
    entities = detect("my_variable_name = 42")
    assert entities == []

def test_deduplicates_overlapping_spans():
    # DATABASE_URL and URL_WITH_CREDENTIALS both match — only one returned
    entities = detect("postgresql://user:pass@host:5432/db")
    starts = [e.start for e in entities]
    assert len(starts) == len(set(starts))  # no duplicate start positions

# --- mask_message() ---

@pytest.fixture
async def conn(tmp_path):
    c = await init_db(tmp_path / "t.db")
    yield c
    await c.close()

async def test_mask_message_assigns_token(conn):
    result = await mask_message("key=AKIA" + "A" * 16 + " text", conn, "s1", 8)
    assert "AKIA" + "A" * 16 not in result
    assert "__AWS1__" in result

async def test_mask_message_database_url_token(conn):
    result = await mask_message("postgresql://user:pass@localhost:5432/mydb", conn, "s1", 8)
    assert "postgresql" not in result
    assert "__DB1__" in result

async def test_mask_message_type_specific_abbrev(conn):
    result = await mask_message("token: ghp_" + "A" * 36, conn, "s1", 8)
    assert "__GH1__" in result

async def test_mask_message_same_value_same_token(conn):
    r1 = await mask_message("AKIA" + "A" * 16, conn, "s1", 8)
    r2 = await mask_message("AKIA" + "A" * 16, conn, "s1", 8)
    assert r1 == r2

async def test_mask_message_pre_redacts_known_entities(conn):
    await mask_message("key=AKIA" + "A" * 16, conn, "s1", 8)
    result = await mask_message("the key is AKIA" + "A" * 16 + " again", conn, "s1", 8)
    assert "AKIA" + "A" * 16 not in result
    assert "__AWS1__" in result

async def test_mask_message_no_entities_unchanged(conn):
    assert await mask_message("hello world", conn, "s1", 8) == "hello world"

async def test_mask_message_per_type_counter(conn):
    t1 = "ghp_" + "A" * 36
    t2 = "ghp_" + "B" * 36
    r1 = await mask_message(t1, conn, "s1", 8)
    r2 = await mask_message(t2, conn, "s1", 8)
    assert "__GH1__" in r1
    assert "__GH2__" in r2

async def test_mask_message_different_types_independent_counters(conn):
    aws_result = await mask_message("AKIA" + "A" * 16, conn, "s1", 8)
    db_result = await mask_message("postgresql://user:pass@localhost/db", conn, "s1", 8)
    assert "__AWS1__" in aws_result
    assert "__DB1__" in db_result
