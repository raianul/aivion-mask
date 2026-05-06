# aivion-mask

Local-first PII masking layer for LLM applications. Masks sensitive data before it reaches any LLM; restores originals in the response.

## Repository Structure

| Path | What it is | Status |
|---|---|---|
| `core/recognizers/` | Shared regex + NER recognizer patterns | scaffold |
| `extension/vscode/` | VS Code extension (clipboard guard → proxy → deep integration) | scaffold |
| `extension/browser/` | Chrome/Firefox extension for AI chat UIs | scaffold |
| `sdk/python/` | `pip install aivion-mask` | scaffold |
| `sdk/typescript/` | `npm install @aivion/mask` | scaffold |
| `doc/platform/` | Product plans per platform | docs only |

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

See `doc/platform/` for detailed per-platform specs.

- `doc/platform/PLAN.md` — core mask/unmask API service
- `doc/platform/VS_CODE.md` — VS Code extension (Phase 0 = clipboard guard, no sidecar)
- `doc/platform/BROWSER-EXTENSION.md` — browser extension
- `doc/platform/MOBILE.md` — mobile

Current state: all implementation directories are scaffold only. Phase 0 (VS Code clipboard guard) is the first deliverable.
