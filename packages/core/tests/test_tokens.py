from aivion_mask_core.tokens import entity_abbrev, make_token, replace_tokens


def test_entity_abbrev_known():
    assert entity_abbrev("DATABASE_URL") == "DB"
    assert entity_abbrev("GITHUB_TOKEN") == "GH"
    assert entity_abbrev("AWS_ACCESS_KEY_ID") == "AWS"
    assert entity_abbrev("OPENAI_API_KEY") == "OAI"
    assert entity_abbrev("ANTHROPIC_API_KEY") == "ANT"
    assert entity_abbrev("SLACK_BOT_TOKEN") == "SLK"
    assert entity_abbrev("STRIPE_SECRET_KEY") == "STR"
    assert entity_abbrev("PRIVATE_KEY") == "KEY"
    assert entity_abbrev("JWT_TOKEN") == "JWT"
    assert entity_abbrev("PRIVATE_IP") == "IP"


def test_entity_abbrev_unknown_falls_back_to_prefix():
    assert entity_abbrev("UNKNOWN_TYPE") == "UNK"
    assert entity_abbrev("FOO") == "FOO"


def test_make_token_format():
    assert make_token("DATABASE_URL", 1) == "__DB1__"
    assert make_token("GITHUB_TOKEN", 1) == "__GH1__"
    assert make_token("AWS_ACCESS_KEY_ID", 1) == "__AWS1__"
    assert make_token("DATABASE_URL", 42) == "__DB42__"


def test_make_token_shared_abbrev():
    # DATABASE_URL and DATABASE_URL_REDIS both map to DB
    assert make_token("DATABASE_URL", 1) == make_token("DATABASE_URL_REDIS", 1)


def test_replace_single_token():
    mappings = {"__DB1__": "postgresql://user:pass@host/db"}
    result = replace_tokens("value is __DB1__ done", mappings)
    assert result == "value is postgresql://user:pass@host/db done"


def test_replace_multiple_tokens():
    mappings = {"__GH1__": "ghp_abc123", "__DB1__": "postgresql://..."}
    assert replace_tokens("__GH1__ and __DB1__", mappings) == "ghp_abc123 and postgresql://..."


def test_replace_unknown_token_unchanged():
    assert replace_tokens("hello __DB99__ world", {}) == "hello __DB99__ world"


def test_replace_no_tokens():
    assert replace_tokens("no tokens here", {"__DB1__": "x"}) == "no tokens here"


def test_replace_same_token_twice():
    mappings = {"__AWS1__": "AKIAIOSFODNN7EXAMPLE"}
    assert replace_tokens("__AWS1__ and __AWS1__", mappings) == "AKIAIOSFODNN7EXAMPLE and AKIAIOSFODNN7EXAMPLE"
