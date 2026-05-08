# aivion-mask — Research Notes

How the system works, why each design decision was made, and what the literature/prior art says.

---

## 1. The Problem

Every time a developer pastes a database URL, API key, or internal hostname into an AI assistant — Claude Code, Cursor, GitHub Copilot, ChatGPT — that value leaves their machine and lands in an LLM provider's logs, training pipeline, or breach surface.

The developer knows this is bad. They do it anyway because stopping to sanitize every paste is too much friction.

The right solution intercepts the data silently, before it reaches the network, and puts the original values back in the response. Zero friction. Zero trust in the provider.

---

## 2. Interception Approaches

Four places you can intercept LLM traffic. Each has a different coverage radius.

### 2a. Clipboard Guard (Phase 0)

**How it works:** Poll the OS clipboard every 500ms. If a credential pattern is detected, either warn the user or silently replace the clipboard contents with a masked version.

**Coverage:** Anything the user copy-pastes manually. Doesn't cover programmatic calls (Cursor's background indexing, Claude Code's file reads).

**Why it was Phase 0:** Zero installation friction. Gives immediate value to users who paste secrets into chat. Acts as a safety net while the proxy-based approach is built. Not currently pursued — proxy approach covers more surface area.

**Limitation:** The masking happens at paste time, not at send time. If the user typed the secret directly, it's not caught. If the app sends it programmatically, it's not caught.

---

### 2b. Local Proxy (Phase 1 — current)

**How it works:** A local FastAPI server on port 47474 acts as an OpenAI-compatible endpoint. The developer configures their LLM client to point at `http://localhost:47474/v1` instead of `https://api.openai.com/v1`. The proxy masks outbound content, forwards to the real LLM, and unmasks the response.

**Coverage:** Any app that respects `OPENAI_BASE_URL` or equivalent config. Covers most developer tools (Continue.dev, aider, custom scripts, local apps). Doesn't cover subscription apps that have the API URL hardcoded (Cursor Pro, Claude Code, GitHub Copilot).

**Why a proxy and not an SDK:** An SDK requires patching every app individually. A proxy is app-agnostic — any tool that speaks HTTP gets coverage automatically.

**Latency overhead:** Measured at ~2ms on localhost (one loopback round-trip + regex scan). For a 200-token message, the regex scan takes ~0.1ms in a thread pool. Negligible compared to LLM inference latency (500ms–5s).

**The key insight — pre-redaction across turns:**
Without session memory, turn 3 of a conversation can re-expose a secret from turn 1. The session model solves this: before running regex detection on a new message, the proxy replaces all known originals (from previous turns) with their tokens. The LLM never sees the original value in any turn.

```
Turn 1: "My DB is postgresql://user:pass@host/db"
        → __DB1__ stored in sessions.db

Turn 2: "Add a migration to the DB postgresql://user:pass@host/db"
        → Pre-redaction replaces it with __DB1__ before regex even runs
        → LLM never sees the original in Turn 2 either
```

---

### 2c. Network-Level MITM (Phase 2 — planned)

**How it works:** Install a local CA certificate into the OS trust store. Use OS-level packet filtering (macOS `pf`, Linux `iptables`, Windows WFP) to redirect all port 443 traffic to a local MITM proxy. The proxy performs TLS termination using dynamically generated per-domain certificates signed by the local CA, applies masking, and re-encrypts to the real LLM endpoint.

**Coverage:** Everything on the machine. No app-level configuration required. Subscription tools (Cursor Pro, Claude Code, GitHub Copilot) are covered because their traffic hits the proxy before reaching the network.

**Why this is the right long-term architecture:** Corporate DLP tools (Zscaler, Netskope, Cisco Umbrella) have used this architecture for a decade to inspect HTTPS traffic for data leakage. aivion-mask is the developer-focused, local-only, open-source version of the same pattern.

**Trust model — NameConstraints:** The CA certificate is generated locally and never leaves the machine. To limit blast radius if it were somehow extracted, the CA uses the X.509 `NameConstraints` extension to restrict it to only the specific LLM domains the user has explicitly opted into:

```
X509v3 Name Constraints:
  Permitted:
    DNS:api.openai.com
    DNS:api.anthropic.com
    DNS:generativelanguage.googleapis.com
```

A browser or OS will reject a certificate from this CA for any domain not in the permitted list. Even if an attacker extracted the CA private key, they could not issue a certificate for `google.com` or `github.com`. The key is only useful for the domains the user chose.

