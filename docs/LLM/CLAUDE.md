# Claude (Anthropic) — Provider Coverage Plan

First provider in the per-provider rollout. Goal: cover every place a developer interacts with Claude, except a small set of vendor-locked surfaces that are honestly out of reach.

> **Status:** plan only. Implementation is the v1.5 ship, follows the validation in `docs/superpowers/plans/staged-waddling-comet.md`.

---

## Goal

A user installs aivion-mask, points any Claude-using tool at the local sidecar, and every prompt is masked before it reaches `api.anthropic.com`. Every response has placeholders restored before the user sees them. The user's existing auth — OAuth (subscription) or API key — flows through unchanged.

No CA install. No system tray. No `sudo`. Plain HTTP on `localhost:47474`.

---

## Coverage targets

### In scope

| Surface | Status | How |
|---|---|---|
| **Claude Code CLI (subscription)** | Primary target | `ANTHROPIC_BASE_URL=http://localhost:47474` — OAuth token from Keychain passes through |
| **Claude Code CLI (API key)** | ✅ | Same, with `x-api-key` header instead of OAuth |
| **Anthropic Python SDK** | ✅ | `Anthropic(base_url="http://localhost:47474")` or env var |
| **Anthropic TypeScript SDK** | ✅ | `new Anthropic({ baseURL: 'http://localhost:47474' })` or env var |
| **Continue.dev with Anthropic provider** | ✅ | Set `apiBase: "http://localhost:47474"` in `~/.continue/config.json` |
| **aider with `--model claude-*`** | ✅ | aider uses litellm under the hood; `ANTHROPIC_API_BASE` env var is honored |
| **llm + `llm-anthropic` plugin** | ✅ | Plugin honors `ANTHROPIC_API_BASE` |
| **Claude.ai web UI** | ✅ in v1.6 | Browser extension — separate work, not in this plan |
| **OpenCode (Anthropic mode)** | ✅ | Honors `ANTHROPIC_BASE_URL` |

### Out of scope (named so we're honest)

| Surface | Why |
|---|---|
| **Claude Desktop app** | Pins certificates; no user-CA path |
| **Cursor's Claude routing** | Cursor proxies through `api.cursor.sh`, not Anthropic directly |
| **GitHub Copilot's Claude option** | Routes through Copilot backend with proprietary wire format |
| **Mobile apps (iOS / Android Claude)** | Universally pin |
| **Anthropic-hosted Claude in third-party platforms** (Bedrock, Vertex) | Different endpoints (`bedrock-runtime.amazonaws.com`, `*.googleapis.com`) — separate provider plans |

---

## Architecture (per request)

```
Tool (Claude Code, SDK, Continue, etc.)
  │
  │  POST http://localhost:47474/v1/messages
  │  Authorization: Bearer <oauth>     OR    x-api-key: <key>
  │  anthropic-version: 2023-06-01
  │  Content-Type: application/json
  │  { messages, system, tools, ... }
  ▼
sidecar /v1/messages handler
  │
  │ 1. extract incoming Authorization / x-api-key / anthropic-version / anthropic-beta
  │ 2. recursively walk request body, mask all string fields:
  │      - system (string OR array of {type:"text", text})
  │      - messages[].content (string OR blocks)
  │      - tool_result.content
  │      - tool definitions (description? — opt out, see Gotchas §3)
  │ 3. forward to https://api.anthropic.com/v1/messages with original auth + headers
  ▼
api.anthropic.com → Claude
  │
  │ stream of SSE events: message_start, content_block_start,
  │   content_block_delta (text_delta or input_json_delta),
  │   content_block_stop, message_delta, message_stop
  ▼
sidecar response handler
  │
  │ 4. for each text_delta: feed through LookaheadBuffer with session mappings → unmask
  │ 5. for each input_json_delta (tool_use args): assemble + unmask + re-emit
  │ 6. forward each event back to client preserving event/data line pairs
  ▼
Tool sees a fully unmasked response, never knew the proxy was there
```

The masking engine itself doesn't change. The work is **request/response shape walkers** and **streaming format parser** — Anthropic's SSE is structurally different from OpenAI's.

