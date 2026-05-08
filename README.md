# aivion-mask

A local-first PII masking layer for LLM applications.

Masks sensitive data before it reaches any LLM. Restores originals in the response. Session-aware, streaming-safe, no server required for local paths.

```
Your text: "Sarah Johnson's SSN is 219-09-9999"
                        ↓
               aivion-mask (local)
                        ↓
  To LLM:   "__P1__'s SSN is __P2__"
                        ↓
               Any LLM (OpenAI / Claude / Gemini / ...)
                        ↓
  Restored: "I've updated Sarah Johnson's record, SSN 219-09-9999 is verified"
```

No LLM calls inside the masking layer. Detection runs on local NER (spaCy / ONNX). Works fully air-gapped.

---

## What's in this repo (open source)

| Path | What it is |
|---|---|
| `extension/vscode/` | VS Code extension — masks secrets before they reach AI coding assistants |
| `extension/browser/` | Chrome/Firefox extension — masks PII in ChatGPT, Claude, Gemini |
| `sdk/python/` | Python SDK — `pip install aivion-mask` |
| `sdk/typescript/` | TypeScript SDK — `npm install @aivion/mask` |
| `core/` | Shared masking logic — token generation, session model, recognizers |

The server-side components (Valkey session store, audit trail, policy management, enterprise admin) are part of the hosted service.

---

## How It Works

### Token format

```
__P1__   __P2__   __P3__  ...
```

- Double underscore delimiters — unambiguous in any text
- Numbered per-session — same entity always gets the same token within a conversation
- 5–7 chars — streaming-safe, almost never splits across SSE chunks
- Display values (`[Name]`, `[Email]`) shown to end users during streaming

### Session model

```
session_id: abc123
  ├── __P1__  →  Sarah Johnson
  ├── __P2__  →  219-09-9999
  └── __P3__  →  sarah.j@company.com
```

Same `session_id` across turns prevents the "turn 3 leak" — an entity mentioned in turn 1 reappearing unmasked later.

---

## VS Code Extension

Protects secrets before they reach Cursor, Continue, GitHub Copilot, or any AI coding assistant.

**Phase 0 (shipped)** — Clipboard guard. Intercepts clipboard on copy, replaces detected secrets with `[REDACTED:TYPE]` before you paste. 40 credential patterns. No server, no config.

```
Install: ext install raianul.aivion-mask-vscode
```

**Phase 1 (shipped)** — Proxy mode. Local OpenAI-compatible server at `http://localhost:47474/v1/chat/completions`. Session tokens (`__P1__`, `__P2__`) replace PII end-to-end with full restore in the response.

**Phase 2 (planned)** — Deep integration. Live scan of open files, inline decorations, pre-commit hook.

[Full plan →](docs/dev-tool/VS_CODE.md)

---

## Claude Code & Anthropic Tools

The sidecar speaks Anthropic's native `/v1/messages` wire format. Point any Claude-using tool at `http://localhost:47474` and every prompt is masked before it reaches `api.anthropic.com`. Responses are unmasked before they reach you.

**Start the sidecar:**

```bash
cd sidecar && pip install -e ".[dev]"
aivion-mask-sidecar          # listens on :47474
```

**Per-tool setup:**

| Tool | How |
|---|---|
| **Claude Code CLI** | `export ANTHROPIC_BASE_URL=http://localhost:47474` in shell rc |
| **Claude Code in VS Code** | Aivion VS Code extension sets `terminal.integrated.env.osx.ANTHROPIC_BASE_URL` automatically |
| **Anthropic Python SDK** | `Anthropic(base_url="http://localhost:47474")` or set `ANTHROPIC_BASE_URL` |
| **Anthropic TypeScript SDK** | `new Anthropic({ baseURL: 'http://localhost:47474' })` or set `ANTHROPIC_BASE_URL` |
| **Continue.dev** | Aivion VS Code extension rewrites `apiBase` in `~/.continue/config.json` |
| **aider** | `export ANTHROPIC_API_BASE=http://localhost:47474` (litellm convention) |
| **llm + llm-anthropic** | `export ANTHROPIC_API_BASE=http://localhost:47474` |
| **OpenCode** | Set `ANTHROPIC_BASE_URL` in OpenCode config or env |

Both OAuth (subscription) and API key auth pass through unchanged. The proxy never stores credentials.

---

## Browser Extension

Masks PII in ChatGPT, Claude, Gemini, Grok, and other AI chat interfaces. Full round-trip: masks on submit, restores originals in the response. Local ONNX NER, IndexedDB session store.

[Full plan →](docs/dev-tool/BROWSER-EXTENSION.md)

---

## Python SDK

```python
from aivion_mask import MaskClient

client = MaskClient(api_key="sk-mask-...")  # or local mode

result = await client.mask(
    text="Sarah Johnson's SSN is 219-09-9999",
    session_id="abc123",
    policy="hr"
)

llm_response = await your_llm(result.text)

restored = await client.unmask(text=llm_response, session_id="abc123")
print(restored.text)
# "I've updated Sarah Johnson's record, SSN 219-09-9999 is verified"
```

---

## TypeScript SDK

```typescript
import { MaskClient } from '@aivion/mask'

const client = new MaskClient({ apiKey: 'sk-mask-...' })

const { text, sessionId } = await client.mask({
  text: "Sarah Johnson's SSN is 219-09-9999",
  policy: 'hr'
})

const llmResponse = await yourLLM(text)
const restored = await client.unmask({ text: llmResponse, sessionId })
```

---

## Supported Entity Types

**PII:** PERSON, EMAIL_ADDRESS, PHONE_NUMBER, LOCATION, DATE_TIME, URL, IP_ADDRESS

**Financial:** CREDIT_CARD, IBAN_CODE, US_BANK_NUMBER, CRYPTO

**Government ID:** US_SSN, US_PASSPORT, US_DRIVER_LICENSE

**Credentials:** AWS_ACCESS_KEY, AZURE_KEY, GITHUB_TOKEN, DATABASE_URL, GENERIC_API_KEY

**Custom:** Regex-based recognizers via config

---

## Local vs Server

| | Local mode | Server mode |
|---|---|---|
| Session store | SQLite / IndexedDB | Valkey |
| NER | spaCy / ONNX | Presidio |
| Audit trail | Local log | PostgreSQL |
| Policy management | `.aivion-mask.json` | API |
| Server required | No | Yes |

Local mode is the default for the VS Code and browser extensions. Server mode is for applications built on top of LLMs that need centralized audit and org-wide policies.

---

## Roadmap

- [x] Core masking engine + session model + 32 credential patterns
- [x] VS Code extension — clipboard guard (Phase 0) — [install](https://marketplace.visualstudio.com/items?itemName=raianul.aivion-mask-vscode)
- [x] Local proxy sidecar (`localhost:47474`) — OpenAI-compatible, async DB, streaming (Phase 1)
- [x] Anthropic `/v1/messages` support + Claude Code integration (v1.5)
- [ ] VS Code extension — deep integration + live scan (Phase 2)
- [ ] Browser extension — Chrome/Firefox
- [ ] Python SDK
- [ ] TypeScript SDK

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
