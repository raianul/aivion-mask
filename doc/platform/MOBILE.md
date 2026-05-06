# sheru-mask — Mobile Plan

Local-first mobile integration. Masks PII before it reaches AI apps (ChatGPT, Claude, Gemini) on iOS and Android. Two interception surfaces: custom keyboard and share extension.

---

## 1. Platforms

| Platform | Interception Method | Phase |
|---|---|---|
| iOS — Custom Keyboard | Keyboard extension intercepts keystrokes | Phase 1 |
| iOS — Share Extension | Intercepts text shared into AI apps | Phase 2 |
| Android — IME Keyboard | Input Method Editor intercepts input | Phase 1 |
| Android — Accessibility Service | Intercepts input/output in any app | Phase 2 |

---

## 2. iOS Architecture

### Custom Keyboard Extension
- iOS allows third-party keyboards via `UIInputViewController`
- User sets sheru-mask as default keyboard in Settings → General → Keyboard
- Keyboard intercepts text before it's inserted into any app input (ChatGPT, Claude, Gemini, etc.)
- On send: NER → mask → paste masked text into app input
- NER model: Core ML export of distilBERT (~40MB, downloaded once)
- Session store: SQLite via App Group (shared between extensions)

**Limitation:** Response unmasking not possible via keyboard alone — keyboard has no read access to text rendered in another app.

### Share Extension (response unmasking)
- User selects AI response text → tap Share → sheru-mask
- Extension looks up tokens in local SQLite session → shows restored text inline
- Workaround for the keyboard limitation above

---

## 3. Android Architecture

### IME Keyboard (Input Method Editor)
- Android allows full custom keyboards via `InputMethodService`
- Intercepts input before it reaches any app — same approach as iOS keyboard
- NER model: ONNX Runtime for Android (~40MB)
- Session store: Room (SQLite wrapper)

### Accessibility Service (Phase 2)
- `AccessibilityService` can read and write text in any app window
- Enables response unmasking — reads AI response text, replaces `__Px__` tokens with originals
- Requires "Accessibility" permission — higher friction to enable, stronger capability

---

## 4. Supported AI Apps (Mobile)

| App | iOS | Android |
|---|---|---|
| ChatGPT | Keyboard (input only) | Keyboard + Accessibility |
| Claude | Keyboard (input only) | Keyboard + Accessibility |
| Gemini | Keyboard (input only) | Keyboard + Accessibility |
| Copilot | Keyboard (input only) | Keyboard + Accessibility |
| Perplexity | Keyboard (input only) | Keyboard + Accessibility |

---

## 5. Constraints vs Browser Extension

| | Browser Extension | Mobile |
|---|---|---|
| Input interception | Full DOM access | Keyboard extension |
| Response interception | Full DOM access | iOS: Share Extension / Android: Accessibility Service |
| NER model | ONNX/WASM in browser | Core ML (iOS) / ONNX Android |
| Session store | IndexedDB | SQLite via App Group / Room |
| Full round-trip mask+unmask | Yes | iOS: Phase 2 / Android: Phase 2 |

Mobile is harder than browser — especially response unmasking on iOS. Phase 1 covers input masking only. Full round-trip requires Phase 2 on both platforms.

---

## 6. Monetization

> **Placeholder — to be decided.**
>
> Questions to answer:
> - Free tier limits?
> - Paid tier unlock (e.g. extended entity set, server connect, response unmasking)?
> - One-time purchase vs subscription?
> - Relationship to API product and browser extension pricing?

---

## 7. Phases

### Phase 1 — Input Masking
- [ ] iOS keyboard extension (Swift) — NER via Core ML, SQLite via App Group
- [ ] Android IME keyboard (Kotlin) — NER via ONNX Runtime
- [ ] Developer policy entity set (credentials, keys, IPs)
- [ ] General policy entity set (PERSON, EMAIL, PHONE, LOCATION)
- [ ] App Store + Play Store submission

### Phase 2 — Full Round-Trip
- [ ] iOS Share Extension for response unmasking
- [ ] Android Accessibility Service for response unmasking
- [ ] Session sync between keyboard and share/accessibility components
- [ ] Multi-turn: pre-redact known entities from previous turns

### Phase 3 — Enterprise Connect
- [ ] Connect to org sheru-mask server (same pattern as browser extension)
- [ ] Policy sync from server
- [ ] Audit trail forwarding (MDM-managed devices)
