# aivion-mask — VS Code Phase 1: Machine-Level Sidecar + Proxy Mode

**Date:** 2026-05-07
**Status:** Approved
**Scope:** Python sidecar (machine-level service), OpenAI-compatible proxy, Presidio NER, SQLite sessions, SSE streaming, MCP endpoint, VS Code extension lifecycle manager, `core/recognizers/` refactor

---

## 1. Goal

Extend the aivion-mask VS Code extension (Phase 0: clipboard guard) with a machine-level Python sidecar that acts as a transparent OpenAI-compatible proxy. Any IDE tool (Continue, Cursor, or any tool that supports a custom `apiBase`) points to `localhost:47474`. The sidecar masks credentials and PII before the prompt reaches the LLM, and restores originals in the response — entirely on the local machine, nothing leaves the device.

The sidecar is not VS Code-specific. It is a machine-level service installed by whichever client comes first (VS Code extension, browser extension, or CLI). All future clients connect to the same running process.

---

## 2. What We Are NOT Building in Phase 1

- Browser extension (designed for, not built)
- Mobile (separate platform entirely)
- Enterprise server connect / team sessions
- False-positive trainer
- Gutter decorations or live editor scan (Phase 2)
- Deterministic pseudonymization mode (Phase 3)
- Audit trail persistence (Phase 2 of PLAN.md)

---

## 3. Architecture Overview

```
Continue / Cursor / any OpenAI-compatible tool
  │
  │  POST http://localhost:47474/v1/chat/completions
  ▼
┌─────────────────────────────────────────┐
│  aivion-mask sidecar (Python)           │
│  port 47474                             │
│                                         │
│  masker.py   Presidio NER               │
│  tokens.py   __P1__ counter per session │
│  session.py  SQLite TTL store           │
│  stream.py   SSE lookahead buffer       │
│  proxy.py    HTTP forward to real LLM   │
│  mcp.py      MCP manifest endpoint      │
└──────────────────┬──────────────────────┘
                   │ forwards masked request
                   ▼
         Real LLM (user-configured apiBase)
         OpenAI / Anthropic / Gemini / Ollama / any
                   │
                   │ streaming response (__P1__ tokens)
                   ▼
         stream.py lookahead buffer
         unscrubs tokens as chunks pass through
                   │
                   ▼
         Restored response → Continue / Cursor

~/.aivion-mask/
  config.toml    apiBase, apiKey, port, session_ttl_hours
  sessions.db    SQLite — {session_id, token, original_value, expires_at}
  sidecar.pid    PID file
  venv/          Python venv (auto-created on first run)
```

**Clients — all connect to the same sidecar:**

| Client | How it installs sidecar | Phase |
|---|---|---|
| VS Code extension | Auto-installs venv + registers system service | Phase 1 (now) |
| Browser extension | Native Messaging triggers standalone installer | Browser Phase 1 |
| CLI | `aivion-mask install-service` | Future |

---

## 4. Python Sidecar

### 4.1 Location

```
sidecar/
  aivion_mask_sidecar/
    __init__.py
    main.py        FastAPI app — all routes, CORS, startup
    masker.py      Presidio analyzer, developer policy
    session.py     SQLite session CRUD + TTL cleanup
    tokens.py      __P1__ counter, deterministic within session
    stream.py      SSE lookahead buffer + unscrub
    proxy.py       Async HTTP forward to real LLM (httpx)
    mcp.py         MCP manifest endpoint
    config.py      config.toml loader (pydantic-settings)
  pyproject.toml   requires Python >=3.10
  requirements.txt
```

### 4.2 Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check — returns `{"status": "ok", "version": "..."}` |
| `POST` | `/v1/chat/completions` | OpenAI-compatible proxy — main entry point |
| `GET` | `/mcp` | MCP manifest for auto-discovery by Continue and MCP-aware tools |
| `DELETE` | `/v1/session/{session_id}` | Wipe session mapping (GDPR erasure, manual clear) |

### 4.3 CORS

Allow all of the following origins (sidecar serves local clients only):
- `http://localhost:*`
- `http://127.0.0.1:*`
- `chrome-extension://*`
- `moz-extension://*`
- VS Code extension webview origin

### 4.4 Masking Pipeline

```
POST /v1/chat/completions received
  │
  ├─ Extract session_id
  │    Priority: X-Aivion-Session header → "user" field in request → generate new UUID
  │
  ├─ For each message in messages[]:
  │    ├─ Pre-redact: replace any tokens already in session (prevents turn-3 leak)
  │    └─ Run Presidio on pre-redacted text → new entities
  │
  ├─ Assign __P1__, __P2__... tokens (incrementing counter per session)
  │    ├─ Same value in same session always gets same token
  │    └─ Persist token ↔ original_value in sessions.db with TTL
  │
  ├─ Replace entities in message content with tokens
  │
  └─ Forward modified request to real LLM (proxy.py)
```

### 4.5 Token Format

