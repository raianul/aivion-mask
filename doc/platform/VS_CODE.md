# sheru-mask — VS Code Extension Plan

Local-first VS Code extension. Masks credentials, secrets, and sensitive code before it reaches any AI coding assistant (Continue, Cursor, GitHub Copilot). Runs as a local sidecar process. No server. PII never leaves the machine.

---

## 1. What It Does

```
Developer asks Cursor/Continue: 
  "help me debug this: postgresql://admin:s3cr3t@10.0.1.55:5432/prod_db"
           │
sheru-mask local sidecar intercepts
           │
Local NER (spaCy) + SQLite session store
           │
"help me debug this: postgresql://admin:__P1__@__P2__:5432/__P3__"
           │
Masked prompt sent to OpenAI / Anthropic / Gemini
           │
LLM responds with __P1__, __P2__, __P3__
           │
sheru-mask unscrubs locally
           │
Developer sees: "... postgresql://admin:s3cr3t@10.0.1.55:5432/prod_db ..."
```

Zero calls to sheru-mask servers. Local Python sidecar, SQLite session, spaCy NER.

---

## 2. Integration Modes

### Mode A — Clipboard Guard (zero setup, works everywhere)

Monitors the clipboard. When a copy event contains secrets, replaces clipboard contents before paste. Works with Copilot, any IDE chat window, any app.

Two sub-modes (configurable in settings):
- `warn` — show a notification: "2 secrets detected in clipboard"
- `block` — silently replace clipboard with masked text

No sidecar needed. No `apiBase` config. Ships in Phase 0.

### Mode B — Proxy (full round-trip, zero config change for Continue/MCP-aware tools)

sheru-mask exposes itself as an **MCP server**. Continue.dev and other MCP-aware tools discover it automatically — no manual `apiBase` change needed.

Also supports manual `apiBase` config for tools that don't support MCP:

```json
// Continue (~/.continue/config.json)
{
  "models": [{
    "title": "GPT-4o via sheru-mask",
    "provider": "openai",
    "model": "gpt-4o",
    "apiBase": "http://localhost:8003/v1/openai",
    "apiKey": "sk-mask-local"
  }]
}
```

```json
// Cursor (settings.json)
{
  "cursor.openaiApiBase": "http://localhost:8003/v1/openai"
}
```

