from aivion_mask_sidecar.stream import split_at_safe_point, LookaheadBuffer

# --- split_at_safe_point ---


def test_no_underscores():
    assert split_at_safe_point("hello world") == ("hello world", "")


def test_complete_token_at_end():
    assert split_at_safe_point("value __P1__") == ("value __P1__", "")


def test_partial_double_underscore():
    safe, hold = split_at_safe_point("value __")
    assert safe == "value "
    assert hold == "__"


def test_partial_with_P():
    safe, hold = split_at_safe_point("value __P")
    assert safe == "value "
    assert hold == "__P"


def test_partial_with_number():
    safe, hold = split_at_safe_point("value __P42")
    assert safe == "value "
    assert hold == "__P42"


def test_partial_closing_underscore():
    safe, hold = split_at_safe_point("value __P1_")
    assert safe == "value "
    assert hold == "__P1_"


def test_complete_then_partial():
    safe, hold = split_at_safe_point("__P1__ and __P")
    assert safe == "__P1__ and "
    assert hold == "__P"


def test_text_with_underscores_not_token():
    # single underscores in variable names should not be held back
    safe, hold = split_at_safe_point("variable_name = val")
    assert hold == ""  # nothing held back — no __ prefix


# --- LookaheadBuffer ---


def test_passthrough_no_tokens():
    buf = LookaheadBuffer({"__P1__": "secret"})
    assert buf.push("hello world") == "hello world"
    assert buf.flush() == ""


def test_replaces_complete_token():
    buf = LookaheadBuffer({"__P1__": "secret"})
    assert buf.push("value is __P1__ done") == "value is secret done"


def test_handles_split_token():
    buf = LookaheadBuffer({"__P1__": "secret"})
    out1 = buf.push("value is __P")
    out2 = buf.push("1__ done")
    assert out1 == "value is "  # held back partial
    assert out2 == "secret done"  # flushed once complete


def test_flush_releases_remainder():
    buf = LookaheadBuffer({"__P1__": "secret"})
    buf.push("value __P1")  # partial held back
    remainder = buf.flush()
    # At flush time the buffer holds "__P1" which is not a complete token
    # replace_tokens won't match it, so it passes through as-is
    assert remainder == "__P1"


def test_multiple_tokens_in_sequence():
    buf = LookaheadBuffer({"__P1__": "alice", "__P2__": "bob"})
    result = buf.push("__P1__ met __P2__")
    assert result == "alice met bob"


def test_flush_empty_after_complete_push():
    buf = LookaheadBuffer({"__P1__": "secret"})
    buf.push("value is __P1__ done")
    assert buf.flush() == ""
