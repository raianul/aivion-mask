# aivion-mask

A local-first credential masking layer for Claude.

Masks sensitive data before it reaches Claude. Restores originals in the response. Session-aware, streaming-safe, no server required.

```
You type:        "save this as DATABASE_URL in my .env:
                  postgresql://admin:s3cr3t@db.internal/prod"
                              ↓  aivion-mask masks credentials
Claude receives: "save this as DATABASE_URL in my .env:
                  postgresql://a***n:***@db***al/***"
                              ↓  forwarded to api.anthropic.com
Claude reasons over the masked text and replies (it never sees the real password).
                              ↓  aivion-mask scans the reply, restores originals
You see:         Claude's reply with credentials restored — usable as-is.
```

Whatever Claude does with the masked input — write config, refuse, ask a question, generate code — anything it echoes back gets unmasked before reaching you.

Works with Claude Code (CLI + VS Code), the Anthropic SDKs, aider, OpenCode, Continue.dev, and anything else that respects `ANTHROPIC_BASE_URL`.

No LLM calls inside the masking layer. Detection is regex + pattern matching, runs fully offline. OpenAI / Gemini providers are on the roadmap.

---

## Privacy

Your prompts go to the LLM API you've configured — and nowhere else. Aivion has no servers, no telemetry, no analytics, no crash reporting.

- The proxy runs entirely on your machine
- The only outbound request is to your chosen LLM provider (e.g. `api.anthropic.com`)
- Token mappings live in a local SQLite file at `~/.aivion-mask/sessions.db` (chmod 0600), expire after 8h by default, and never leave your machine
- API keys / OAuth tokens pass through unchanged — the proxy never stores credentials

See [PRIVACY.md](PRIVACY.md) for full details.

---

## Quick Start — Claude Code

**Install (one command):**

```bash
git clone https://github.com/raianul/aivion-mask.git
cd aivion-mask
./install.sh
```

`install.sh` will:

1. Check Python ≥ 3.10
2. Create an isolated venv at `~/.aivion-mask/venv/`
3. Install `aivion-mask-core` + `aivion-mask-claude` into it
4. Add `PATH` + `ANTHROPIC_BASE_URL` lines to your `~/.zshrc` or `~/.bashrc` (with confirmation — you can decline)
5. Start the proxy in the background and open the dashboard in your browser

**Open a new terminal** so Claude Code (and any other tool in that shell) picks up the new `ANTHROPIC_BASE_URL`. The proxy itself is already running — no further action needed.

**Daily commands:**

| Command | What it does |
|---|---|
| `aivion-mask start` | Start the proxy in the background |
| `aivion-mask stop` | Stop it |
| `aivion-mask restart` | Stop + start |
| `aivion-mask status` | Show running/not, version, port |
| `aivion-mask logs -f` | Tail proxy logs |
| `aivion-mask dashboard` | Open the web UI in your browser |

### Uninstall

```bash
./uninstall.sh
```

`uninstall.sh` will:

1. Stop the proxy if it's running
2. Remove the `aivion-mask` block from your shell rc file — both the `PATH` line and the `ANTHROPIC_BASE_URL` export, so Claude Code (and any other tool reading that env var) stops routing through the proxy
3. Delete the venv at `~/.aivion-mask/venv/`
4. Ask before deleting `~/.aivion-mask/` (which holds your config, auth token, and session DB) — answer `n` to keep your data for a future reinstall

Open a new terminal afterward so the rc changes take effect.

**Per-tool reference:**

| Tool | How |
|---|---|
| **Claude Code CLI** | Picks up `ANTHROPIC_BASE_URL` automatically |
| **Claude Code in VS Code** | Restart VS Code after adding to shell rc |
| **Anthropic Python SDK** | Picks up `ANTHROPIC_BASE_URL`, or pass `base_url="http://localhost:47474"` |
| **Anthropic TypeScript SDK** | Picks up `ANTHROPIC_BASE_URL`, or pass `baseURL: 'http://localhost:47474'` |
| **aider** | `export ANTHROPIC_API_BASE=http://localhost:47474` (litellm convention) |
| **llm + llm-anthropic** | `export ANTHROPIC_API_BASE=http://localhost:47474` |
| **OpenCode** | Picks up `ANTHROPIC_BASE_URL` automatically |
| **Continue.dev** | Set `apiBase: "http://localhost:47474"` in `~/.continue/config.json` |

Both OAuth (subscription) and API key auth pass through unchanged.