- Format: `__P{n}__` where n is a session-scoped incrementing integer (1, 2, 3...)
- Same original value in the same session always maps to the same token
- Short (5–9 chars) — SSE chunks are typically 4–8 chars, so a token rarely splits
- Stored in `sessions.db`: `(session_id, token, original_value, expires_at)`

### 4.6 Streaming + Lookahead Buffer (`stream.py`)

The LLM response arrives as SSE chunks. `__P1__` tokens can split across chunk boundaries (e.g. chunk 1: `__P`, chunk 2: `1__`). The lookahead buffer handles this:

```
Algorithm:
  buffer = ""
  for each chunk from LLM:
    buffer += chunk.content
    safe_flush, buffer = split_at_safe_point(buffer)
    unscrubbed = replace_complete_tokens(safe_flush, session)
    yield unscrubbed

  # flush remainder when stream ends
  yield replace_complete_tokens(buffer, session)

split_at_safe_point(text):
  # Safe to flush everything up to the last __ that hasn't closed yet
  # If text ends with partial token (contains __ but no closing __):
  #   hold back from last __ onward
  # Otherwise: flush all
```

Buffer hold-back is at most ~15 characters — negligible latency impact.

### 4.7 Session Store (`session.py`)

SQLite schema:
```sql
CREATE TABLE sessions (
  session_id   TEXT NOT NULL,
  token        TEXT NOT NULL,        -- __P1__
  original     TEXT NOT NULL,        -- actual secret value
  token_index  INTEGER NOT NULL,     -- 1, 2, 3... per session
  created_at   INTEGER NOT NULL,     -- unix timestamp
  expires_at   INTEGER NOT NULL,     -- unix timestamp
  PRIMARY KEY (session_id, token)
);

-- Reverse lookup: "does this value already have a token in this session?"
CREATE UNIQUE INDEX idx_session_original ON sessions(session_id, original);
CREATE INDEX idx_session_expiry ON sessions(expires_at);
```

Token counter per session: `SELECT MAX(token_index) FROM sessions WHERE session_id = ?` — next token is `MAX + 1` (or 1 if no rows yet).

TTL cleanup: background task runs every 10 minutes, deletes rows where `expires_at < now()`.

Default TTL: 8 hours (configurable in `config.toml`).

### 4.8 Presidio / Developer Policy (`masker.py`)

Entities detected in Phase 1 (developer policy — credentials and secrets):