---

## Endpoint plumbing

### 1. New route: `POST /v1/messages`

Currently the sidecar has only `POST /v1/chat/completions`. Add `/v1/messages` alongside it. Two completion paths in `main.py`, each calling its provider-specific masker + forwarder.

Decision needed: **per-route upstream** or **per-config upstream**?

- **Per-config (current)**: `_config.llm.api_base` is a single value. Doesn't work when the user has both a Claude tool and an OpenAI tool pointed at the same proxy.
- **Per-route (recommended)**: `/v1/messages` → `https://api.anthropic.com`, `/v1/chat/completions` → `https://api.openai.com/v1`. Config still allows override per route for testing.

Pick per-route. Add a tiny route-to-upstream map:

```python
# config.py
DEFAULT_UPSTREAMS = {
    "/v1/messages":         "https://api.anthropic.com",
    "/v1/chat/completions": "https://api.openai.com/v1",
}
```

### 2. Auth header pass-through

Anthropic accepts **two** auth schemes:

| Header | Used by | Format |
|---|---|---|
| `Authorization: Bearer <token>` | Claude Code subscription mode (OAuth) | `sk-ant-oat01-...` |
| `x-api-key: <key>` | Direct API users, SDKs configured with API key | `sk-ant-api03-...` |

The proxy must forward **whichever** the client sent, unchanged. Don't normalize one to the other.

```python
# Pseudocode for the auth-forwarding step in main.py
forwarded_headers = {}
for h in ("Authorization", "x-api-key", "anthropic-version", "anthropic-beta"):
    v = request.headers.get(h)
    if v is not None:
        forwarded_headers[h] = v
forwarded_headers["Content-Type"] = "application/json"
```

If neither auth header is present and no key is configured in `~/.aivion-mask/config.toml`, return 401 with a clear message.

### 3. `anthropic-version` header is required

Anthropic returns 400 if the request lacks `anthropic-version`. The CLI / SDKs always send it. The proxy must forward it byte-for-byte. **Do not** hardcode a default version — Anthropic adds breaking changes between versions and the client picked theirs deliberately.

Same for `anthropic-beta` when present (used for tool use, prompt caching, etc.).

---

## Request body walking

Anthropic's request body is recursive. The masker needs to traverse all string-bearing fields:

```jsonc
{
  "model": "claude-sonnet-4-6",            // skip — not user-provided text
  "max_tokens": 4096,                       // skip
  "system": "<string>" | [                  // mask all .text fields
    { "type": "text", "text": "<mask>", "cache_control": {...} }
  ],
  "messages": [
    {
      "role": "user" | "assistant",
      "content": "<string>" | [             // mask string OR walk block array
        { "type": "text", "text": "<mask>" },
        { "type": "image", "source": {...} },           // skip — binary/url
        { "type": "tool_use", "id": "...",
          "name": "...", "input": <json> },             // walk JSON values? — see Gotchas
        { "type": "tool_result", "tool_use_id": "...",
          "content": "<string>" | [...] },              // mask
        { "type": "document", "source": {...} }         // skip — binary/url
      ]
    }
  ],
  "tools": [
    { "name": "...", "description": "<string>",         // skip — schema text, not user data
      "input_schema": {...} }
  ],
  "metadata": { "user_id": "..." }                      // skip — Anthropic-side tracking
}
```

The walker is mechanically simple: a recursive function that mutates `text` fields in place when `type == "text"` or operates on string `content` directly. Image and document blocks are passed through unchanged.

### What about `tool_result.content`?

This is where prior tool-call output gets fed back to the model. Often contains the full output of `bash`, `read_file`, etc. — **prime location for leaked secrets**. Must mask.

### What about `tool_use.input`?

This is the JSON payload the *previous* assistant turn requested as tool args. By the time the user sends the next request with tool results, the assistant's tool call already happened upstream and was unmasked in the response stream. So when the request loop comes back around, `tool_use.input` should already contain the original (unmasked) values that the assistant generated.

