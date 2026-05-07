from __future__ import annotations
import re

_TOKEN_RE = re.compile(r'__P\d+__')

def make_token(index: int) -> str:
    return f"__P{index}__"

def replace_tokens(text: str, mappings: dict[str, str]) -> str:
    return _TOKEN_RE.sub(lambda m: mappings.get(m.group(0), m.group(0)), text)