**sudo requirement:** Installing a CA into the OS trust store and loading `pf` rules requires elevated privileges. This is unavoidable. The setup wizard requests `sudo` once. After that, normal operation requires no elevated privileges.

---

### 2d. SDK Injection (future)

**How it works:** A pip/npm package that wraps the official LLM SDK. `MaskClient` wraps `openai.OpenAI`, intercepts all `.chat.completions.create()` calls, and applies masking in-process.

**Coverage:** Python/TypeScript apps that install the SDK explicitly. Zero network overhead (no local proxy hop). Best for developers building apps, not for protecting IDEs.

**Gap:** Doesn't cover CLI tools, VS Code extensions, or any app the developer doesn't control.

---

## 3. Detection: Regex vs. NER

aivion-mask currently uses pure regex for detection. Here's why, and when NER would be worth adding.

### Regex (current approach)

32 patterns covering the major credential formats: AWS keys, GitHub tokens, OpenAI/Anthropic API keys, database URLs, JWTs, Stripe keys, Slack tokens, private IPs, and more.

**Strengths:**
- Zero false positives for structured credentials (AWS keys have a specific 20-char AKIA prefix + entropy — no ambiguity)
- Deterministic — same input always produces same output
- Fast — 32 compiled patterns scan a 500-token message in ~0.1ms
- No external dependencies — works offline, no model to download

**Weaknesses:**
- Can't detect unstructured PII: names, email addresses, phone numbers, addresses
- Can't detect custom internal formats it hasn't seen
- Pattern maintenance — new credential formats need manual additions

### NER / Presidio (researched, not yet implemented)

Microsoft Presidio uses spaCy NER models to detect named entities (person names, email addresses, phone numbers, org names) that don't have a structured format.

**Would add:**
- Email addresses: `john.doe@internal.company.com`
- Person names: `John Doe, VP Engineering` — contextually sensitive
- Phone numbers, addresses
- Custom entity types via fine-tuning

**Trade-offs:**
- spaCy model is ~50MB download; `en_core_web_sm` is the smallest at ~12MB
- NER inference adds ~10–30ms per message (vs 0.1ms for regex)
- False positive rate is higher — "Apple" as a person's nickname vs. the company
- Determinism is weaker — model output can vary by version

**Verdict:** Regex is the right foundation for credentials (structured, high-confidence). NER is worth adding as an optional layer for unstructured PII — off by default, opt-in for users who need it. The scrubber service in `sheru-platform` already uses Presidio; the architecture is well understood.

---

## 4. Token Format Design

### Why `__DB1__` and not `[REDACTED:DATABASE_URL]`

The Phase 0 extension uses `[REDACTED:DATABASE_URL_POSTGRES]` tokens. These are human-readable but have two problems:

**Problem 1 — Streaming safety.** LLM responses arrive as a stream of small chunks. If a token spans multiple chunks, the unmask step must buffer partial tokens. `[REDACTED:DATABASE_URL_POSTGRES]` is 36 characters. A 36-character buffer is large — any chunk smaller than 36 characters triggers a lookahead hold.

`__DB1__` is 7 characters. The lookahead buffer only needs to hold 7 characters, which is almost never split across chunks.

**Problem 2 — Context window efficiency.** LLMs have finite context windows. `[REDACTED:DATABASE_URL_POSTGRES]` uses 36 tokens in the LLM's vocabulary. `__DB1__` uses 3–4 tokens. For a message with 10 masked values, this saves ~300 context tokens.

**Problem 3 — LLM confusion.** Long bracket-format tokens look like instructions to some LLMs. `[REDACTED:X]` has been observed to cause LLMs to generate their own `[REDACTED:Y]` tokens in responses. Short double-underscore tokens (`__DB1__`) look like code identifiers, which LLMs handle predictably.

### Why double underscores

`__TOKEN__` is the Python dunder convention — unambiguous in any text, rarely occurs naturally in prose or code except as a Python magic method name. The regex `__[A-Z]{2,6}\d+__` has an extremely low false-positive rate.

Single underscores (`_DB1_`) or angle brackets (`<DB1>`) appear too often in natural text and code.

### Why type-specific abbreviations

