# sheru-mask — Browser Extension Plan

Local-first Chrome/Firefox extension. Masks PII before it reaches ChatGPT, Claude, Gemini, or any other AI chat interface. No server. No account required. PII never leaves the device.

---

## 1. What It Does

```
User types in ChatGPT input box
           │
Extension intercepts DOM submit event
           │
Local NER (ONNX/WASM)  +  IndexedDB session store
           │
"Sarah Johnson's SSN is 219-09-9999"
     → "__P1__'s SSN is __P2__"
           │
Masked text sent to ChatGPT
           │
ChatGPT responds: "I've updated __P1__'s record, SSN __P2__ is verified"
           │
Extension intercepts DOM response
           │
Lookup __P1__, __P2__ in IndexedDB
           │
User sees: "I've updated Sarah Johnson's record, SSN 219-09-9999 is verified"
```

Zero network calls to sheru-mask servers. Fully air-gapped.

---

## 2. Supported Platforms

| Platform | Status |
|---|---|
| ChatGPT (chat.openai.com) | Phase 1 |
| Claude (claude.ai) | Phase 1 |
| Gemini (gemini.google.com) | Phase 1 |
| Grok (x.com/i/grok) | Phase 2 |
| Microsoft Copilot | Phase 2 |
| DeepSeek | Phase 2 |
| Perplexity | Phase 2 |

---

## 3. Local Architecture

```
Browser Extension
  ├── content_script.js     DOM interception per supported site
  ├── background.js         Service worker — session coordinator
  ├── popup/                Settings UI (policy selector, entity toggles)
  └── lib/
       ├── ner.js           ONNX runtime + model inference
       ├── session.js       IndexedDB read/write (token map + TTL)
       ├── masker.js        Token generation + display_value mapping
       └── unmasker.js      Token → original lookup
```

**NER model:** ONNX export of a distilBERT NER model fine-tuned on PII entities. Runs entirely in-browser via `onnxruntime-web`. ~40MB model download, cached after first install.

**Session store:** IndexedDB — survives page reloads, scoped per browser profile.

**Token format:** Same as server: `__P1__`, `__P2__` — 5-7 chars, streaming-safe.

**Display values:** `[Name]`, `[Email]`, `[SSN]` shown to user during streaming. Full originals restored after response completes.

---

## 4. DOM Interception Strategy

Each supported platform requires a site-specific content script adapter.

**ChatGPT / Claude / Gemini pattern:**
- Intercept `Enter` keypress and send button click on the textarea
- Read textarea value → run NER → replace value → allow submit
- Observe response DOM mutations (streaming chunks) → buffer until `__Px__` token is complete → replace with display value
- On stream end → run full unmask → replace entire response text

**Streaming handling:**
- Response arrives in chunks: `"I've updat"` → `"ed __P"` → `"1__ 's record"`
- Buffer chunks until `safe_flush_point` — flush everything before a `__` that hasn't closed yet
- Display value shown live; full unmask runs once stream ends

---

## 5. Policy (Entity) Selection

User selects a policy in the extension popup:

| Policy | Entities |
|---|---|
| **General** | PERSON, EMAIL_ADDRESS, PHONE_NUMBER, LOCATION |
| **Medical** | + US_SSN, DATE_TIME, MEDICAL_RECORD_NUMBER |
| **Finance** | + CREDIT_CARD, IBAN_CODE, US_BANK_NUMBER |
| **Developer** | AWS_ACCESS_KEY, AZURE_KEY, GITHUB_TOKEN, IP_ADDRESS, URL |
| **Custom** | User-defined entity toggle list |

Stored in `chrome.storage.local`. No server sync.

---

## 6. Session Model

```
Session = one conversation tab
  ├── session_id: generated on first mask in that tab
  ├── __P1__ → Sarah Johnson
  ├── __P2__ → 219-09-9999
  └── expires: 24h after last activity
```

- New tab → new session
- Reload same tab → same session (IndexedDB persists)
- Multi-turn: turn 2 pre-redacts known entities before running NER → prevents "3rd message leak"
- Session TTL: 24h default, configurable in settings

---

## 7. Competitor: ChatWall

| | ChatWall | sheru-mask extension |
|---|---|---|
| Token format | `[NAME_1]` (category-only) | `__P1__` (numbered, unambiguous) |
| NER model | BERT (v1 local) → ONNX (v2) | ONNX distilBERT |
| Multi-turn session | No | Yes — pre-redacts known entities |
| Per-policy presets | No | Yes |
| Display values during streaming | No | Yes |
| Open source | MIT | TBD |
| Pricing | Free → €4.90/mo | Free tier + paid |
| Browser | Chrome only | Chrome + Firefox |

ChatWall's `[NAME_1]` token: category-only, same entity type collision risk, no guaranteed round-trip uniqueness if LLM paraphrases. `__P1__` is position-indexed — always unambiguous.

---

## 8. Privacy Guarantee

- NER model runs in WASM inside the browser sandbox
- Session store is IndexedDB — never synced to any server
- No analytics, no telemetry (opt-in only for crash reports)
- No account required for local use
- Optional: connect to org's sheru-mask server for centralized audit (enterprise)

---

## 9. Optional Server Connect (Enterprise)

Enterprise users can connect the extension to their org's sheru-mask server:

```
Extension settings → "Connect to org server"
  → Enter: https://mask.company.com
  → Enter: sk-mask-...
  → Session store switches from IndexedDB → org Valkey
  → Audit trail written to org PostgreSQL
  → Policy pulled from org config (not local presets)
```

This bridges the consumer extension into the enterprise API product. Same extension, two modes.

---

## 10. Monetization

> **Placeholder — to be decided.**
>
> Questions to answer:
> - Free tier limits (e.g. N entities/day, N sessions/month)?
> - Paid tier unlocks (e.g. extended entity set, session history, enterprise connect)?
> - One-time purchase vs subscription?
> - Relationship to API product pricing tiers?

---

## 11. Phases

### Phase 1 — Core Extension
- [ ] Chrome extension manifest v3
- [ ] Content scripts for ChatGPT, Claude, Gemini
- [ ] ONNX NER model (distilBERT, 5 entity types: PERSON, EMAIL, PHONE, LOCATION, SSN)
- [ ] IndexedDB session store with TTL
- [ ] `__P1__` token generation + display value substitution
- [ ] Streaming-safe unmask (safe_flush_point buffer)
- [ ] Popup UI — policy selector, on/off toggle per site
- [ ] Chrome Web Store submission

### Phase 2 — More Platforms + Entities
- [ ] Firefox support (WebExtensions API)
- [ ] Grok, Copilot, DeepSeek, Perplexity content scripts
- [ ] Extended entity set (financial, healthcare, credentials)
- [ ] Custom entity toggle in popup
- [ ] Multi-turn session memory visible in popup ("3 entities masked this conversation")

### Phase 3 — Enterprise Connect
- [ ] Server connect mode (org sheru-mask instance)
- [ ] Policy sync from server
- [ ] Audit trail forwarding
- [ ] SSO via org API key

### Phase 4 — Polish
- [ ] Inline highlight — show masked spans in the textarea before submit
- [ ] Session history panel — see what was masked per conversation
- [ ] Export session log (local JSON)