But: if the masker pre-redaction loop sees an original value in `tool_use.input` that's now in the session map, it should re-redact it before sending. So **walk JSON values in `tool_use.input` too**.

---

## Response body walking (non-streaming)

Less common — most clients use streaming — but must work for SDK users who set `stream=False`:

```jsonc
{
  "id": "msg_xxx",
  "type": "message",
  "role": "assistant",
  "content": [
    { "type": "text", "text": "<unmask>" },
    { "type": "tool_use", "id": "...", "name": "...",
      "input": { /* walk JSON values, unmask placeholders */ } }
  ],
  "stop_reason": "end_turn",
  "usage": { ... }
}
```

Walk every text field through `replace_tokens(text, mappings)`. Walk tool_use input JSON recursively, replacing tokens in string leaves.

---

## Streaming format

Anthropic SSE is **not** the same as OpenAI's. Differences that matter:

| Feature | OpenAI | Anthropic |
|---|---|---|
| Line shape | `data: {...}\n\n` | `event: <name>\n` + `data: {...}\n\n` |
| Stream end | `data: [DONE]` | `event: message_stop` |
| Delta content | `choices[].delta.content` (always text) | `delta.text` (text), `delta.partial_json` (tool args) |
| Block tracking | one stream per choice | indexed `content_block_start` / `content_block_stop` per block |
| Errors mid-stream | `data: {"error":...}` | `event: error\ndata: {...}` |

### Event sequence example (text response)

```
event: message_start
data: {"type":"message_start","message":{"id":"msg_xxx",...}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"The "}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"answer"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{...}}

event: message_stop
data: {"type":"message_stop"}
```

### Event sequence example (tool use)

```
event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"toolu_xxx","name":"bash","input":{}}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"{\"command\": \""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"psql __DB"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"1__\"}"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}
```

The placeholder `__DB1__` is split across **two** `partial_json` deltas. The unmasking logic has to handle this.

### Streaming implementation strategy

For **text deltas** (`delta.type == "text_delta"`):
- Reuse the existing `LookaheadBuffer` per `index` (one buffer per content block — not one global buffer)
- Push each `delta.text` into the buffer, emit safe portion as the new `delta.text`
- On `content_block_stop` for that index, flush the buffer

For **input_json deltas** (`delta.type == "input_json_delta"`):
- Per-index buffer that accumulates `partial_json` strings
- Apply unmask to the accumulated string before re-emitting (string-level unmasking is fine — the LLM emits valid JSON eventually)
- Re-emit the full unmasked partial as the next `partial_json` delta, using a "high-water mark" approach so the client sees forward progress
- Simpler alternative: hold all `input_json_delta`s for an index, only emit when `content_block_stop` for that index arrives, reconstruct as one large delta. Loses the streaming feel for tool args but is correct and shippable. **Pick this for v1.5**, optimise later.

For **other events** (`message_start`, `message_delta`, `message_stop`, `ping`, `error`):
- Pass through unchanged.

### Parser shape

```python
async def parse_anthropic_sse(byte_stream):
    """Yields (event_name, json_payload) tuples."""
    pending_event = None
    async for line in byte_stream.aiter_lines():
        if line.startswith("event: "):
            pending_event = line[7:].strip()
        elif line.startswith("data: "):
            payload = json.loads(line[6:])
            yield pending_event, payload
            pending_event = None
        elif line == "":
            pass  # SSE event boundary
```

---

## Files to create / modify

### New

- `sidecar/aivion_mask_sidecar/anthropic.py` — request walker, response walker, streaming parser, per-block buffer manager
- `sidecar/tests/test_anthropic.py` — fixtures + unit tests for each walker
- `sidecar/tests/fixtures/anthropic_sse_*.txt` — captured SSE event streams for tests

### Modified

- `sidecar/aivion_mask_sidecar/main.py` — add `POST /v1/messages` route, route-to-upstream map, header pass-through
- `sidecar/aivion_mask_sidecar/proxy.py` — generalize `forward_complete` / `forward_streaming` to accept incoming headers + per-route upstream
- `sidecar/aivion_mask_sidecar/config.py` — `DEFAULT_UPSTREAMS` constant + optional override map
- `sidecar/tests/test_proxy.py` — add pass-through tests
- `sidecar/tests/test_main.py` — add `/v1/messages` smoke test
- `sidecar/pyproject.toml` — version bump

