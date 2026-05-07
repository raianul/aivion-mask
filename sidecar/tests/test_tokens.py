from aivion_mask_sidecar.tokens import make_token, replace_tokens

def test_make_token_format():
    assert make_token(1) == "__P1__"
    assert make_token(42) == "__P42__"

def test_replace_single_token():
    mappings = {"__P1__": "secret123"}
    assert replace_tokens("value is __P1__ done", mappings) == "value is secret123 done"

def test_replace_multiple_tokens():
    mappings = {"__P1__": "alice", "__P2__": "bob"}
    assert replace_tokens("__P1__ and __P2__", mappings) == "alice and bob"

def test_replace_unknown_token_unchanged():
    assert replace_tokens("hello __P99__ world", {}) == "hello __P99__ world"

def test_replace_no_tokens():
    assert replace_tokens("no tokens here", {"__P1__": "x"}) == "no tokens here"

def test_replace_same_token_twice():
    mappings = {"__P1__": "secret"}
    assert replace_tokens("__P1__ and __P1__", mappings) == "secret and secret"
