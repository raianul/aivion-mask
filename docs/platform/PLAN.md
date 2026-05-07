# Sheru Mask — Product Plan

> Name TBD. Working name: `sheru-mask`

---

## 1. What It Is

Not a guardrail. Not a DLP filter.

A **PII Data Plane for LLM applications** — the layer that sits between any app and any LLM, making PII handling lossless, auditable, and policy-driven.

A guardrail answers: *"is this safe to send?"*
Sheru Mask answers: *"who said what, in which context, under which policy — and can I prove it?"*

### Core insight
Every other product in this space treats PII as a security problem (block or allow). We treat it as an **identity problem** — the original values must be preserved, restored, and auditable with zero ambiguity. That requires statefulness, numbered tokens, and session memory. No competitor has all three.

---

## 2. The Flow

```
Your App
    │
    │  "Sarah Johnson's SSN is 219-09-9999"
    ▼
┌─────────────────────────────┐
│         /v1/mask            │
│                             │
│  Sarah Johnson  →  __P1__   │
│  219-09-9999   →  __P2__    │
│  session_id    →  abc123    │
└─────────────────────────────┘
    │
    │  "__P1__'s SSN is __P2__"
    ▼
  Any LLM (OpenAI / Gemini / Claude / Bedrock / ...)
    │
    │  "I've updated __P1__'s record, SSN __P2__ is verified"
    ▼
┌─────────────────────────────┐
│         /v1/unmask          │
│                             │
│  __P1__  →  Sarah Johnson   │
│  __P2__  →  219-09-9999     │
│  session_id: abc123         │
└─────────────────────────────┘
    │
    │  "I've updated Sarah Johnson's record, SSN 219-09-9999 is verified"
    ▼
Your App
```

**No LLM calls inside the service.** Detection runs entirely on local Presidio (spaCy NER).
No external APIs, no cost per detection, works fully air-gapped.

---

## 3. Token Format

```
__P1__   __P2__   __P3__  ...
```

- Double underscore delimiters — unambiguous in any text, cannot accidentally match real words
- Numbered per-session — same entity always gets the same token within a conversation
- Short (5–7 chars) — almost never splits across SSE streaming chunks
- Display values (`[Name]`, `[Email]`) shown to end users during streaming, not raw tokens

**Why not NoPII-style `[PERSON: VAULT_T8bd4avHCnX4vmFwr0nA]`:**
- 30+ char tokens split across streaming chunks constantly — forces full response buffering
- Vault stored on their servers — HIPAA/GDPR liability for customers
- No per-role policies

---

## 4. Streaming Support

True real-time streaming — no buffering the full response.

```
chunk 1: "I've updated [Name]..."     ← display_value shown live to user
chunk 2: "SSN [SSN] is verified"      ← display_value shown live to user
                  ↓
         full text assembled
                  ↓
              /v1/unmask
                  ↓
"I've updated Sarah Johnson's record, SSN 219-09-9999 is verified"
```

- `safe_flush_point` lookahead buffer catches the rare case where `__P1__` splits across chunks
- Display values give users readable placeholders during streaming
- Full originals restored via `/v1/unmask` after stream completes
- No competitor in the market does this correctly

---

## 5. Session Model

Session ID is the key to everything.

```
session_id: abc123
  ├── __P1__  →  Sarah Johnson
  ├── __P2__  →  219-09-9999
  └── __P3__  →  sarah.j@company.com
```

- New conversation → new `session_id`
- Turn 2, 3, 4 of the same conversation → reuse same `session_id`
- Presidio pre-redacts known entities on subsequent turns before running detection
- Prevents "3rd message leak" — entity mentioned in turn 1 reappearing unmasked in turn 3
- Session TTL configurable per tenant (default 24h) — mapping expires automatically
- Stored in Valkey/Redis — persistent across service restarts

---

## 6. Policy System

Per-role entity configuration managed via API — no config file redeploys.