`__DB1__`, `__DB2__` instead of `__P1__`, `__P2__` gives the LLM semantic context. An LLM that sees `__DB1__` in a migration script knows it's likely a connection string, not a name or an API key. This improves the quality of LLM responses when secrets appear in functional code.

---

## 5. Streaming and the Split-Token Problem

LLM streaming uses Server-Sent Events (SSE). The response arrives as a series of JSON chunks:

```
data: {"choices":[{"delta":{"content":"the value is __DB"}}]}
data: {"choices":[{"delta":{"content":"1__ ok"}}]}
data: [DONE]
```

The token `__DB1__` was split across two chunks. A naive unmask step that replaces `__DB1__` in each chunk independently would fail — neither chunk contains the complete token.

### LookaheadBuffer

The proxy uses a `LookaheadBuffer` that holds back any suffix that could be the start of a token:

```python
_PARTIAL_RE = re.compile(r'_[_A-Z\d]*_?')
```

When a chunk arrives, the buffer checks if it ends with a potential partial token (`__DB`, `__`, `_D`). If so, it withholds that suffix and waits for the next chunk. When the next chunk arrives, the buffer prepends the withheld suffix and checks again.

**Latency impact:** The buffer adds one chunk of latency (~20ms at typical LLM stream rates). This is undetectable to the user.

**Edge case — no complete token:** If the stream ends and the buffer still holds a partial match that turned out to not be a real token (e.g. `__not_a_token`), `buf.flush()` releases it unchanged.

---

## 6. Session Model and the Turn-3 Leak

### The problem

Consider this conversation:

```
Turn 1: "My DB URL is postgresql://user:pass@host/db"
        Proxy masks → "My DB URL is __DB1__"
        LLM responds → "Got it, I'll use __DB1__"
        Proxy unmasks response → shown to user as-is (or unmasked)

Turn 2: "Write a migration for that database"
        No credentials in this message — proxy passes it unchanged
        LLM responds fine

Turn 3: "Here's the error from postgresql://user:pass@host/db:"
        Turn 3 contains the original credential again
```

If the proxy only runs regex on the current message, Turn 3 re-exposes the credential. The LLM now has the original value in its context.

### The solution — pre-redaction

Before running regex detection on any new message, the proxy loads all known (token → original) mappings for the session and replaces every known original with its token:

```python
mappings = await get_all_mappings(conn, session_id)
for token, original in mappings.items():
    text = text.replace(original, token)
# Then run regex on the already-sanitised text
entities = await loop.run_in_executor(None, detect, text)
```

Turn 3 is sanitized before regex even runs. The LLM never sees the original value.

### Session identity

The `X-Aivion-Session` header is the primary session identifier. If absent, the proxy falls back to the `user` field in the request body (OpenAI convention), then generates a new UUID per request.

For tools that don't send session headers (most IDEs), the UUID-per-request approach means Turn 3 protection doesn't work — each message is a fresh session with no memory. This is a known gap. The planned fix is IP-based session inference: requests from the same source IP within a time window share a session.

---

## 7. Multi-Format LLM Support

Phase 1 only handles OpenAI's `/v1/chat/completions` format. The other major formats:

| Provider | Endpoint | Request field | Response field |
|---|---|---|---|
| OpenAI | `/v1/chat/completions` | `messages[].content` | `choices[].message.content` |
| Anthropic | `/v1/messages` | `messages[].content` (array of blocks) | `content[].text` |
| Google Gemini | `/v1beta/models/{model}:generateContent` | `contents[].parts[].text` | `candidates[].content.parts[].text` |
| Cohere | `/v2/chat` | `messages[].content` | `message.content[].text` |
| Ollama | `/api/chat` | `messages[].content` | `message.content` (streaming: `message.content` per line) |

All formats: the masking engine is format-agnostic (it works on strings). The format-specific work is:
1. Extract all text fields from the request
2. Mask each one
3. Forward to the real endpoint
4. Extract text fields from the response
5. Unmask each one

The MITM proxy (Phase 2) will intercept traffic to each provider's real domain, so it needs a handler per format. The local proxy (Phase 1) only needs OpenAI format because it's an OpenAI-compatible endpoint — tools that speak non-OpenAI formats won't point at it.

---

## 8. Platform-Specific Traffic Interception

### macOS — pf (Packet Filter)

macOS's built-in firewall. Configured via `/etc/pf.conf` or anchor files in `/etc/pf.anchors/`.

