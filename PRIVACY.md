# Privacy Policy — Aivion Mask

**Last updated:** 2026-05-08

## Summary

Aivion Mask does not collect, transmit, or process any data on behalf of Aivion. All processing runs locally on your machine. The only outbound network requests are the LLM API calls you explicitly route through the proxy — nothing goes to Aivion servers.

---

## What the sidecar does

Aivion Mask runs a local HTTP proxy on `localhost:47474`. It intercepts LLM API requests from your tools (Claude Code, SDK scripts, etc.), detects and replaces credentials and secrets with short-lived tokens, forwards the masked request to the upstream LLM API (e.g. `api.anthropic.com`), and restores the originals in the response before returning it to you.

---

## Data collection

**None — by Aivion.**

- No telemetry
- No analytics
- No crash reporting
- No usage statistics
- No requests to Aivion servers of any kind

---

## Local data storage

The sidecar writes to your local machine only:

| What | Where | Why | Retention |
|---|---|---|---|
| Session token mappings (masked token ↔ original value) | `~/.aivion-mask/sessions.db` (SQLite) | Needed to restore originals in LLM responses | TTL 8 hours by default, configurable |
| Config file | `~/.aivion-mask/config.toml` | Sidecar settings (port, patterns, API key if configured) | Until you delete it |

No logs of request content are written. The SQLite database stores only the token↔original mapping pairs, not the full request or response text.

---

## Network requests

The sidecar makes outbound HTTPS requests **only** to the upstream LLM API you configure (default: `api.anthropic.com`). Your API key or OAuth token is forwarded in the request header, exactly as your tool would have sent it. Aivion Mask never sees, stores, or transmits your credentials to any other destination.

---

## Third parties

No data is shared with any third party beyond the LLM API you have explicitly configured. There are no third-party SDKs, trackers, or analytics services.

---

## Your rights (GDPR)

The only personal data that may be processed locally is whatever you include in your LLM prompts (which you control). Aivion does not receive or store this data. If you want to clear local session data, delete `~/.aivion-mask/sessions.db` or call `DELETE /v1/session/{id}` on the running sidecar.

If you have any questions, contact:

**Controller:** Sayed Raianul Kabir  
**Email:** raianul.berlin@gmail.com  
**GitHub:** https://github.com/raianul/aivion-mask

---

## Future versions

If future versions introduce any form of server-side data collection (e.g. optional cloud audit trail), this policy will be updated before release and users will be explicitly informed.
