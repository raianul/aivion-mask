# Aivion Mask

Masks credentials and secrets before they reach AI coding assistants (Cursor, Continue, GitHub Copilot).

## What it does

When you copy text containing secrets, Aivion Mask intercepts it:

- **Warn mode** — shows a notification: "2 secrets detected in clipboard"
- **Block mode** — silently replaces clipboard contents with masked text

```
You copy:  postgresql://admin:s3cr3t@10.0.1.55:5432/prod_db
You paste: [REDACTED:DATABASE_URL_POSTGRES]
```

No server. No sidecar. Runs entirely locally.

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
| `aivion-mask.clipboard.pollIntervalMs` | `500` | Poll interval in ms |

## Commands

- **Aivion Mask: Toggle On/Off** — enable or disable the clipboard monitor

## Privacy

All detection runs locally. No data leaves your machine.