```
# Redirect LLM traffic to local MITM proxy
rdr pass on en0 proto tcp to <llm_hosts> port 443 -> 127.0.0.1 port 47474
rdr pass on lo0 proto tcp to <llm_hosts> port 443 -> 127.0.0.1 port 47474
```

`pf` rules are loaded with `pfctl -f /etc/pf.conf`. Requires `sudo`. On macOS 13+ (Ventura), pf is preloaded but disabled by default — enable with `pfctl -e`.

**Scoped redirect:** Rather than redirecting all port 443 traffic (which would be a VPN), aivion-mask only redirects to the specific LLM hostnames. This is done via a `pf` table:

```
table <llm_hosts> { api.openai.com, api.anthropic.com, ... }
rdr pass proto tcp to <llm_hosts> port 443 -> 127.0.0.1 port 47474
```

The proxy receives the connection, reads the SNI hostname from the TLS ClientHello to identify which domain is being targeted, and uses that to generate the correct per-domain certificate.

### Linux — iptables / nftables

```bash
# iptables (legacy, still dominant)
iptables -t nat -A OUTPUT -p tcp --dport 443 -d api.openai.com -j REDIRECT --to-port 47474

# nftables (modern)
nft add rule ip nat OUTPUT tcp dport 443 ip daddr { 1.2.3.4, 5.6.7.8 } redirect to :47474
```

iptables works on IPs, not hostnames. The daemon must resolve LLM hostnames to IPs at startup and keep the table updated (LLM providers use CDNs with rotating IPs). A background task re-resolves every 5 minutes and updates the table.

### Windows — WFP (Windows Filtering Platform)

WFP is the Windows kernel-level network filter framework. The user-space API is complex; the practical approach is using `netsh` to add a port proxy:

```
netsh interface portproxy add v4tov4 listenport=443 connectaddress=127.0.0.1 connectport=47474
```

`netsh portproxy` only works for TCP and doesn't support hostname filtering — it redirects all 443 traffic. This means the MITM proxy must handle non-LLM traffic gracefully (pass it through without interception). An allowlist in config controls which SNI hostnames get masked vs. passed through.

---

## 9. TLS MITM — How Certificates Work

When a browser (or LLM client) connects to `api.openai.com`:

1. TCP connection established
2. TLS handshake: client sends `ClientHello` with SNI = `api.openai.com`
3. Server presents a certificate for `api.openai.com`
4. Client verifies: is this cert signed by a trusted CA?