---

## Tests

### Unit (no network)

- Walker: mask string `system` → unchanged shape, masked content
- Walker: mask block-array `system` → walks each `text` field
- Walker: mask `messages[].content` string form
- Walker: mask `messages[].content` block array (text + image + tool_result mix)
- Walker: mask `tool_result.content` string and array forms
- Walker: walk `tool_use.input` JSON, mask string leaves
- Response walker: unmask `content[].text`, unmask `tool_use.input` JSON leaves
- SSE parser: parse `event:` + `data:` pairs
- SSE parser: handle malformed events gracefully (skip + continue)
- Streaming: text delta with placeholder split across two chunks → unmasks correctly
- Streaming: input_json_delta with placeholder split across two chunks → unmasks correctly
- Streaming: passes through `ping` events unchanged
- Streaming: passes through `error` events unchanged

### Integration (respx-mocked)

- Full request + complete response with API key auth
- Full request + complete response with OAuth Bearer auth
- Full streaming response with text deltas
- Full streaming response with tool_use deltas
- Header pass-through preserves `anthropic-version`, `anthropic-beta`
- Auth precedence: client header wins over configured key
- 401 when no auth provided and no key configured

### Manual smoke (must pass before shipping v1.5)

1. `ANTHROPIC_BASE_URL=http://localhost:47474 claude "what model are you?"` — works in subscription mode
2. Same with `ANTHROPIC_API_KEY` set in env, no subscription — works
3. Same prompt with a fake DB URL embedded — masked in proxy logs, original restored in CLI output
4. Multi-turn: turn 1 introduces a secret, turn 3 mentions it again — confirm pre-redaction prevents re-exposure
5. Streaming: same prompt with `stream=True` (Claude Code uses streaming by default) — placeholders unmasked at the chunk boundary
6. Tool use: ask Claude to run a `bash` command involving a DB URL — confirm the placeholder gets unmasked in the tool_use.input JSON before the user sees it

---

## Per-tool setup

| Tool | Setup |
|---|---|
| **Claude Code (CLI)** | `export ANTHROPIC_BASE_URL=http://localhost:47474` in shell rc |
| **Claude Code in VS Code** | Same env var — restart VS Code after adding to shell rc |
| **Anthropic Python SDK** | `Anthropic(base_url="http://localhost:47474")` or env var |
| **Anthropic TypeScript SDK** | `new Anthropic({ baseURL: 'http://localhost:47474' })` or env var |
| **Continue.dev** | Set `apiBase: "http://localhost:47474"` in `~/.continue/config.json` |
| **aider** (claude models) | `export ANTHROPIC_API_BASE=http://localhost:47474` (litellm convention) |
| **llm + llm-anthropic** | `export ANTHROPIC_API_BASE=http://localhost:47474` |
| **OpenCode** | Set `ANTHROPIC_BASE_URL` in OpenCode config or env |

---

## Gotchas

### 1. Claude Code OAuth tokens are long-lived but not infinite

The OAuth token in macOS Keychain (`Claude Code-credentials`) is refreshed by Claude Code itself periodically. The proxy never stores the token — it just forwards the header. If Anthropic rotates auth or the user logs out, the next request gets 401 from upstream and the proxy passes that through. **Don't cache the token in the proxy.**

### 2. `anthropic-version` is required and not stable

Anthropic introduces breaking changes between API versions (e.g., `2023-06-01` vs `2024-10-01`). Always forward the client's chosen version. Don't ever override.

### 3. Mask `tools[].description` — yes or no?

Tool descriptions are author-written, often contain internal API URLs, schema field names, or example values that may be sensitive. Default decision: **don't mask**, because the description is part of the tool definition (the developer wrote it deliberately) and masking it would break tool routing. Make this configurable later (`mask_tool_descriptions: bool` in config.toml) for users with strict policies.

### 4. Prompt caching breaks if we mask cached content