```json
// HR policy
{
  "policy": "hr",
  "entities": ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "US_SSN", "DATE_TIME", "LOCATION"]
}

// Finance policy
{
  "policy": "finance",
  "entities": ["CREDIT_CARD", "IBAN_CODE", "US_BANK_NUMBER", "US_SSN", "PERSON", "EMAIL_ADDRESS"]
}

// Developer policy
{
  "policy": "developer",
  "entities": ["AWS_ACCESS_KEY", "AZURE_KEY", "GITHUB_TOKEN"]
}
```

- Platform manages global policies via admin API
- Per-org policy overrides supported
- Custom entity types via regex or NER recognizer JSON
- Confidence score thresholds configurable per entity type

---

## 7. Supported Entity Types

**PII**
PERSON, EMAIL_ADDRESS, PHONE_NUMBER, LOCATION, DATE_TIME, URL, IP_ADDRESS

**Financial**
CREDIT_CARD, IBAN_CODE, US_BANK_NUMBER, US_ITIN, CRYPTO

**Government ID**
US_SSN, US_PASSPORT, US_DRIVER_LICENSE, UK_NHS, AU_TFN

**Healthcare / PHI**
MEDICAL_RECORD_NUMBER, US_NPI (via custom recognizer)

**Credentials**
AWS_ACCESS_KEY, AZURE_KEY, GITHUB_TOKEN (via custom recognizer)

**Custom**
Regex-based and NER-based recognizers defined via API per org

---

## 8. Audit Trail

Every mask/unmask event logged with full context. Logs stay in your infrastructure.

```json
{
  "event": "mask",
  "session_id": "abc123",
  "user_id": "user_xyz",
  "org_id": "org_abc",
  "policy": "hr",
  "entities_detected": [
    { "type": "PERSON", "token": "__P1__", "score": 0.95 },
    { "type": "US_SSN",  "token": "__P2__", "score": 0.99 }
  ],
  "timestamp": "2026-05-06T10:23:11Z"
}
```

- Original values **never** logged — only entity type + token
- Queryable: "all CREDIT_CARD detections for org X in the last 30 days"
- Compliance-ready: HIPAA, GDPR, SOC2
- Logs never leave your infrastructure

---

## 9. API Design

### POST /v1/mask
```json
// Request
{
  "text": "Sarah Johnson's SSN is 219-09-9999",
  "session_id": "abc123",
  "policy": "hr"
}

// Response
{
  "text": "__P1__'s SSN is __P2__",
  "session_id": "abc123",
  "entities": [
    { "type": "PERSON", "token": "__P1__", "display_value": "[Name]", "score": 0.95 },
    { "type": "US_SSN",  "token": "__P2__", "display_value": "[SSN]",  "score": 0.99 }
  ]
}
```

### POST /v1/unmask
```json
// Request
{
  "text": "I've updated __P1__'s record, SSN __P2__ is verified",
  "session_id": "abc123"
}

// Response
{
  "text": "I've updated Sarah Johnson's record, SSN 219-09-9999 is verified"
}
```

### GET /v1/session/{session_id}
```json
// Response — metadata only, no raw PII values
{
  "session_id": "abc123",
  "created_at": "2026-05-06T10:23:11Z",
  "expires_at": "2026-05-07T10:23:11Z",
  "entity_count": 3,
  "policy": "hr"
}
```

### DELETE /v1/session/{session_id}
Immediately wipe session mapping — GDPR right to erasure (Art. 17)

### POST /v1/policies
Create or update a named policy for the org

### GET /v1/policies
List all policies for the calling org

### GET /v1/audit
Paginated audit log — filter by org, user, entity_type, date range

### GET /v1/health
Liveness check

---

## 10. Auth

API key per tenant — replaces current Clerk JWT dependency.

```
Authorization: Bearer sk-mask-xxxxxxxxxxxxxx
```

