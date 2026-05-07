# aivion-mask — System Tray App (Network-Level)

## Vision

A lightweight system tray application that sits silently on the user's machine and
intercepts all outbound LLM traffic at the network level. No per-app configuration.
No API key management. No browser extension. No VS Code extension required.

Install once → protected forever.

---

## Why Network Level

Every other approach requires the user to configure each tool individually:

| Approach | Covers | Gap |
|---|---|---|
| VS Code extension | VS Code only | Cursor, Claude.ai, browser, CLI — all missed |
| Browser extension | Browser tabs only | Native apps missed |
| Env vars per app | Apps that respect them | Subscription apps (Cursor Pro, Copilot) missed |
| **Network level** | **Everything on the machine** | **Nothing missed** |

Corporate DLP tools (Zscaler, Netskope) already use this pattern to prevent data leakage.
aivion-mask is the developer-focused, local-only, open-source version.

---

## How It Works

```
Any app on your machine
        │
        │  HTTPS → api.anthropic.com / api.openai.com / etc.
        ▼
   macOS pf (packet filter)
        │  redirects port 443 → localhost:47474
        ▼
┌─────────────────────────────────────────┐
│         aivion-mask sidecar             │
│                                         │
│  1. TLS termination (fake cert, our CA) │
│  2. Mask secrets in request             │
│  3. Forward to real LLM endpoint        │
│  4. Unmask tokens in response           │
│  5. Re-encrypt response to app          │
└─────────────────────────────────────────┘
        │
        ▼
   Real LLM API — never sees raw secrets
```

---

## Components

### 1. CA Certificate Manager
- Generate a local CA keypair on first install (`~/.aivion-mask/ca.key`, `ca.crt`)
- Install CA cert into macOS System Keychain (one-time `sudo`)
- All dynamically generated per-domain certs are signed by this CA
- Uninstall removes the CA cert cleanly