| Entity | Detection method |
|---|---|
| `AWS_ACCESS_KEY_ID` | Custom regex (`AKIA[A-Z0-9]{16}`) |
| `AWS_SECRET_KEY` | Custom regex (context-based) |
| `GITHUB_TOKEN` | Custom regex (`ghp_`, `ghs_`, `github_pat_`) |
| `OPENAI_API_KEY` | Custom regex (`sk-`, `sk-proj-`) |
| `ANTHROPIC_API_KEY` | Custom regex (`sk-ant-api`) |
| `GOOGLE_API_KEY` | Custom regex (`AIza`) |
| `STRIPE_KEY` | Custom regex (`sk_live_`, `sk_test_`) |
| `DATABASE_URL` | Custom regex (postgres://, mysql://, mongodb://) |
| `PRIVATE_KEY` | Custom regex (PEM headers) |
| `JWT_TOKEN` | Custom regex (eyJ....) |
| `SLACK_TOKEN` | Custom regex (`xoxb-`, `xoxp-`) |
| `URL_WITH_CREDENTIALS` | Custom regex |
| `PRIVATE_IP` | Custom regex (10.x, 192.168.x, 172.16-31.x) |

These mirror the 42 patterns already in `core/recognizers/index.ts`. Python patterns are the equivalent regex, wrapped as Presidio `PatternRecognizer` instances.

Presidio is used as the orchestration layer — all recognizers are custom (credential-focused), not the default Presidio PII set. The default Presidio PII entities (PERSON, EMAIL, etc.) are OFF in Phase 1 developer policy.

### 4.9 Configuration (`config.py`)

`~/.aivion-mask/config.toml`:
```toml
[sidecar]
port = 47474
session_ttl_hours = 8
idle_shutdown_minutes = 0   # 0 = never auto-shutdown

[llm]
api_base = "https://api.openai.com/v1"
api_key = "sk-..."
```

Config loaded at startup via pydantic-settings. File is created with defaults on first run if absent.

### 4.10 MCP Endpoint (`mcp.py`)

`GET /mcp` returns a JSON manifest describing the sidecar to MCP-aware tools:

```json
{
  "name": "aivion-mask",
  "version": "0.1.0",
  "description": "Local PII masking proxy — credentials and secrets never reach your LLM",
  "proxy": {
    "url": "http://localhost:47474/v1",
    "protocol": "openai"
  },
  "health": "http://localhost:47474/health"
}
```

The VS Code extension reads this on startup and auto-configures Continue.dev by writing to `~/.continue/config.json` if Continue is installed.

---

## 5. VS Code Extension Changes

### 5.1 New file: `sidecar.ts`

Responsibilities:
1. Check if sidecar is running (`GET /health`)
2. If not running: check for venv → install if missing → spawn process
3. Write PID to `~/.aivion-mask/sidecar.pid`
4. Register as system service (launchd / systemd / Task Scheduler) on first install
5. Poll `/health` until ready (max 30s with progress notification)
6. Return sidecar URL to caller

**First-run install sequence:**
```
Extension activates
  → GET http://localhost:47474/health
  → 200 OK → done, sidecar already running
  → Fail →
      Check ~/.aivion-mask/venv/bin/aivion-mask-sidecar exists
      No → show progress: "Setting up Aivion Mask sidecar (first time only)..."
           python3 -m venv ~/.aivion-mask/venv
           ~/.aivion-mask/venv/bin/pip install aivion-mask-sidecar
      Spawn: ~/.aivion-mask/venv/bin/aivion-mask-sidecar
      Register system service (platform-specific)
      Poll /health every 500ms up to 30s
      → Ready → dismiss progress, update status bar
      → Timeout → show error: "Aivion Mask sidecar failed to start. Check output panel."
```

**On VS Code deactivate:** Do NOT stop the sidecar. Other clients (browser extension) may be using it.

### 5.2 Updated `extension.ts`

Add sidecar startup call in `activate()`:
```typescript
// After clipboard monitor setup:
const sidecar = new SidecarManager(context)
await sidecar.ensureRunning()
// Update status bar to show proxy is active
```

### 5.3 Updated `statusBar.ts`

Add a second status bar state: proxy active. Show `Aivion Mask: proxy :47474` when sidecar is running, `Aivion Mask: clipboard only` when sidecar is unavailable.

### 5.4 System Service Registration

| Platform | Method |
|---|---|
| macOS | Write `~/Library/LaunchAgents/com.aivionlabs.mask.plist`, run `launchctl load` |
| Linux | Write `~/.config/systemd/user/aivion-mask.service`, run `systemctl --user enable --now` |
| Windows | `schtasks /create` with `ONLOGON` trigger |

Service is registered once on first install. Extension checks for registration on subsequent activations and skips if already registered.

---

## 6. `core/recognizers/` Refactor

Move `extension/vscode/src/recognizers.ts` → `core/recognizers/index.ts`.

`extension/vscode/src/recognizers.ts` becomes a re-export:
```typescript
export * from '../../../core/recognizers/index'
```

No functional change to the VS Code extension. The browser extension will import from `core/recognizers/` when that work begins.

`core/recognizers/` has its own `package.json` so it can be imported as a local workspace package by both extensions.

---

## 7. Proxy Request/Response Contract

### Request (from IDE tool → sidecar)

Standard OpenAI chat completions format. Sidecar reads:
- `messages[].content` — mask each message's content
- `model` — pass through to real LLM unchanged (or override from config)
- `stream` — pass through; sidecar handles both streaming and non-streaming
- `user` — used as session_id fallback if `X-Aivion-Session` header absent

### Response (sidecar → IDE tool)

Streaming: SSE `data: {...}` chunks, same format as OpenAI. Tokens unscrubbed via lookahead buffer.

Non-streaming: complete JSON response, tokens unscrubbed before returning.

---

## 8. Error Handling

| Scenario | Behaviour |
|---|---|
| Real LLM unreachable | Return 502 with `{"error": "upstream LLM unreachable"}` |
| No `api_key` in config | Return 400 with `{"error": "No LLM API key configured. Edit ~/.aivion-mask/config.toml"}` |
| Presidio detection fails | Log warning, pass message through unmasked (fail open — don't break the user's workflow) |
| Session TTL expired mid-conversation | Unscrub returns token as-is (e.g. `__P1__` stays), log warning |
| sidecar port already in use | Log error, try port+1 up to 3 times, update config.toml with actual port |

---

## 9. Testing

### Python sidecar (pytest)
- `test_masker.py` — each pattern: positive match, negative match, overlap deduplication
- `test_session.py` — TTL expiry, same-value same-token, cross-session isolation
- `test_stream.py` — token split across chunks, multi-token in one chunk, no tokens (passthrough)
- `test_proxy.py` — mock upstream server, verify masked request forwarded, response unscrubbed

### TypeScript extension (mocha / @vscode/test-electron)
- `sidecar.test.ts` — mock venv + process spawn, health-check polling, timeout behaviour
- Existing clipboard + recognizer tests remain unchanged

---

## 10. Out of Scope (Explicitly Deferred)

- Per-project `.aivion-mask.json` config (Phase 2)
- General PII policy (PERSON, EMAIL, PHONE) — developer policy only in Phase 1
- Browser extension Native Messaging host registration
- Standalone installer package (`aivion-mask-installer`)
- CLI tool
- Audit trail
- Session history panel / webview
- Inline gutter decorations