### Bypass the proxy

When you want to talk to Claude directly (debugging, no secrets in the prompt, proxy is down):

```bash
# Just this one command:
env -u ANTHROPIC_BASE_URL claude

# This terminal session only:
unset ANTHROPIC_BASE_URL

# Permanently: comment out the export in ~/.zshrc and open a new terminal.
```

The proxy itself can be left running — it just won't see the traffic.

---

## How It Works

### Token format

Detected secrets are replaced with display-safe tokens:

```
postgresql://admin:s3cr3t@db.internal/prod  →  postgresql://a***n:***@db***al/***
ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcd1234      →  ghp_AB***1234
AKIAZZZZZZZZZZZZZZZZ                         →  AKIA***ZZZZ
```

Scheme and structure are preserved so the LLM understands what it's working with. Secrets are hidden. Passwords are always fully redacted (`***`); other values reveal a length-proportional prefix and suffix.

### Session model

Each request gets a session ID. Token mappings (masked → original) are stored locally and used to restore the response.

```
session_id: abc123
  ├── token_1  →  postgresql://admin:s3cr3t@db.internal/prod
  ├── token_2  →  ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcd1234
  └── token_3  →  AKIAZZZZZZZZZZZZZZZZ
```

Same `session_id` across turns prevents the "turn 3 leak" — a secret mentioned in turn 1 is pre-redacted in all subsequent turns before regex detection even runs.

---

## Performance

aivion-mask adds **5–8 ms of CPU overhead** per request — too small to notice against typical 1–4 second Anthropic API responses (well under 1% added latency).

### How it was measured

Against a **local mock** Anthropic upstream (loopback only — internet connection not involved). The proxy is started in a subprocess pointed at the mock so the only thing being timed is the proxy's own work: parsing, masking, forwarding, response scanning, unmasking. The heavy case actually round-trips real masked tokens (the bench computes `display_value()` for each fixture secret, bakes those into the mock response, and verifies originals come back before timing — so we know the unmask path is exercised).

| | |
|---|---|
| Hardware | Apple M1 |
| OS | macOS 15.6 |
| Python | 3.12.2 |
| aivion-mask | `aivion-mask-claude` 0.2.0 |
| Iterations | 100 per case, 10 warmup, direct/proxy interleaved per iteration |

Per-case proxy overhead (direct-to-mock vs. proxy-to-mock):

| Case | Mean | Stddev | p95 |
|---|---|---|---|
| Clean prompt, non-streaming | +5.6 ms | ±0.9 | 8.5 ms |
| Clean prompt, streaming     | +5.8 ms | ±0.8 | 8.3 ms |
| Heavy prompt (3 secrets), non-streaming | +6.5 ms | ±1.2 | 9.5 ms |
| Heavy prompt (3 secrets), streaming     | +6.8 ms | ±1.3 | 9.8 ms |

Individual means typically drift ±0.5 ms between runs even on the same machine — laptop thermal state, OS background tasks, and disk cache state all influence them. The per-case stddev above is *within-run*; expect that much again of *between-run* variance when reproducing.

**Numbers will differ on other hardware** — newer Apple Silicon, x86 server, Linux containers will all measure slightly differently. Reproduce on yours:

```bash
~/.aivion-mask/venv/bin/python benchmarks/run.py
```

Real-API smoke tests (`smoke_real_macos_oauth.py` / `smoke_real_api_key.py`) are also included for end-to-end sanity checks against `api.anthropic.com`, but their results are dominated by Anthropic's natural per-call latency variance and your connection's bufferbloat — they verify the proxy works, not how fast it is. See [`benchmarks/README.md`](benchmarks/README.md) for full methodology and caveats.

---

## Dashboard

A local web UI at `http://127.0.0.1:47474/` shows masking activity per request and lets you clear expired sessions.

### Auth token

The dashboard is auth-gated — only someone with the local token can open it. The token is auto-generated on first start and stored at `~/.aivion-mask/auth-token` (chmod 0600).

**Get the URL two ways:**

1. **From startup logs** — when you run the proxy, it prints the full URL:
   ```
   INFO:  aivion_mask_claude - Dashboard: http://127.0.0.1:47474/?token=...
   ```

2. **From the file** — `cat ~/.aivion-mask/auth-token`, then build `http://127.0.0.1:47474/?token=<paste>`.

The token persists across restarts. To rotate it, delete the file and restart the proxy.

### What you'll see

