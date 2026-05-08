# aivion-mask

Local-first PII masking layer for LLM applications. Masks sensitive data before it reaches any LLM; restores originals in the response.

## Repository Structure

| Path | What it is | Status |
|---|---|---|
| `core/recognizers/` | Shared regex + NER recognizer patterns | shared credential pattern library |
| `sidecar/` | Local FastAPI proxy — masks PII before LLM, restores in response | active |
| `extension/browser/` | Chrome/Firefox extension for AI chat UIs | scaffold |
| `sdk/python/` | `pip install aivion-mask` | scaffold |
| `sdk/typescript/` | `npm install @aivion/mask` | scaffold |
| `docs/dev-tool/` | Developer-tool roadmap (browser extension, research) | docs only |
| `docs/api/` | Scrubber-server SaaS API roadmap | docs only |
| `docs/LLM/` | Per-provider coverage plans (Claude, OpenAI, ...) | docs only |
| `docs/archived/` | Researched but not building (system tray, mobile) | docs only |

## Code Style

- **Python:** `ruff` — config in `pyproject.toml`
- **`core/`:** zero external runtime dependencies — must work offline

## Sidecar Commands

```bash
cd sidecar
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # install + dev deps
pytest -v                        # run all sidecar tests
aivion-mask-sidecar              # start sidecar on :47474
```

## Key Design Invariants

- **No LLM calls inside the masking layer.** Detection is pure Presidio/spaCy + regex.
- **Token format:** `__P1__`, `__P2__` — short (5–7 chars), streaming-safe, double-underscore delimiters unambiguous in any text.
- **Session model:** same `session_id` across turns prevents "turn 3 leak". Pre-redact known entities before running NER on subsequent turns.
- **Display values ≠ tokens:** `__P1__` goes to the LLM; `[Name]` is shown to end users during streaming. Two separate concepts.

## Recognizers (`core/recognizers/`)

When adding a new pattern:
- Include at least one positive and one negative test case
- Use entropy filtering to reduce false positives
- Document the pattern source
- Add entry to `core/recognizers/README.md`

## Build Phases

**Sidecar (primary focus)**
- `docs/LLM/CLAUDE.md` — Anthropic provider plan (auth pass-through, `/v1/messages`, SSE handler) — shipped v0.2.0
- `docs/LLM/OPENAI.md`, `GEMINI.md`, ... (next providers)

**Browser extension**
- `docs/dev-tool/BROWSER-EXTENSION.md` — Chrome/Firefox extension for ChatGPT, Claude.ai, Gemini, etc.
- `docs/dev-tool/RESEARCH.md` — interception approaches, token format design, streaming, prior art

**Scrubber-server SaaS API** (separate product, future track)
- `docs/api/PLAN.md` — multi-tenant `/v1/mask` + `/v1/unmask` API for app teams to integrate

**Archived** (researched, not on the roadmap)
- `docs/archived/MASK.md` — system-tray network-MITM (cert pinning + CA-key-storage make it not worth building)
- `docs/archived/MOBILE.md` — mobile keyboards / share extensions (out of scope for v1–v2)

## Gotchas

- **Test fixture credentials** trigger GitHub secret scanning push protection. Use split string concatenation in tests: `'xoxb-' + '123...'` not `'xoxb-123...'`.