- Keys scoped to org — all calls under a key share org-level policies and audit trail
- Key rotation supported
- Service keys for backend-to-backend calls (workflow engine, workers, queues)
- Usage tracked per key for billing metering

---

## 11. SDK

### Python
```python
from sheru_mask import MaskClient

client = MaskClient(
    base_url="https://mask.aivionlabs.com",
    api_key="sk-mask-..."
)

# Step 1 — mask before LLM
result = await client.mask(
    text="Sarah Johnson's SSN is 219-09-9999",
    session_id="abc123",
    policy="hr"
)

# Step 2 — call any LLM with masked text (your code, unchanged)
llm_response = await your_llm(result.text)

# Step 3 — unmask after LLM
restored = await client.unmask(
    text=llm_response,
    session_id="abc123"
)

print(restored.text)
# "I've updated Sarah Johnson's record, SSN 219-09-9999 is verified"
```

### TypeScript
```typescript
import { MaskClient } from '@aivion/mask'

const client = new MaskClient({
  baseUrl: 'https://mask.aivionlabs.com',
  apiKey: 'sk-mask-...'
})

const { text, sessionId } = await client.mask({
  text: "Sarah Johnson's SSN is 219-09-9999",
  policy: 'hr'
})

const llmResponse = await yourLLM(text)

const restored = await client.unmask({ text: llmResponse, sessionId })
```

---

## 12. Repository Structure

```
aivion-mask/
  core/
    recognizers/     Shared TypeScript credential patterns (VS Code + browser extension)
  sidecar/           Machine-level local service (Python)
    aivion_mask_sidecar/
      main.py        FastAPI app — port 47474
      masker.py      Presidio analyzer + anonymizer
      session.py     SQLite session store (TTL, CRUD)
      tokens.py      __P1__ token generation per session
      stream.py      SSE lookahead buffer for streaming unscrub
      proxy.py       Forward masked request to real LLM
      mcp.py         MCP manifest endpoint
      config.py      ~/.aivion-mask/config.toml loader
    pyproject.toml
  extension/
    vscode/          VS Code extension (Phase 0 shipped, Phase 1 in progress)
    browser/         Chrome/Firefox extension (scaffold)
  sdk/
    python/          pip install aivion-mask
    typescript/      npm install @aivion/mask
  docs/
    platform/        Per-platform specs (this directory)
  pyproject.toml
  CLAUDE.md
```

**Data directory (local machine, never synced):**
```
~/.aivion-mask/
  config.toml        apiBase, apiKey, port, session TTL
  sessions.db        SQLite — token maps with TTL
  sidecar.pid        PID file — prevents duplicate processes
  venv/              Python venv (auto-created on first install)
```

**No external services required.** Presidio runs embedded in the sidecar process (no separate containers needed for local use). Docker compose is provided for self-hosted team/enterprise deployments only.

---

## 13. Deployment Options

### Self-hosted (Docker)
```bash
docker compose up
# pii service     → :47474
# presidio-analyzer → :5002
# presidio-anonymizer → :5001
# valkey          → :6379
```

### Cloud SaaS
- `mask.aivionlabs.com`
- Multi-tenant, API key per org
- Usage metering for billing

### Air-gapped / Customer VPC
- Docker image pushed to customer's private registry
- Zero external network calls at runtime
- Full data residency guarantee — PII never leaves the customer's environment

---

## 14. Phases

### Phase 1 — Extract from sheru-platform
- [ ] New repo `sheru-mask`
- [ ] Replace Clerk JWT auth → API key auth
- [ ] Replace in-memory session store → Valkey with TTL
- [ ] Clean `/v1/mask` and `/v1/unmask` endpoints (rename from scrub/unscrub)
- [ ] Policy CRUD endpoints
- [ ] Docker compose (service + Presidio + Valkey)
- [ ] Update sheru-platform gateway to call new standalone service
- [ ] CLAUDE.md

