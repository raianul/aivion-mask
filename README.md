# aivion-mask

A local-first PII masking layer for LLM applications.

Masks sensitive data before it reaches any LLM. Restores originals in the response. Session-aware, streaming-safe, no server required.

```
Your prompt: "connect to postgresql://admin:s3cr3t@db.internal/prod"
                        ↓
               aivion-mask (local proxy)
                        ↓
  To LLM:   "connect to postgresql://adm***al/***"
                        ↓
               Claude / OpenAI / ...
                        ↓
  Restored: "I'd connect using: postgresql://admin:s3cr3t@db.internal/prod"
```

No LLM calls inside the masking layer. Detection is regex + pattern matching, runs fully offline.

---

## What's in this repo

| Path | Package | What it is |
|---|---|---|
| `packages/core/` | `aivion-mask-core` | Shared masking engine — patterns, session store, tokens, streaming |
| `packages/claude/` | `aivion-mask-claude` | Anthropic Claude provider (ships now) |
| `packages/openai/` | `aivion-mask-openai` | OpenAI provider (scaffold) |
| `extension/browser/` | — | Chrome/Firefox extension for AI chat UIs (planned) |

---

## How It Works

### Token format

Detected secrets are replaced with display-safe tokens:

```
postgresql://admin:s3cr3t@db.internal/prod  →  postgresql://adm***al/***
ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcd1234     →  ghp_ABCD***1234
AKIAZZZZZZZZZZZZZZZZ                        →  AKIA***ZZZZ
```

Scheme and structure are preserved so the LLM understands what it's working with. Secrets are hidden.

### Session model

```
session_id: abc123
  ├── token_1  →  postgresql://admin:s3cr3t@db.internal/prod
  ├── token_2  →  ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcd1234
  └── token_3  →  AKIAZZZZZZZZZZZZZZZZ
```

Same `session_id` across turns prevents the "turn 3 leak" — a secret mentioned in turn 1 is pre-redacted in all subsequent turns before NER even runs.

---

## Quick Start — Claude Code

**1. Install and start:**

```bash
git clone https://github.com/raianul/aivion-mask.git
cd aivion-mask/packages/claude
pip install -e .
aivion-mask-claude          # proxy listens on :47474
```

**2. One line in your shell rc:**

```bash
# ~/.zshrc or ~/.bashrc
export ANTHROPIC_BASE_URL=http://localhost:47474
```

Restart your terminal and VS Code (quit and reopen — not just reload). Every tool that respects `ANTHROPIC_BASE_URL` now routes through the proxy.

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

Both OAuth (subscription) and API key auth pass through unchanged. The proxy never stores credentials.

---

## Supported Credential Types

**Cloud keys:** AWS_ACCESS_KEY_ID, AWS_SECRET_KEY, GOOGLE_API_KEY, AZURE_STORAGE

**Source control:** GITHUB_TOKEN (ghp_, ghs_, gho_, github_pat_)

**AI providers:** OPENAI_API_KEY, OPENAI_API_KEY_V2 (sk-proj-), ANTHROPIC_API_KEY

**Payments:** STRIPE_SECRET_KEY, STRIPE_TEST_KEY, STRIPE_RESTRICTED

**Messaging:** SLACK_BOT_TOKEN, SLACK_USER_TOKEN, SLACK_APP_TOKEN, SLACK_WEBHOOK, SENDGRID_API_KEY, MAILCHIMP_API_KEY, MAILGUN_API_KEY, TWILIO_ACCOUNT_SID

**Package registries:** NPM_TOKEN, PYPI_TOKEN

**E-commerce:** SHOPIFY_TOKEN, SHOPIFY_CUSTOM_TOKEN

**Infrastructure:** TERRAFORM_TOKEN, DOCKER_HUB_PAT, FIREBASE_URL

**Connection strings:** DATABASE_URL (Postgres, MySQL, MongoDB), DATABASE_URL_REDIS, URL_WITH_CREDENTIALS

**Cryptographic:** PRIVATE_KEY (RSA, EC, OpenSSH), JWT_TOKEN

**Network:** PRIVATE_IP (10.x, 192.168.x, 172.16-31.x)

**Custom:** Regex-based patterns via `~/.aivion-mask/config.toml`

---

## Roadmap

- [x] Core masking engine + session model + 40 credential patterns
- [x] Anthropic `/v1/messages` provider — Claude Code + SDK + streaming (`aivion-mask-claude` v0.2.0)
- [ ] `aivion-mask-claude install` — one-command shell rc setup + system service registration
- [ ] OpenAI `/v1/chat/completions` provider (`aivion-mask-openai`)
- [ ] Browser extension — Chrome/Firefox

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
