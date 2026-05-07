from aivion_mask_sidecar.stream import split_at_safe_point, LookaheadBuffer

# --- split_at_safe_point ---


def test_no_underscores():
    assert split_at_safe_point("hello world") == ("hello world", "")


def test_complete_token_at_end():
    assert split_at_safe_point("value __DB1__") == ("value __DB1__", "")


def test_partial_double_underscore():
    safe, hold = split_at_safe_point("value __")
    assert safe == "value "
    assert hold == "__"


def test_partial_with_letters():
    safe, hold = split_at_safe_point("value __DB")
    assert safe == "value "
    assert hold == "__DB"


def test_partial_with_number():
    safe, hold = split_at_safe_point("value __DB42")
    assert safe == "value "
    assert hold == "__DB42"


def test_partial_closing_underscore():
    safe, hold = split_at_safe_point("value __DB1_")
    assert safe == "value "
    assert hold == "__DB1_"


def test_complete_then_partial():
    safe, hold = split_at_safe_point("__DB1__ and __GH")
    assert safe == "__DB1__ and "
    assert hold == "__GH"


def test_text_with_underscores_not_token():
    # single underscores in variable names should not be held back
    safe, hold = split_at_safe_point("variable_name = val")
    assert hold == ""  # nothing held back — no __ prefix


# --- LookaheadBuffer ---


def test_passthrough_no_tokens():
    buf = LookaheadBuffer({"__DB1__": "secret"})
    assert buf.push("hello world") == "hello world"
    assert buf.flush() == ""


def test_replaces_complete_token():
    buf = LookaheadBuffer({"__DB1__": "postgresql://user:pass@host/db"})
    assert buf.push("value is __DB1__ done") == "value is postgresql://user:pass@host/db done"


def test_handles_split_token():
    buf = LookaheadBuffer({"__DB1__": "secret"})
    out1 = buf.push("value is __DB")
    out2 = buf.push("1__ done")
    assert out1 == "value is "  # held back partial
    assert out2 == "secret done"  # flushed once complete


def test_flush_releases_remainder():
    buf = LookaheadBuffer({"__DB1__": "secret"})
    buf.push("value __DB1")  # partial held back
    remainder = buf.flush()
    # At flush time the buffer holds "__DB1" which is not a complete token
    # replace_tokens won't match it, so it passes through as-is
    assert remainder == "__DB1"


def test_multiple_tokens_in_sequence():
    buf = LookaheadBuffer({"__GH1__": "ghp_token", "__DB1__": "postgresql://..."})
    result = buf.push("__GH1__ used __DB1__")
    assert result == "ghp_token used postgresql://..."


def test_flush_empty_after_complete_push():
    buf = LookaheadBuffer({"__DB1__": "secret"})
    buf.push("value is __DB1__ done")
    assert buf.flush() == ""
