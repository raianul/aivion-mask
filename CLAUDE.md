# aivion-mask

Local-first PII masking layer for LLM applications. Masks sensitive data before it reaches any LLM; restores originals in the response.

## Repository Structure

| Path | What it is | Status |
|---|---|---|
| `core/recognizers/` | Shared regex + NER recognizer patterns | shared credential pattern library |
| `sidecar/` | Local FastAPI proxy — masks PII before LLM, restores in response | Phase 1 |
| `extension/vscode/` | VS Code extension (clipboard guard → proxy → deep integration) | Phase 0 shipped (v0.1.1) |
| `extension/browser/` | Chrome/Firefox extension for AI chat UIs | scaffold |
| `sdk/python/` | `pip install aivion-mask` | scaffold |
| `sdk/typescript/` | `npm install @aivion/mask` | scaffold |
| `docs/dev-tool/` | Developer-tool roadmap (VS Code, browser extension, research) | docs only |
| `docs/api/` | Scrubber-server SaaS API roadmap | docs only |
| `docs/LLM/` | Per-provider coverage plans (Claude, OpenAI, ...) | docs only |
| `docs/archived/` | Researched but not building (system tray, mobile) | docs only |

## Code Style

- **Python:** `ruff` — config in `pyproject.toml`
- **TypeScript:** ESLint + Prettier — config in each package
- **`core/`:** zero external runtime dependencies — must work offline

## Development

```bash
# Python (sidecar / SDK)
python -m venv .venv && source .venv/bin/activate
pip install -e sdk/python/         # when implemented

# TypeScript (VS Code extension / browser extension / TS SDK)
cd extension/vscode && npm install && npm run compile
cd extension/browser && npm install && npm run build
cd sdk/typescript && npm install && npm run build
```

## VS Code Extension Commands

```bash
cd extension/vscode
npm run compile                                    # tsc
npm run watch                                      # tsc --watch
npm run lint                                       # eslint
npm test                                           # mocha via @vscode/test-electron
npm run package                                    # vsce package → .vsix
npx vsce publish --pat <token>                     # publish (publisher: raianul)
npx vsce publish patch --pat <token>               # bump patch + publish
```

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
- **Token format (Phase 1+):** `__P1__`, `__P2__` — short (5–7 chars), streaming-safe, double-underscore delimiters unambiguous in any text. Phase 0 uses `[REDACTED:TYPE]` (e.g. `[REDACTED:DATABASE_URL_POSTGRES]`) — regex only, no session model.
- **Session model:** same `session_id` across turns prevents "turn 3 leak". Pre-redact known entities before running NER on subsequent turns.
- **Display values ≠ tokens:** `__P1__` goes to the LLM; `[Name]` is shown to end users during streaming. Two separate concepts.

## Recognizers (`core/recognizers/`)

When adding a new pattern:
- Include at least one positive and one negative test case
- Use entropy filtering to reduce false positives
- Document the pattern source
- Add entry to `core/recognizers/README.md`

## Build Phases

Two parallel product tracks share the same masking engine:

**Developer tool** (this repo's primary focus)
- `docs/dev-tool/VS_CODE.md` — VS Code extension (Phase 0 shipped, Phase 1 sidecar shipped, Phase 2 deep integration next)
- `docs/dev-tool/BROWSER-EXTENSION.md` — Chrome/Firefox extension for ChatGPT, Claude.ai, Gemini, etc.
- `docs/dev-tool/RESEARCH.md` — interception approaches, token format design, streaming, prior art

**Per-provider coverage** (applies to both tracks)
- `docs/LLM/CLAUDE.md` — Anthropic provider plan (auth pass-through, `/v1/messages`, SSE handler)
- `docs/LLM/OPENAI.md`, `GEMINI.md`, ... (next)

**Scrubber-server SaaS API** (separate product, future track)
- `docs/api/PLAN.md` — multi-tenant `/v1/mask` + `/v1/unmask` API for app teams to integrate

**Archived** (researched, not on the roadmap)
- `docs/archived/MASK.md` — system-tray network-MITM (cert pinning + CA-key-storage make it not worth building)
- `docs/archived/MOBILE.md` — mobile keyboards / share extensions (out of scope for v1–v2)

Current state: Phase 1 (sidecar + proxy + VS Code integration) complete. Phase 0 clipboard guard live at `raianul.aivion-mask-vscode` on the marketplace. Browser extension and SDKs are scaffold.

## Gotchas

- **Test fixture credentials** trigger GitHub secret scanning push protection. Use split string concatenation in tests: `'xoxb-' + '123...'` not `'xoxb-123...'`.
- **`.vscodeignore`** — wildcard negation after `!out/**` does not re-exclude subdirectories in vsce. Explicitly list every file to include instead of relying on `!out/**` + `out/test/**`.
- **Publisher ID** is `raianul` (personal account, marketplace.visualstudio.com/manage/publishers/raianul). Not `aivionlabs`.