| Column | What it means |
|---|---|
| **Request ID** | UUID of the request (one per Claude Code prompt unless `X-Aivion-Session` is set explicitly) |
| **Tokens masked** | How many credentials/secrets were detected and replaced |
| **First seen** | When the request was processed |
| **Expires** | Countdown to when token mappings will be deleted (defaults to 8h) |

The **Clean expired** button forces an immediate sweep (otherwise it runs automatically every 10 minutes).

---

## Configuration

The config file lives at `~/.aivion-mask/config.toml`. It is created automatically on first run — you don't need to touch it to get started.

```toml
[sidecar]
port = 47474
session_ttl_hours = 8
unmask_response = true

# Custom regex patterns (optional):
# [[sidecar.custom_patterns]]
# name    = "MY_INTERNAL_TOKEN"
# pattern = 'int_[A-Za-z0-9]{32}'
```

### Settings

| Key | Default | Description |
|---|---|---|
| `port` | `47474` | Port the local proxy listens on. Change if something else is using it. |
| `session_ttl_hours` | `8` | How long token↔original mappings are kept in the local SQLite store. |
| `unmask_response` | `true` | Restore original values in the LLM response before returning it to your tool. Set to `false` to see the masked response as-is. |

### Custom patterns

Add your own regex patterns to catch internal tokens, API keys, or any secret format that isn't covered by the built-in list:

```toml
[[sidecar.custom_patterns]]
name    = "MY_INTERNAL_TOKEN"
pattern = 'int_[A-Za-z0-9]{32}'

[[sidecar.custom_patterns]]
name    = "ACME_API_KEY"
pattern = 'acme_[a-f0-9]{40}'
```

`name` is used as the label in logs. `pattern` is a Python regex — test it with `python3 -c "import re; print(re.findall(r'your_pattern', 'test_input'))"` before adding.

### Applying changes

Config is read once at startup. After editing `~/.aivion-mask/config.toml`, restart the proxy:

```bash
aivion-mask restart
```

---

## Supported Credential Types

**Cloud keys:** AWS_ACCESS_KEY_ID, AWS_SECRET_KEY, GOOGLE_API_KEY, AZURE_STORAGE

**Source control:** GITHUB_TOKEN (ghp_, ghs_, gho_, github_pat_)

**AI providers:** OPENAI_API_KEY, OPENAI_API_KEY_V2 (sk-proj-), ANTHROPIC_API_KEY

**Payments:** STRIPE_SECRET_KEY, STRIPE_TEST_KEY, STRIPE_RESTRICTED

**Messaging:** SLACK_BOT_TOKEN, SLACK_USER_TOKEN, SLACK_APP_TOKEN, SLACK_WEBHOOK, SENDGRID_API_KEY, MAILGUN_API_KEY, TWILIO_ACCOUNT_SID

**Package registries:** NPM_TOKEN, PYPI_TOKEN

**E-commerce:** SHOPIFY_TOKEN, SHOPIFY_CUSTOM_TOKEN

**Infrastructure:** TERRAFORM_TOKEN, DOCKER_HUB_PAT, FIREBASE_URL

**Connection strings:** DATABASE_URL (Postgres, MySQL, MongoDB), DATABASE_URL_REDIS, URL_WITH_CREDENTIALS

**Cryptographic:** PRIVATE_KEY (RSA, EC, OpenSSH), JWT_TOKEN

**Network:** PRIVATE_IP (10.x, 192.168.x, 172.16-31.x)

**Custom:** Regex-based patterns via `~/.aivion-mask/config.toml`

---

## Repository Structure

| Path | Package | What it is |
|---|---|---|
| `packages/core/` | `aivion-mask-core` | Shared masking engine — patterns, session store, tokens, streaming |
| `packages/claude/` | `aivion-mask-claude` | Anthropic Claude provider (ships now) |

---

## Roadmap

- [x] Core masking engine + session model + 40 credential patterns
- [x] Anthropic `/v1/messages` provider — Claude Code + SDK + streaming
- [x] `install.sh` / `uninstall.sh` — one-command setup, isolated venv, shell rc edits
- [x] `aivion-mask` CLI — `start`, `stop`, `restart`, `status`, `logs`, `dashboard`
- [ ] System service registration (launchd / systemd) — auto-start on login
- [ ] OpenAI `/v1/chat/completions` provider (`aivion-mask-openai`)
- [ ] Browser extension — Chrome/Firefox

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