Anthropic supports `cache_control: {"type": "ephemeral"}` on content blocks. Cached blocks must be **byte-identical** across requests for the cache to hit. If we mask differently between requests (e.g., a new secret appears in a previously-cached block), the cache misses and the user pays full price.

Mitigations:
- The session model already produces stable tokens for the same input (`__DB1__` for `postgresql://...` is consistent within a session)
- BUT: if a session expires (8h TTL) and a new session starts mid-request, tokens may differ — this would break caching
- **Recommendation:** when a request has any `cache_control` blocks, log it and document that caching may be reduced; revisit if users complain

### 5. The `metadata.user_id` field

Anthropic uses this for abuse tracking. The proxy may overwrite it (we pop `user` from OpenAI requests today for the same reason). For Anthropic, **leave `metadata` alone** — overwriting it might trigger Anthropic's abuse detection and get the user rate-limited.

### 6. Subscription tokens have different rate limits

OAuth subscription tokens are subject to user-tier rate limits (Pro vs Max). API keys are subject to org-tier limits. The proxy can't change this — it forwards 429 from upstream. Make sure error pass-through preserves the `retry-after` header.

### 7. `anthropic-beta` features may add new content block types

`computer-use-2024-10-22`, `prompt-caching-2024-07-31`, etc., introduce new block types (`computer_use`, `cache_control`). The walker should be **block-type-aware**: only walk known-text-bearing types, pass through unknown types unmodified. Don't try to mask things you don't understand.

### 8. Claude.ai web is *not* in this plan

Claude.ai's web frontend talks to a different API (`https://claude.ai/api/...`) with cookie auth and a proprietary message shape. That's the browser extension's job (v1.6), not the sidecar's. **Don't try to handle `claude.ai` here.**

---

## Phasing (within v1.5)

**Day 1–2:** Auth pass-through in `main.py` + `proxy.py`, generalize forwarder to accept incoming headers and per-route upstreams. Tests for pass-through.

**Day 3–4:** `anthropic.py` request walker (system, messages, tool_result, tool_use.input). Unit tests for each shape.

**Day 5:** `anthropic.py` non-streaming response walker. Tests.

**Day 6–7:** SSE parser for Anthropic events. Per-block `LookaheadBuffer` for text deltas. Hold-and-emit strategy for `input_json_delta`. Tests with fixture SSE streams.

**Day 8:** End-to-end manual smoke against `api.anthropic.com` with real OAuth and real API key. Iterate on bugs.

**Day 9:** Documentation — per-tool setup table in README, troubleshooting guide.

**Day 10:** Buffer day for the inevitable surprise.

That's two work weeks. After day 10, Claude provider is shippable.

---

## Verification scope before v1.5 ships

These claims need empirical confirmation, not assumption:

| Claim | How to verify |
|---|---|
| Claude Code respects `ANTHROPIC_BASE_URL` | `ANTHROPIC_BASE_URL=http://localhost:9999 claude` — should error with connection refused, proving env var is honored |
| OAuth token from Keychain is sent as `Authorization: Bearer ...` header | tcpdump or proxy logs on a request from authenticated Claude Code |
| API-key requests use `x-api-key` header (not `Authorization`) | Same — capture a request from `ANTHROPIC_API_KEY=... claude` |
| `anthropic-version` and `anthropic-beta` are present on every request | Log request headers in proxy |
| Streaming events follow the documented event/data line format | Capture `claude` SSE response, save as fixture |

Do not commit the v1.5 ship until these five items are verified on this machine.

---

## What's intentionally NOT in this plan

- **Bedrock / Vertex Claude** — different endpoints, different auth, different request shapes. Separate `docs/LLM/BEDROCK_CLAUDE.md` if/when needed.
- **Claude.ai browser** — v1.6 browser extension, separate file.
- **Tool result post-processing** beyond unmasking — no policy enforcement on tool args, no "block if dangerous" logic.
- **Per-message rate-limit shaping** — proxy is transparent, upstream limits apply.
- **Cost / token accounting** — out of scope; users have Anthropic dashboard for that.
