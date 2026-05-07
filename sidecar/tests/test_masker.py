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
def conn(tmp_path):
    c = init_db(tmp_path / "t.db")
    yield c
    c.close()

def test_mask_message_assigns_token(conn):
    result = mask_message("key=AKIA" + "A" * 16 + " text", conn, "s1", 8)
    assert "AKIA" + "A" * 16 not in result
    assert "__P1__" in result

def test_mask_message_same_value_same_token(conn):
    r1 = mask_message("AKIA" + "A" * 16, conn, "s1", 8)
    r2 = mask_message("AKIA" + "A" * 16, conn, "s1", 8)
    assert r1 == r2  # same token assigned

def test_mask_message_pre_redacts_known_entities(conn):
    # First message — assigns __P1__
    mask_message("key=AKIA" + "A" * 16, conn, "s1", 8)
    # Second message mentions same value — should pre-redact without re-detecting
    result = mask_message("the key is AKIA" + "A" * 16 + " again", conn, "s1", 8)
    assert "AKIA" + "A" * 16 not in result
    assert "__P1__" in result

def test_mask_message_no_entities_unchanged(conn):
    assert mask_message("hello world", conn, "s1", 8) == "hello world"