### 2. MITM Proxy Engine
- Built on top of [mitmproxy](https://mitmproxy.org/) Python library
- Intercepts HTTPS connections to known LLM endpoints
- Generates per-domain certificates on the fly (signed by local CA)
- Passes non-LLM traffic through untouched
- Plugs into existing masking engine (already built)

**Known LLM endpoints to intercept:**
```
api.openai.com
api.anthropic.com
generativelanguage.googleapis.com
api.groq.com
api.mistral.ai
openrouter.ai
api.cohere.ai
```

### 3. Traffic Redirector
Platform-specific rules to redirect port 443 traffic to the sidecar.

**macOS (pf):**
```
rdr pass on lo0 proto tcp to port 443 -> 127.0.0.1 port 47474
rdr pass on en0 proto tcp to port 443 -> 127.0.0.1 port 47474
```

**Linux (iptables):**
```
iptables -t nat -A OUTPUT -p tcp --dport 443 -j REDIRECT --to-port 47474
```

**Windows (WFP — Windows Filtering Platform):**
Redirect via `netsh` or a lightweight WFP driver.

### 4. Multi-Format Proxy
The sidecar currently only speaks OpenAI format. Network-level interception means
it will receive Anthropic, Google, Cohere formats too. Add format handlers:

| Endpoint | Format | Status |
|---|---|---|
| `/v1/chat/completions` | OpenAI | ✅ done |
| `/v1/messages` | Anthropic | ➕ add |
| `/v1beta/models/*/generateContent` | Google Gemini | ➕ add |
| `/v1/chat` | Cohere | ➕ add |

All formats: mask request → forward → unmask response. Same masking engine underneath.

### 5. System Tray UI
Cross-platform system tray app. Minimal UI — status and quick controls only.

```
🛡️ aivion-mask: active
─────────────────────
Masked today: 47 secrets
Active sessions: 3
─────────────────────
Pause interception
View log
Settings
─────────────────────
Quit
```

**Tech stack:** Python + `pystray` + `Pillow` (icon rendering)
Packaged as a single binary via PyInstaller (same pattern as sheru-desktop).

### 6. Settings Window
Minimal settings — everything has sensible defaults:

- Toggle interception on/off
- `unmask_response` toggle
- Custom patterns (add/remove)
- Allowlist — domains to never intercept
- View masked secrets log (tokens only, never originals)

---

## What Changes for Existing Components

### Sidecar (`sidecar/`)
- Add `mitmproxy` as dependency
- Add HTTPS termination mode (vs current HTTP-only proxy mode)
- Add Anthropic `/v1/messages` format handler
- Add Google Gemini format handler
- Existing masking engine unchanged

### VS Code Extension (`extension/vscode/`)
- Becomes optional — useful for settings UI inside VS Code
- `SidecarManager` detects if system-level interception is active, skips manual setup
- Status bar shows interception status

### Config (`~/.aivion-mask/config.toml`)
New fields:
```toml
[sidecar]
mode = "network"          # "proxy" (manual) or "network" (MITM)
intercept_domains = [     # domains to intercept
  "api.openai.com",
  "api.anthropic.com",
]
allowlist_domains = []    # domains to never touch
```

---

## Install Flow (macOS)

```
1. Download aivion-mask.dmg
2. Drag to Applications
3. Open aivion-mask
4. First-run wizard:
   ─────────────────────────────────────────────
   "aivion-mask needs to install a security
    certificate to protect your LLM traffic.
    This stays on your machine only."
   [Install Certificate]  → sudo prompt → done
   ─────────────────────────────────────────────
   "Enable network-level protection?"
   [Enable]  → pf rules installed → done
   ─────────────────────────────────────────────
5. System tray icon appears — active immediately
6. Every LLM call from every app is now masked
```

---

## Uninstall Flow

```
aivion-mask → Quit → "Remove all components?"
→ Removes pf rules
→ Removes CA cert from keychain
→ Deletes ~/.aivion-mask/
→ Clean uninstall, no residue
```

---

## Security Considerations

- CA private key stored at `~/.aivion-mask/ca.key` with `chmod 600`
- Key never leaves the machine — all cert generation is local
- Only known LLM domains are intercepted — all other HTTPS passes through untouched
- User can audit the allowlist and intercept list at any time
- Interception can be paused or disabled from system tray instantly
- Full uninstall removes all trust anchors cleanly

---

## Tech Stack

| Component | Technology |
|---|---|
| Proxy engine | Python + mitmproxy library |
| Masking engine | Existing sidecar (Python) |
| System tray | Python + pystray |
| Certificate management | Python cryptography library |
| Traffic redirect (macOS) | pf (pfctl) |
| Traffic redirect (Linux) | iptables |
| Traffic redirect (Windows) | netsh / WFP |
| Packaging | PyInstaller → .dmg / .exe / .AppImage |

---

## Phases

### Phase 2a — MITM Engine (macOS only)
- CA cert generation and system trust installation
- mitmproxy-based HTTPS interception
- pf traffic redirect
- Intercept OpenAI + Anthropic (covers 80% of usage)
- System tray with on/off toggle

### Phase 2b — Multi-Format Support
- Add Google Gemini format handler
- Add Cohere format handler
- Intercept all known LLM endpoints

### Phase 2c — Windows + Linux
- Windows: WFP-based traffic redirect
- Linux: iptables rules
- Platform-specific packaging (.exe, .AppImage)

### Phase 2d — Settings + Dashboard
- Full settings window
- Masked secrets log (tokens only)
- Per-session activity view
- Custom patterns UI

---

## Current State

| Component | Status |
|---|---|
| Masking engine (32 patterns + custom) | ✅ done |
| Session management (SQLite) | ✅ done |
| OpenAI proxy (`/v1/chat/completions`) | ✅ done |
| Type-specific tokens (`__DB1__`, `__GH1__`) | ✅ done |
| Config system (TOML + VS Code settings sync) | ✅ done |
| HTTPS MITM engine | ⬜ not started |
| CA cert management | ⬜ not started |
| Traffic redirection | ⬜ not started |
| Anthropic format handler | ⬜ not started |
| Google Gemini format handler | ⬜ not started |
| System tray UI | ⬜ not started |
| Packaging / installer | ⬜ not started |
