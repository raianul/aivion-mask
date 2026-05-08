# aivion-mask

Local-first PII masking layer for LLM applications. Masks sensitive data before it reaches any LLM; restores originals in the response.

## Repository Structure

| Path | Package | What it is | Status |
|---|---|---|---|
| `packages/core/` | `aivion-mask-core` | Shared masking engine — patterns, session store, tokens, streaming | active |
| `packages/claude/` | `aivion-mask-claude` | Anthropic Claude provider (`/v1/messages`, SSE, streaming) | active |
| `packages/openai/` | `aivion-mask-openai` | OpenAI provider scaffold | gitignored |
| `extension/browser/` | — | Chrome/Firefox extension for AI chat UIs | planned |

## Code Style

- **Python:** `ruff` — config in `pyproject.toml`

## Commands

```bash
# Core package
cd packages/core
pip install -e ".[dev]"
pytest -v

# Claude provider
cd packages/claude
pip install -e ".[dev]"
pytest -v
aivion-mask-claude          # start proxy on :47474
```

## Key Design Invariants

- **No LLM calls inside the masking layer.** Detection is pure regex — no ML, no spaCy, no Presidio.
- **Display-value tokens:** secrets are replaced with a partial-reveal string (e.g. `ghp_ABCD***1234`), not opaque `__P1__` tokens. The LLM sees enough context to be useful.
- **Session model:** same `session_id` across turns prevents "turn 3 leak". Pre-redact known entities before running regex on subsequent turns. Without `X-Aivion-Session` header, each request is a fresh session (Claude Code default).
- **Structural URL masking:** connection strings are masked component-by-component (user, password, host, db) so the LLM understands what it's working with.

## Gotchas

- **Test fixture credentials** trigger GitHub secret scanning push protection. Use split string concatenation in tests: `'xoxb-' + '123...'` not `'xoxb-123...'`.
- **packages/openai/** is gitignored — OpenAI provider is not released yet.
- **Each Claude Code prompt = new session** — the session store fills with single-use entries. They expire automatically (default 8h TTL, swept every 10 min).

## Known Issues

- **Display-value token collision (theoretical):** `display_value()` uses fixed prefix/suffix slices. Two distinct secrets that share both first-N and last-M chars produce the same masked token. Combined with `INSERT OR REPLACE` on PK `(session_id, token)`, the second secret silently clobbers the first → response unmasking returns the wrong original. Risk is astronomically low for long tokens (10 chars of base62 entropy for ≥32-char inputs) but real for short custom-pattern matches. Fix deferred — revisit if a collision is observed in practice.
