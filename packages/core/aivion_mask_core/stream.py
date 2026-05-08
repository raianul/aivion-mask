from __future__ import annotations
import re

from .tokens import replace_tokens

# Matches a trailing suffix that could be the start of an incomplete type-specific token.
_PARTIAL_RE = re.compile(r'_[_A-Z\d]*_?$')
_TOKEN_RE = re.compile(r'__[A-Z]{2,6}\d+__')


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


def _star_prefix_len(token: str) -> int:
    """Minimum prefix length that includes the first '*' — the earliest meaningful partial match."""
    i = token.find("*")
    return i + 1 if i >= 0 else len(token)


class LookaheadBuffer:
    """Accumulates streaming text and emits it only when no partial token is at the edge."""

    def __init__(self, mappings: dict[str, str]) -> None:
        self._mappings = mappings
        self._buf = ""
        # Display-value tokens (non-__ABBREV{n}__ format) need prefix-based holdback.
        # Store (token, min_prefix_len) so we only hold back when the partial match
        # includes at least one '*' — avoids false holdbacks on single-char coincidences.
        self._display_tokens = [
            (t, _star_prefix_len(t))
            for t in mappings
            if not _TOKEN_RE.fullmatch(t)
        ]

    def push(self, chunk: str) -> str:
        """Accept a new chunk; return content safe to emit now."""
        self._buf += chunk
        # First pass: hold back partial __ABBREV{n}__ tokens via regex
        safe, self._buf = split_at_safe_point(self._buf)
        # Second pass: hold back any suffix of `safe` that is a prefix of a display_value token,
        # but only when the partial match reaches the first '*' (meaningful partial).
        for token, min_len in self._display_tokens:
            for prefix_len in range(min(len(token) - 1, len(safe)), min_len - 1, -1):
                if safe.endswith(token[:prefix_len]):
                    self._buf = safe[-prefix_len:] + self._buf
                    safe = safe[:-prefix_len]
                    break
        return replace_tokens(safe, self._mappings)

    def flush(self) -> str:
        """End of stream — emit everything remaining."""
        result = replace_tokens(self._buf, self._mappings)
        self._buf = ""
        return result