In normal operation, the cert is signed by a public CA (DigiCert, Let's Encrypt). The OS ships with a bundle of trusted CA certificates.

In MITM mode:
1. The MITM proxy intercepts the TCP connection
2. It reads the SNI from the `ClientHello` without completing the TLS handshake
3. It generates a new certificate for `api.openai.com`, signed by the local CA
4. It completes the TLS handshake with the client using the fake cert
5. Simultaneously, it opens a new TLS connection to the real `api.openai.com`
6. All traffic flows through the proxy: client ↔ proxy (fake cert) ↔ real server (real cert)

The client trusts the fake cert because the local CA is in the OS trust store (added during setup). From the client's perspective, the connection is secure — it just doesn't know the CA is local.

### mitmproxy as the engine

[mitmproxy](https://mitmproxy.org/) is a mature Python library that handles all of this:
- TLS interception and certificate generation
- Per-domain cert caching
- Non-LLM traffic passthrough
- Flow API for reading/modifying request bodies

aivion-mask uses mitmproxy as a library (not the CLI tool). The masking engine plugs in as a mitmproxy addon:

```python
class MaskAddon:
    async def request(self, flow: mitmproxy.http.HTTPFlow):
        if flow.request.host in INTERCEPT_DOMAINS:
            body = json.loads(flow.request.content)
            # mask body messages
            flow.request.content = json.dumps(masked_body).encode()

    async def response(self, flow: mitmproxy.http.HTTPFlow):
        if flow.request.host in INTERCEPT_DOMAINS:
            body = json.loads(flow.response.content)
            # unmask response content
            flow.response.content = json.dumps(unmasked_body).encode()
```

### Certificate caching

Generating a new certificate for each domain is CPU-intensive (~5ms). mitmproxy caches generated certs in memory, so after the first request to `api.openai.com`, subsequent connections use the cached cert. The cache has no impact on security — the cert is still signed by the local CA and still only works for that specific domain.

---

## 10. Performance Research

### Regex scanning

32 compiled regex patterns on a 4KB message (about 1000 tokens):

| Approach | Time |
|---|---|
| Sync, main thread | ~0.3ms |
| Thread pool (`run_in_executor`) | ~0.3ms CPU + 0.1ms overhead |

For a typical 200-token message (~800 bytes), scanning is ~0.1ms. The thread pool approach is used to keep the asyncio event loop unblocked for concurrent requests — not because scanning is slow.

### SQLite write throughput

SQLite in WAL mode supports:
- ~10,000 writes/sec on modern SSD
- Multiple concurrent readers with no blocking
- One writer at a time (WAL buffer), but writes complete without waiting for readers

For the sidecar use case, writes happen once per new secret per session. A typical chat session might generate 5–10 DB writes total. WAL mode is overkill for this workload but costs nothing and enables the multi-worker uvicorn setup.

### aiosqlite overhead

aiosqlite wraps sqlite3 in a background thread and exposes an async interface. Each `await conn.execute()` incurs ~0.1ms of asyncio scheduling overhead on top of the SQLite operation itself.

For the sidecar, this is acceptable — DB calls are infrequent (only when new secrets are detected) and the overhead is dwarfed by LLM latency.

### Multi-worker concurrency

Two uvicorn workers means two OS processes, each with their own Python interpreter, asyncio event loop, aiosqlite connection, and thread pool. There is no shared memory between workers — they communicate only through the shared SQLite file.

For the current workload (a handful of concurrent LLM sessions per developer machine), two workers is sufficient headroom. The ceiling is the SQLite write serialization — one writer at a time — but since writes are infrequent, contention is negligible.

---

## 11. Prior Art

| Tool | Approach | Gap |
|---|---|---|
| **Zscaler / Netskope** | Network-level MITM for DLP | Enterprise-only, cloud-dependent, not open source |
| **mitmproxy** | General-purpose MITM proxy | No LLM-specific masking, no session model |
| **Presidio** (Microsoft) | PII detection and anonymization | No LLM proxy, no session model, NER-only (no structured credential patterns) |
| **Nightfall AI** | Cloud-based DLP API | Data leaves the machine before being scanned — defeats the purpose |
| **Detect-Secrets** (Yelp) | Git pre-commit hook for secrets | Scan-only, no real-time interception, no LLM integration |
| **Vault** (HashiCorp) | Secret management, dynamic secrets | Prevents secret creation, doesn't protect existing secrets at LLM send time |
| **Continue.dev privacy mode** | Don't send code to LLM | Binary — blocks everything, not selective |

None of the existing tools combine: (1) real-time interception, (2) session-aware pre-redaction, (3) response unmasking, (4) local-only operation, and (5) zero per-app configuration.

---

## 12. Open Questions

**Q: What about multimodal inputs (images)?**
Images sent to LLMs can contain secrets (screenshots of terminals, error messages). The current pipeline only masks text. OCR on images before sending is technically feasible (Tesseract, Apple Vision Framework) but adds significant latency and complexity. Out of scope for now.

**Q: What about tool calls / function calling?**
LLMs can generate structured tool call payloads (`{"function": "run_query", "args": {"connection": "postgresql://..."}}`). The current unmasking step only looks at `choices[].message.content`. If a token like `__DB1__` appears in a function call argument, it won't be unmasked in the response. Needs a recursive unmask pass over all string fields in the response body.

**Q: What about the LLM seeing the token patterns themselves?**
If the LLM's training data included `__DB1__`-style tokens, it might try to complete or repeat them. In practice, double-underscore identifiers appear constantly in Python code in training data — the LLM treats them as identifiers, not special directives. This has not been observed as a problem in testing.

**Q: What if two different secrets get the same token?**
The session model uses `INSERT OR REPLACE` on `(session_id, token)` as the primary key. Two different secrets always get different tokens because `next_index()` increments per abbreviation. The only collision risk is if a session TTL expires, a new session starts with the same ID, and `__DB1__` gets assigned to a different value. The session ID is a UUID — collision probability is negligible.

**Q: Can the proxy handle non-JSON LLM formats?**
Some endpoints return newline-delimited JSON (ndjson) or plain text. The current proxy assumes JSON request/response bodies. Non-JSON formats would be passed through unmasked. This is acceptable for Phase 1 (OpenAI-compatible only) but must be addressed in Phase 2 when all providers are intercepted.
