"""Shared logic for the real-API benchmarks.

Both smoke_real_macos_oauth.py (OAuth from keychain) and smoke_real_api_key.py (ANTHROPIC_API_KEY)
import this. They differ only in how they build the auth headers.
"""
from __future__ import annotations
import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass
from typing import Callable

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prompts import CLEAN_PROMPT, HEAVY_PROMPT, make_request_body  # noqa: E402

PROXY_URL  = "http://localhost:47474/v1/messages"
DIRECT_URL = "https://api.anthropic.com/v1/messages"

CASES = {
    "clean-nonstream": (CLEAN_PROMPT, False),
    "clean-stream":    (CLEAN_PROMPT, True),
    "heavy-nonstream": (HEAVY_PROMPT, False),
    "heavy-stream":    (HEAVY_PROMPT, True),
}


def check_proxy_alive() -> bool:
    try:
        r = httpx.get("http://localhost:47474/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


# --- Timing ----------------------------------------------------------------

@dataclass
class Sample:
    ttfb_ms: float
    total_ms: float
    output_tokens: int = 0


def _request_non_streaming(client, url, body, headers) -> Sample:
    t0 = time.perf_counter()
    r = client.post(url, json=body, headers=headers)
    elapsed = (time.perf_counter() - t0) * 1000
    if r.status_code != 200:
        raise RuntimeError(f"non-200 from {url}: {r.status_code} {r.text[:300]}")
    out = r.json().get("usage", {}).get("output_tokens", 0)
    return Sample(ttfb_ms=elapsed, total_ms=elapsed, output_tokens=out)


def _request_streaming(client, url, body, headers) -> Sample:
    t0 = time.perf_counter()
    ttfb = None
    output_tokens = 0
    with client.stream("POST", url, json=body, headers=headers) as r:
        if r.status_code != 200:
            raise RuntimeError(f"non-200 from {url}: {r.status_code} {r.read().decode()[:300]}")
        for line in r.iter_lines():
            if line and ttfb is None:
                ttfb = (time.perf_counter() - t0) * 1000
            if line.startswith("data: "):
                try:
                    payload = json.loads(line[6:])
                    if payload.get("type") == "message_delta":
                        output_tokens = payload.get("usage", {}).get("output_tokens", output_tokens)
                except Exception:
                    pass
    total = (time.perf_counter() - t0) * 1000
    return Sample(ttfb_ms=ttfb or total, total_ms=total, output_tokens=output_tokens)


# --- Stats -----------------------------------------------------------------

def _pct(xs, p):
    if not xs: return 0.0
    s = sorted(xs); k = (len(s) - 1) * (p / 100)
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _summary(label, samples):
    ttfb = [s.ttfb_ms for s in samples]
    total = [s.total_ms for s in samples]
    return {
        "label": label, "n": len(samples),
        "ttfb_mean": statistics.mean(ttfb), "ttfb_p50": _pct(ttfb, 50), "ttfb_p95": _pct(ttfb, 95),
        "total_mean": statistics.mean(total), "total_p50": _pct(total, 50), "total_p95": _pct(total, 95),
        "out_tokens_mean": statistics.mean([s.output_tokens for s in samples]) if samples else 0,
    }


def _table(rows):
    cols = ["label", "n", "ttfb_mean", "ttfb_p50", "ttfb_p95", "total_mean", "total_p50", "total_p95", "out_tokens_mean"]
    heads = ["case", "n", "ttfb-mean", "ttfb-p50", "ttfb-p95", "tot-mean", "tot-p50", "tot-p95", "out-tok"]
    fmt = lambda v: f"{v:.1f}" if isinstance(v, float) else str(v)
    widths = [max(len(h), max((len(fmt(r[c])) for r in rows), default=0)) for c, h in zip(cols, heads)]
    lines = [" | ".join(h.ljust(w) for h, w in zip(heads, widths)),
             "-+-".join("-" * w for w in widths)]
    for r in rows:
        lines.append(" | ".join(fmt(r[c]).ljust(w) for c, w in zip(cols, widths)))
    return "\n".join(lines)


# --- Run loop --------------------------------------------------------------

def _run_case(case_name: str, iters: int, warmup: int, headers: dict, model: str, max_tokens: int):
    prompt, stream = CASES[case_name]
    body = make_request_body(prompt, model=model, stream=stream, max_tokens=max_tokens)
    fn = _request_streaming if stream else _request_non_streaming

    with httpx.Client(timeout=60.0) as c:
        for _ in range(warmup):
            fn(c, DIRECT_URL, body, headers)
            fn(c, PROXY_URL,  body, headers)
        direct = [fn(c, DIRECT_URL, body, headers) for _ in range(iters)]
        proxy  = [fn(c, PROXY_URL,  body, headers) for _ in range(iters)]
    return _summary(f"{case_name} | direct", direct), _summary(f"{case_name} | proxy", proxy)


def parse_args(prog: str | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog=prog)
    ap.add_argument("--iters", type=int, default=5)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--case", choices=list(CASES) + ["all"], default="all")
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--max-tokens", type=int, default=256)
    return ap.parse_args()


def run_benchmark(build_headers: Callable[[], dict], args: argparse.Namespace) -> int:
    """Validate proxy is up, build auth headers via the provided callback, and run.

    Returns exit code (0 on success, non-zero on setup error).
    """
    if not check_proxy_alive():
        print("aivion-mask proxy not running on :47474. Start it: aivion-mask start", file=sys.stderr)
        return 1
    try:
        headers = build_headers()
    except SystemExit:
        raise
    except Exception as e:
        print(f"Failed to build auth headers: {e}", file=sys.stderr)
        return 1

    cases = list(CASES) if args.case == "all" else [args.case]
    total_calls = len(cases) * (args.iters + args.warmup) * 2
    print(f"Running {len(cases)} case(s), {total_calls} total API calls "
          f"(model={args.model}, max_tokens={args.max_tokens})\n", flush=True)

    rows = []
    for c in cases:
        print(f"[{c}] iters={args.iters} warmup={args.warmup} ...", flush=True)
        try:
            d, p = _run_case(c, args.iters, args.warmup, headers, args.model, args.max_tokens)
        except Exception as e:
            print(f"  ! {e}", file=sys.stderr)
            continue
        rows.append(d); rows.append(p)
        delta_ttfb  = p["ttfb_mean"]  - d["ttfb_mean"]
        delta_total = p["total_mean"] - d["total_mean"]
        pct = (delta_total / d["total_mean"]) * 100 if d["total_mean"] else 0.0
        print(f"  → ttfb {delta_ttfb:+.1f} ms, total {delta_total:+.1f} ms ({pct:+.1f}%)")

    if rows:
        print("\n" + _table(rows))
    return 0