### Phase 2 — Production Hardening
- [ ] Persistent audit trail (PostgreSQL)
- [ ] `GET /v1/audit` with filters
- [ ] `DELETE /v1/session/{id}` — GDPR right to erasure
- [ ] API key management (create, rotate, revoke)
- [ ] Usage metering per API key
- [ ] Rate limiting per key
- [ ] Multi-language support (Spanish, German)

### Phase 3 — SDK + Developer Experience
- [ ] Python SDK (`pip install sheru-mask`)
- [ ] TypeScript SDK (`npm install @aivion/mask`)
- [ ] OpenAPI spec + generated docs
- [ ] Integration guides (OpenAI, LiteLLM, LangChain, direct)
- [ ] Quickstart: working in under 5 minutes

### Phase 4 — Enterprise
- [ ] Admin dashboard (policy editor, audit viewer, usage graphs)
- [ ] Custom entity recognizers via API
- [ ] Confidence score thresholds per entity per policy
- [ ] SOC2 / HIPAA documentation
- [ ] SLA + support tiers
- [ ] SSO for admin dashboard

---

## 15. Competitive Position

| | NoPII | Protecto | Nightfall | Private AI | Sheru Mask |
|---|---|---|---|---|---|
| Bidirectional mask + restore | ✅ | ✅ | ❌ | ✅ | ✅ |
| True streaming | ❌ | ❌ | ✅ | ❌ | ✅ |
| Session-aware multi-turn | ✅ | ✅ | ❌ | ❌ | ✅ |
| Per-role policies | ❌ | ✅ | ❌ | ❌ | ✅ |
| Self-hostable | ❌ | ❌ | ❌ | ✅ | ✅ |
| Audit trail ownership | ❌ | ❌ | ❌ | ✅ | ✅ |
| Workflow / agent native | ❌ | ❌ | ❌ | ❌ | ✅ |
| No LLM dependency | ✅ | ✅ | ✅ | ✅ | ✅ |
| Developer-friendly entry price | ✅ $50/mo | ❌ enterprise | ❌ enterprise | ❌ $39k/yr | ✅ |

**The gap we fill:** true streaming + self-hostable + per-role policies. Nobody has all three.

---

## 16. Pricing Model

| Tier | Who | Price | Limits |
|---|---|---|---|
| **Developer** | Solo builders, evaluation | Free | 1M tokens/mo, 1 policy |
| **Startup** | Small teams | $99/mo | 50M tokens/mo, 5 policies, audit trail |
| **Business** | Growing SaaS | $499/mo | 500M tokens/mo, unlimited policies, full audit |
| **Enterprise** | Regulated industries | Custom | Self-hosted, SLA, compliance docs, custom entities |

Token = characters processed through mask + unmask combined.

---

## 17. Key Design Decisions

**No LLM calls inside the service.**
Detection is pure Presidio + spaCy. Local, fast, free, air-gappable. The service has no network dependencies beyond Valkey.

**Session store in Valkey, not in-memory.**
Survives restarts, supports horizontal scaling, TTL-based expiry for privacy compliance.

**Numbered tokens, not category-only.**
`__P1__` not `<PERSON>`. Unambiguous restoration even when the same entity type appears multiple times. This is the core technical differentiator.

**Short tokens for streaming safety.**
5–7 chars. SSE chunks are 4–8 chars. Long tokens (NoPII's 30+ char vault IDs) split across chunks and force full-response buffering.

**Display values separate from tokens.**
`__P1__` in the LLM request. `[Name]` shown to end users during streaming. Two separate concepts serving two separate needs.

**API key auth, not Clerk.**
Service must work for any caller — not just Aivion products. Clerk is a sheru-platform concern, not a PII service concern.

**Self-hostable as first-class deployment.**
Not an afterthought. Regulated industries will not send PII to a third-party SaaS. Air-gapped Docker image is the enterprise unlock.
