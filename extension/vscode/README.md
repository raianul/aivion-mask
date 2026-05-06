# Aivion Mask — Clipboard Guard

Detects credentials and secrets in your clipboard before you paste them into Cursor, Continue, GitHub Copilot, or any AI coding assistant.

## What it does

When you copy text containing secrets, Aivion Mask intercepts it:

- **Warn mode** — shows a notification: "2 secrets detected in clipboard" with a "Block now" option
- **Block mode** — silently replaces clipboard contents with masked text before you can paste

```
You copy:  postgresql://admin:s3cr3t@10.0.1.55:5432/prod_db
You paste: [REDACTED:DATABASE_URL_POSTGRES]
```

No server. No sidecar. Runs entirely locally. Nothing leaves your machine.

## Detected credential types (40)

AWS keys · GitHub tokens · Slack tokens · Stripe keys · SendGrid · Twilio · Google API keys ·
OpenAI · Anthropic · NPM tokens · PyPI tokens · Shopify · Mailchimp · Mailgun ·
Database connection strings (Postgres, MySQL, MongoDB, Redis) ·
Private keys (RSA, EC, OpenSSH, PKCS#8) · JWT tokens ·
URLs with embedded credentials · Private IP addresses ·
Firebase URLs · Azure storage strings · Terraform tokens · Docker Hub tokens

## Configuration

| Setting | Default | Description |
|---|---|---|
| `aivion-mask.clipboard.enabled` | `true` | Enable clipboard monitoring |
| `aivion-mask.clipboard.mode` | `"warn"` | `"warn"` or `"block"` |
| `aivion-mask.clipboard.pollIntervalMs` | `500` | Poll interval in ms (100–5000) |

Open VS Code Settings (`Ctrl+,`) and search for `aivion-mask` to configure.

## Commands

- **Aivion Mask: Toggle On/Off** — enable or disable the clipboard monitor (`Ctrl+Shift+P` → "Aivion Mask")

The status bar item (bottom-right) shows the current state: active, disabled, or secrets detected.

## Coming in Phase 1

- **Proxy mode** — local OpenAI-compatible server (`http://localhost:8003/v1/openai`). Point Cursor or Continue at it and secrets are masked end-to-end with full restore in the LLM response.
- **MCP server** — auto-discovered by Continue and MCP-aware tools, no manual config.

## Privacy

All detection runs locally on your machine using regex patterns. No data is transmitted, no telemetry, no analytics. [Privacy policy →](https://github.com/raianul/aivion-mask/blob/main/PRIVACY.md)

## Source

[github.com/raianul/aivion-mask](https://github.com/raianul/aivion-mask) — Apache 2.0
