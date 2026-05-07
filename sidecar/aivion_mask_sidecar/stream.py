from __future__ import annotations
import re

from .tokens import replace_tokens

# Matches a trailing suffix that could be the start of an incomplete __Pn__ token.
_PARTIAL_RE = re.compile(r'_[_P\d]*$')
_TOKEN_RE = re.compile(r'__P\d+__')


def split_at_safe_point(text: str) -> tuple[str, str]:
    """Return (safe_to_flush, hold_back).

    Holds back any trailing suffix that looks like an incomplete __Pn__ token.
    """
    m = _PARTIAL_RE.search(text)
    if not m:
        return text, ""
    partial = m.group(0)
    if _TOKEN_RE.fullmatch(partial):
        return text, ""
    return text[: m.start()], partial


class LookaheadBuffer:
    """Accumulates streaming text and emits it only when no partial token is at the edge."""

    def __init__(self, mappings: dict[str, str]) -> None:
        self._mappings = mappings
        self._buf = ""

    def push(self, chunk: str) -> str:
        """Accept a new chunk; return content safe to emit now."""
        self._buf += chunk
        safe, self._buf = split_at_safe_point(self._buf)
        return replace_tokens(safe, self._mappings)

    def flush(self) -> str:
        """End of stream — emit everything remaining."""
        result = replace_tokens(self._buf, self._mappings)
        self._buf = ""
        return result
