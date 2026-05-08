# aivion-mask benchmarks

Measures the latency overhead the proxy adds, isolated from real-network noise.

```
client ──► mock /v1/messages           (baseline)
client ──► proxy ──► mock /v1/messages (with masking + unmasking)
```

The mock returns a fixed canned response. The proxy is spawned in a subprocess
with `HOME` pointed at a temp dir and `ANTHROPIC_UPSTREAM` patched to the mock,
so it does **not** collide with your `aivion-mask start` instance on `:47474`.

## Run

```bash
~/.aivion-mask/venv/bin/python benchmarks/run.py
~/.aivion-mask/venv/bin/python benchmarks/run.py --iters 200 --warmup 20
~/.aivion-mask/venv/bin/python benchmarks/run.py --case heavy-stream-long
```

Cases:

| Case | Prompt | Stream | Response |
|---|---|---|---|
| `clean-nonstream-short` | no secrets | off | ~300 char |
| `clean-stream-short`    | no secrets | on  | ~300 char SSE |
| `heavy-nonstream-long`  | DB URL + 3 API keys | off | ~700 char w/ real masked tokens |
| `heavy-stream-long`     | DB URL + 3 API keys | on  | ~700 char SSE w/ real masked tokens |

## What you get

For each case, two rows: `direct` and `proxy`, plus a delta line. Columns:

- `ttfb-mean / sd / p95` — time to first byte (ms): mean, standard deviation, 95th percentile. For non-streaming, ttfb equals total.
- `tot-mean / sd / p95 / max` — full response time (ms): mean, stddev, p95, worst single iteration.

## Methodology details

- **Direct/proxy interleaved per iteration**, not all-direct then all-proxy. Removes the warm-cache bias toward whichever side runs second.
- **Heavy case round-trips real masked tokens.** At bench startup, `prompts.py` runs each fixture API key through the proxy's actual `display_value()` to compute the exact tokens the proxy will store; the long mock response embeds those tokens. Before timing each heavy case, the bench sends the prompt through the proxy once and asserts the originals come back — if unmask is broken, the bench fails loudly.
- **AWS_SECRET_ACCESS_KEY is intentionally omitted** from the heavy fixture. `AWS_SECRET_KEY` is in `_ALWAYS_REDACT`, which assigns it the display token `***`. That single-token entry collides with the literal `***` substring inside other display tokens (e.g. `ghp_AB***1234`), corrupting unmask via substring replacement. The collision is real and documented in `CLAUDE.md`; the bench drops it so the timing reflects the common case, not the bug.

## Ports

- mock: `47475`
- bench proxy: `47476`
- your normal proxy (left alone): `47474`

## Notes

- This measures **proxy overhead only**, not real Anthropic latency. For a
  real-world delta, see the real-API benchmarks below.
- The mock returns the same payload regardless of input, so any difference
  between `direct` and `proxy` columns is the masking + forwarding cost.
- The bench process inherits CPU contention from your machine — close other
  workloads for cleaner numbers.

---

## Real-API smoke tests

These are **sanity probes**, not benchmarks. They confirm the proxy works
end-to-end against the real `api.anthropic.com` (auth, streaming, error
handling). Use them to catch a hidden regression — not to measure latency.
For the defensible proxy-overhead number, run the mock bench above.

Two variants depending on what auth you have:

| Script | Auth source | Platforms |
|---|---|---|
| `smoke_real_macos_oauth.py` | Claude Code OAuth token from macOS keychain | macOS only |
| `smoke_real_api_key.py`     | `ANTHROPIC_API_KEY` env var                 | any |

Both share `_runner.py` — they only differ in how they build the auth header.
The proxy must be running on `:47474` (`aivion-mask start`).

```bash
# Claude Code subscription user (macOS):
~/.aivion-mask/venv/bin/python benchmarks/smoke_real_macos_oauth.py

# API key user (any OS):
export ANTHROPIC_API_KEY=sk-ant-api03-...
~/.aivion-mask/venv/bin/python benchmarks/smoke_real_api_key.py

# Both accept the same flags:
... --iters 10 --case heavy-stream --max-tokens 256 --model claude-haiku-4-5
```

Each iteration costs real tokens. Defaults: Haiku 4.5, `max_tokens=256`,
`--iters 5`. A full run (`--iters 10 --case all`) is roughly 96 API calls
and ~$0.10–0.15.

Cases: `clean-nonstream`, `clean-stream`, `heavy-nonstream`, `heavy-stream`.

### Smoke-test notes

- Results are **noisy** on consumer connections — bufferbloat alone can
  add hundreds of ms of jitter, swamping the proxy's ~6 ms overhead. Use
  the mock bench above for the trustworthy proxy-overhead number.
- The real bench is mainly useful as a sanity check that there's no
  hidden 100+ ms regression — i.e., the proxy isn't doing something
  catastrophically slow on the wire.
- Tokens never touch disk or logs; they live in the bench process only.