The local server:
1. Receives the prompt
2. Runs NER → masks → stores session in SQLite
3. Forwards masked prompt to the real LLM (using the developer's own API key)
4. Receives LLM response
5. Unscrubs → returns to Cursor/Continue

Developer's real API key is passed through locally — never stored by sheru-mask.

### Mode C — VS Code Extension (deepest integration)

VS Code extension spawns the local sidecar automatically. Adds:
- Inline gutter annotations — highlights detected entities before sending
- Live scan on file open/change — proactively flags what would be masked
- Status bar: "3 entities masked" counter
- Command palette: `sheru-mask: Show session`, `sheru-mask: Clear session`
- Works even with Copilot (intercepts at the extension host level)

---

## 3. Local Architecture

```
VS Code Extension (TypeScript)
  ├── extension.ts          Activation, sidecar lifecycle manager
  ├── clipboard.ts          Clipboard monitor (Mode A — warn/block)
  ├── statusBar.ts          Entity counter in status bar
  ├── decorator.ts          Inline gutter highlights for detected entities
  ├── liveScanner.ts        On file open/change — proactive detection
  └── commands.ts           Show session, clear session, toggle on/off

Local Sidecar (Python — same binary as sheru-desktop)
  ├── main.py               FastAPI app — OpenAI-compatible proxy + MCP server
  ├── masker.py             Presidio analyzer + anonymizer
  ├── session.py            SQLite session store (TTL, CRUD)
  ├── deterministic.py      Workspace-level persistent token map (optional)
  ├── policy.py             Developer policy entity config
  ├── trainer.py            False-positive exclusion store
  └── proxy.py              Forward masked request to real LLM provider
```

The sidecar is the same Python binary used in sheru-desktop. Shared codebase, different entry point.

---

## 4. Developer Policy — Entity Set

The default entity set for IDE context focuses on secrets and internal infrastructure:

```json
{
  "policy": "developer",
  "entities": [
    "AWS_ACCESS_KEY",      // AKIA...
    "AZURE_KEY",           // Azure subscription/resource keys
    "GITHUB_TOKEN",        // ghp_, ghs_, github_pat_
    "GENERIC_API_KEY",     // Bearer tokens, API keys in headers
    "IP_ADDRESS",          // Private ranges: 10.x, 192.168.x, 172.16.x
    "URL",                 // Internal hostnames, service URLs
    "EMAIL_ADDRESS",       // Commit authors, internal contacts
    "PASSWORD",            // Passwords in connection strings
    "DATABASE_URL"         // Full connection strings (custom recognizer)
  ]
}
```

Custom recognizers configurable per project via `.sheru-mask.json` in the workspace root.

---

## 5. Session Model

```
Session = one VS Code workspace
  ├── session_id: derived from workspace path hash
  ├── __P1__ → s3cr3t
  ├── __P2__ → 10.0.1.55
  ├── __P3__ → prod_db
  └── expires: 8h after last activity (configurable)
```

- New workspace → new session
- Reopen same workspace → same session (SQLite persists in `~/.sheru-mask/sessions/`)
- Multi-turn: second prompt pre-redacts known entities before running NER
- Session cleared on: manual clear, TTL expiry, or workspace close (optional)

### Deterministic Mode (opt-in)

Workspace-level persistent token map — `John Smith` always maps to `__P1__` in this workspace across all sessions, not just within one conversation. Useful for long-running projects with repeated context.

Enable in `.sheru-mask.json`:
```json
{ "deterministic": true }
```

Stored separately from session map in `~/.sheru-mask/deterministic/{workspace_hash}.db`.

---

## 6. Per-Project Config

`.sheru-mask.json` in workspace root overrides global policy:

```json
{
  "policy": "developer",
  "deterministic": false,
  "extra_entities": ["DATABASE_URL"],
  "ignore_patterns": ["test_", "mock_", "fake_"],
  "session_ttl_hours": 4,
  "clipboard_mode": "block"
}
```

`ignore_patterns` — regex patterns that suppress masking (e.g. test fixtures with fake credentials).

---

## 7. False-Positive Trainer

Right-click any detected entity in the editor → "Not a secret — ignore this pattern". sheru-mask learns and stops flagging similar values.

Learned exclusions stored in `~/.sheru-mask/trainer.json`. Exportable and shareable across team via `.sheru-mask.json` committed to the repo.

---

## 8. Supported AI Coding Tools

| Tool | Integration | Mode |
|---|---|---|
| Continue | MCP discovery (auto) or `apiBase` | B |
| Cursor | Custom `openaiApiBase` in settings | B |
| GitHub Copilot | Extension host intercept | C only |
| Codeium | Custom endpoint config | B |
| Tabnine | Custom endpoint (Enterprise) | B |
| Any MCP-aware tool | MCP server auto-discovery | B |
| Any OpenAI-compatible tool | `apiBase` = `http://localhost:8003/v1/openai` | B |

---

## 9. Sidecar Lifecycle

The VS Code extension manages the sidecar process:

```
VS Code opens
  → Extension activates
  → Check: is sidecar running? (GET http://localhost:8003/health)
  → No → spawn sidecar process
  → Yes → attach to existing (sheru-desktop may already be running it)
  → Show status bar item: "sheru-mask: active"

VS Code closes
  → Extension deactivates
  → If extension started the sidecar → send SIGTERM
  → If sidecar was already running (sheru-desktop) → leave it running
```

If sheru-desktop is installed, the sidecar is already running — the VS Code extension just attaches. Single process, shared sessions.

---

## 10. Privacy Guarantee

- All NER runs in the local sidecar (spaCy, no ONNX needed — Python is available)
- SQLite session store at `~/.sheru-mask/sessions/` — never synced
- Real LLM API key passed through in-memory only, never written to disk
- No telemetry, no analytics (opt-in crash reporting only)
- Works fully offline (NER detection, session management) — only LLM forward requires network

---

## 11. Optional Server Connect (Enterprise / Team)

Teams can point the sidecar at a shared sheru-mask server for centralized audit:

```toml
# ~/.sheru-mask/config.toml
[server]
url = "https://mask.company.com"
api_key = "sk-mask-..."
mode = "server"   # "local" (default) or "server"
```

In server mode:
- Session store switches from SQLite → org Valkey
- Audit trail written to org PostgreSQL
- Policy pulled from org config (not local `.sheru-mask.json`)
- Team shares one session namespace (useful for pair programming / PR review flows)

---

## 12. Competitors

| | SecretShields | SecureAIFlow | OX Security | Cloak | Vibe Owl | sheru-mask |
|---|---|---|---|---|---|---|
| Category | Pre-paste masking | Cloud AI proxy | SAST / secret scan | Camera hiding | Secret scan + clipboard | Local AI proxy |
| Processing | Local (clipboard) | **Cloud (Germany)** | Cloud | Local (color only) | Local | Local |
| Data leaves device | No | **Yes** | Yes | No | No | No |
| Detection | 38 regex patterns | Regex + MiniLM | Heuristic | None (color) | Heuristic | NER + regex |
| Round-trip unmask | No | Yes | No | No | No | Yes |
| Session / multi-turn | No | Yes | No | No | No | Yes |
| Works with Copilot | Yes (clipboard) | Yes | No | Yes (visual only) | Yes (clipboard) | Mode C only |
| Account required | No | Yes | Yes | No | No | No |
| Pricing | Free / MIT | €0–€45+/seat | Free (SaaS) | Free / MIT | Free + Pro | TBD |
| Open source | MIT | Closed | Closed | MIT | Closed | TBD |

**The gap we fill:** local + full round-trip + session-aware + no account. Nobody has all four.

**Features worth adapting:**
- **SecretShields** — clipboard mode as Phase 0 (works everywhere, zero setup)
- **SecureAIFlow** — deterministic pseudonymization option, published F1 benchmarks
- **Vibe Owl** — false-positive trainer, clipboard warn/block modes, live scan on file open
- **OX Security** — MCP server exposure for auto-discovery by Continue and other tools
- **Cloak** — live editor decorations showing what would be masked

---

## 13. Monetization

> **Placeholder — to be decided.**
>
> Questions to answer:
> - Free tier limits (e.g. N masks/day, developer policy only)?
> - Paid tier unlocks (e.g. all policies, session history panel, enterprise server connect)?
> - One-time purchase vs subscription?
> - Relationship to API product pricing tiers?

---

## 14. Phases

### Phase 0 — Clipboard Guard (1 week, works everywhere)
- [ ] Clipboard monitor (TypeScript, no sidecar needed)
- [ ] Warn mode: notification when secrets detected
- [ ] Block mode: silently replace clipboard with masked text
- [ ] 38+ regex patterns for credential types (port from SecretShields patterns)
- [ ] VS Code Marketplace submission

### Phase 1 — Proxy Mode + MCP Server
- [ ] Python sidecar: FastAPI OpenAI-compatible proxy on `localhost:8003`
- [ ] MCP server endpoint for auto-discovery by Continue and MCP-aware tools
- [ ] Presidio NER with developer policy
- [ ] SQLite session store with TTL
- [ ] `__P1__` token generation + unscrub on response
- [ ] Continue + Cursor integration docs
- [ ] `~/.sheru-mask/config.toml` for real API key + provider config

### Phase 2 — VS Code Extension (deep integration)
- [ ] Extension scaffold (TypeScript, manifest)
- [ ] Sidecar lifecycle manager (spawn/attach/shutdown)
- [ ] Live scan on file open/change — proactive detection in editor
- [ ] Inline gutter decorations — highlight detected entities
- [ ] Status bar counter: "N entities masked"
- [ ] Command palette: show session, clear session, toggle
- [ ] False-positive trainer (right-click → "ignore this pattern")
- [ ] `.sheru-mask.json` per-project config + IntelliSense
- [ ] `.env` file awareness — flag all values when `.env` is open

### Phase 3 — Power Features
- [ ] Deterministic pseudonymization mode (workspace-level persistent map)
- [ ] Session panel (webview) — list all masked entities this workspace session
- [ ] Hover on decoration → show entity type + token
- [ ] GitHub Copilot intercept (Mode C)
- [ ] JetBrains plugin (same sidecar, different extension host)
- [ ] Published detection benchmarks (F1 on CredData / SecretBench)

### Phase 4 — Team / Enterprise
- [ ] Server connect mode
- [ ] Team session namespace
- [ ] Policy sync from org sheru-mask server
- [ ] Audit trail forwarding
- [ ] Pre-commit hook integration (warn before git push if secrets detected)
