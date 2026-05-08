import pytest
from aivion_mask_core.masker import detect, mask_message, display_value, Entity
from aivion_mask_core.session import init_db

# --- display_value() ---

def test_display_value_always_redact_password():
    assert display_value("mysecret", "URL_PASS") == "***"

def test_display_value_always_redact_aws_secret():
    assert display_value("A" * 40, "AWS_SECRET_KEY") == "***"

def test_display_value_very_short():
    assert display_value("ab", "GITHUB_TOKEN") == "***"
    assert display_value("abcd", "GITHUB_TOKEN") == "***"

def test_display_value_5_to_8():
    assert display_value("Ahmed", "CUSTOM") == "A***d"
    assert display_value("abcdefgh", "CUSTOM") == "a***h"

def test_display_value_9_to_16():
    assert display_value("supersecret", "CUSTOM") == "su***et"
    assert display_value("a" * 16, "CUSTOM") == "aa***aa"

def test_display_value_17_to_32():
    val = "prod-internal-key"   # 17 chars
    assert display_value(val, "CUSTOM") == val[:4] + "***" + val[-4:]

def test_display_value_33_plus():
    val = "ghp_" + "A" * 36    # 40 chars
    result = display_value(val, "GITHUB_TOKEN")
    assert result == val[:6] + "***" + val[-4:]

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
    # 20-char AWS key → 17-32 tier: first 4 + *** + last 4
    assert "AKIA***AAAA" in result

async def test_mask_message_database_url_structural(conn):
    result = await mask_message("postgresql://user:pass@localhost:5432/mydb", conn, "s1", 8)
    # scheme and port preserved; credentials replaced with display values
    assert result.startswith("postgresql://")
    assert ":5432/" in result
    assert "pass" not in result  # password always → ***
    assert "***" in result
    # components are display_value masked inline (not stored as __ABBREV{n}__)
    assert "__USER" not in result
    assert "__PASS" not in result
    assert "__HOST" not in result
    assert "__DB" not in result

async def test_mask_message_type_specific_abbrev(conn):
    result = await mask_message("token: ghp_" + "A" * 36, conn, "s1", 8)
    # 40-char GH token → 33+ tier: first 6 + *** + last 4
    assert "ghp_AA***AAAA" in result

async def test_mask_message_same_value_same_token(conn):
    r1 = await mask_message("AKIA" + "A" * 16, conn, "s1", 8)
    r2 = await mask_message("AKIA" + "A" * 16, conn, "s1", 8)
    assert r1 == r2  # same value → same display_value → idempotent

async def test_mask_message_pre_redaction_does_not_match_substring(conn):
    # First turn: register a custom-pattern-style short original via direct save
    from aivion_mask_core.session import save_token
    await save_token(conn, "s1", "FOO***BAR", "FOOBAR", 0, 8)
    # Second turn: text contains "FOOBAR" as a substring of "FOOBARBAZ".
    # Word-boundary pre-redaction must NOT corrupt the larger token.
    result = await mask_message("the FOOBARBAZ value", conn, "s1", 8)
    assert "FOOBARBAZ" in result
    # But standalone FOOBAR should be replaced.
    result2 = await mask_message("just FOOBAR alone", conn, "s1", 8)
    assert "FOO***BAR" in result2


async def test_mask_message_pre_redacts_known_entities(conn):
    await mask_message("key=AKIA" + "A" * 16, conn, "s1", 8)
    result = await mask_message("the key is AKIA" + "A" * 16 + " again", conn, "s1", 8)
    assert "AKIA" + "A" * 16 not in result
    assert "AKIA***AAAA" in result

async def test_mask_message_no_entities_unchanged(conn):
    assert await mask_message("hello world", conn, "s1", 8) == "hello world"

async def test_mask_message_different_values_get_different_display_tokens(conn):
    t1 = "ghp_" + "A" * 36
    t2 = "ghp_" + "B" * 36
    r1 = await mask_message(t1, conn, "s1", 8)
    r2 = await mask_message(t2, conn, "s1", 8)
    assert "ghp_AA***AAAA" in r1
    assert "ghp_BB***BBBB" in r2
    assert r1 != r2

async def test_mask_message_different_types_independent_counters(conn):
    aws_result = await mask_message("AKIA" + "A" * 16, conn, "s1", 8)
    db_result = await mask_message("postgresql://user:pass@localhost/mydb", conn, "s1", 8)
    assert "AKIA***AAAA" in aws_result
    # structural masking: scheme preserved, components display_value masked inline
    assert db_result.startswith("postgresql://")
    assert "pass" not in db_result
    assert "***" in db_result
