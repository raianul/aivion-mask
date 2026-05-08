"""Benchmark aivion-mask: mock-direct vs. via-proxy → mock.

Usage (from repo root):

    ~/.aivion-mask/venv/bin/python benchmarks/run.py
    ~/.aivion-mask/venv/bin/python benchmarks/run.py --iters 200 --warmup 20
    ~/.aivion-mask/venv/bin/python benchmarks/run.py --case heavy-stream-long

The proxy spawned here uses HOME=<tmp> so it does not collide with your
running aivion-mask instance on :47474.
"""
from __future__ import annotations
import argparse
import os
import statistics
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prompts import CLEAN_PROMPT, HEAVY_PROMPT, make_request_body  # noqa: E402

MOCK_PORT = 47475
PROXY_PORT = 47476
HEALTH_TIMEOUT = 8.0


# --- Process management ----------------------------------------------------

@contextmanager
def _spawn(cmd, env, name, health_url):
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + HEALTH_TIMEOUT
        while time.monotonic() < deadline:
            try:
                r = httpx.get(health_url, timeout=1.0)
                if r.status_code == 200:
                    break
            except Exception:
                pass
            if proc.poll() is not None:
                out, err = proc.communicate(timeout=1)
                raise RuntimeError(
                    f"{name} died before becoming healthy:\n"
                    f"stdout: {out.decode(errors='replace')}\n"
                    f"stderr: {err.decode(errors='replace')}"
                )
            time.sleep(0.1)
        else:
            raise RuntimeError(f"{name} did not become healthy at {health_url}")
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


# --- Timing primitives -----------------------------------------------------

@dataclass
class Sample:
    ttfb_ms: float
    total_ms: float


def _request_non_streaming(client: httpx.Client, url: str, body: dict, headers: dict) -> Sample:
    t0 = time.perf_counter()
    r = client.post(url, json=body, headers=headers)
    t1 = time.perf_counter()
    if r.status_code != 200:
        raise RuntimeError(f"non-200 from {url}: {r.status_code} {r.text[:200]}")
    # For non-streaming TTFB == total (we only see the response when it's complete).
    elapsed_ms = (t1 - t0) * 1000
    return Sample(ttfb_ms=elapsed_ms, total_ms=elapsed_ms)


def _request_streaming(client: httpx.Client, url: str, body: dict, headers: dict) -> Sample:
    t0 = time.perf_counter()
    ttfb_ms = None
    with client.stream("POST", url, json=body, headers=headers) as r:
        if r.status_code != 200:
            raise RuntimeError(f"non-200 from {url}: {r.status_code}")
        for chunk in r.iter_bytes():
            if chunk and ttfb_ms is None:
                ttfb_ms = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    total_ms = (t1 - t0) * 1000
    return Sample(ttfb_ms=ttfb_ms or total_ms, total_ms=total_ms)


# --- Stats -----------------------------------------------------------------

def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100)
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _summary(label: str, samples: list[Sample]) -> dict:
    ttfb = [s.ttfb_ms for s in samples]
    total = [s.total_ms for s in samples]
    return {
        "label": label,
        "n": len(samples),
        "ttfb_mean": statistics.mean(ttfb),
        "ttfb_stdev": statistics.stdev(ttfb) if len(ttfb) > 1 else 0.0,
        "ttfb_p50": _pct(ttfb, 50),
        "ttfb_p95": _pct(ttfb, 95),
        "total_mean": statistics.mean(total),
        "total_stdev": statistics.stdev(total) if len(total) > 1 else 0.0,
        "total_p50": _pct(total, 50),
        "total_p95": _pct(total, 95),
        "total_max": max(total),
    }


def _format_table(rows: list[dict]) -> str:
    cols = ["label", "n", "ttfb_mean", "ttfb_stdev", "ttfb_p95", "total_mean", "total_stdev", "total_p95", "total_max"]
    headers = ["case", "n", "ttfb-mean", "ttfb-sd", "ttfb-p95", "tot-mean", "tot-sd", "tot-p95", "tot-max"]
    widths = [max(len(h), max((len(_fmt(r[c])) for r in rows), default=0)) for c, h in zip(cols, headers)]
    out = []
    out.append(" | ".join(h.ljust(w) for h, w in zip(headers, widths)))
    out.append("-+-".join("-" * w for w in widths))
    for r in rows:
        out.append(" | ".join(_fmt(r[c]).ljust(w) for c, w in zip(cols, widths)))
    return "\n".join(out)


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


# --- Cases -----------------------------------------------------------------

CASES = {
    # name: (prompt, stream, response_size)
    "clean-nonstream-short":  (CLEAN_PROMPT, False, "short"),
    "clean-stream-short":     (CLEAN_PROMPT, True,  "short"),
    "heavy-nonstream-long":   (HEAVY_PROMPT, False, "long"),
    "heavy-stream-long":      (HEAVY_PROMPT, True,  "long"),
}


def _run_case(case_name: str, iters: int, warmup: int) -> tuple[dict, dict]:
    prompt, stream, _response_size = CASES[case_name]
    body = make_request_body(prompt, stream=stream)
    headers = {"x-api-key": "bench-fake-key", "anthropic-version": "2023-06-01"}

    direct_url = f"http://127.0.0.1:{MOCK_PORT}/v1/messages"
    proxy_url  = f"http://127.0.0.1:{PROXY_PORT}/v1/messages"
    fn = _request_streaming if stream else _request_non_streaming

    direct: list[Sample] = []
    proxied: list[Sample] = []

    with httpx.Client(timeout=30.0) as client:
        # Warmup: still alternates so neither side gets a colder cache.
        for i in range(warmup):
            if i % 2 == 0:
                fn(client, direct_url, body, headers)
                fn(client, proxy_url,  body, headers)
            else:
                fn(client, proxy_url,  body, headers)
                fn(client, direct_url, body, headers)
        # Measured iters: alternate the order pair-by-pair so position bias
        # (e.g. CPU thermal warmup, OS scheduler quirks) cancels out.
        for i in range(iters):
            if i % 2 == 0:
                direct.append(fn(client, direct_url, body, headers))
                proxied.append(fn(client, proxy_url,  body, headers))
            else:
                proxied.append(fn(client, proxy_url,  body, headers))
                direct.append(fn(client, direct_url, body, headers))

    return (
        _summary(f"{case_name} | direct", direct),
        _summary(f"{case_name} | proxy",  proxied),
    )


def _verify_unmask(case_name: str) -> None:
    """Send the heavy prompt through the proxy once and confirm originals come back.

    Catches the bug class where mock-response strings drift away from what
    `display_value()` actually produces, silently zeroing out the unmask path.
    """
    prompt, stream, _ = CASES[case_name]
    if "heavy" not in case_name:
        return
    body = make_request_body(prompt, stream=False)  # always non-stream for assertion
    headers = {"x-api-key": "bench-fake-key", "anthropic-version": "2023-06-01"}
    proxy_url = f"http://127.0.0.1:{PROXY_PORT}/v1/messages"
    r = httpx.post(proxy_url, json=body, headers=headers, timeout=10.0)
    if r.status_code != 200:
        raise RuntimeError(f"verify_unmask: non-200 from proxy: {r.status_code} {r.text[:200]}")
    text = "".join(b.get("text", "") for b in r.json().get("content", []))
    from prompts import HEAVY_SECRETS  # noqa: E402
    missing = [name for name, (_, raw) in HEAVY_SECRETS.items() if raw not in text]
    if missing:
        raise RuntimeError(
            f"verify_unmask: proxy did not restore original secrets: {missing}\n"
            f"Response excerpt: {text[:400]}\n"
            "Bench is broken — fix prompts.py before trusting numbers."
        )


# --- Main ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=100)
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--case", choices=list(CASES) + ["all"], default="all")
    args = ap.parse_args()

    cases_to_run = list(CASES) if args.case == "all" else [args.case]

    # Group cases by response size so we only need one mock per size.
    by_size: dict[str, list[str]] = {"short": [], "long": []}
    for c in cases_to_run:
        by_size[CASES[c][2]].append(c)

    all_rows: list[dict] = []
    tmp_home = tempfile.mkdtemp(prefix="aivion-mask-bench-")

    for size, cases in by_size.items():
        if not cases:
            continue
        mock_env = os.environ.copy()
        mock_env["MOCK_RESPONSE"] = size
        mock_env["MOCK_PORT"] = str(MOCK_PORT)
        mock_cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "mock_anthropic.py")]
        proxy_env = os.environ.copy()
        proxy_env["HOME"] = tmp_home
        proxy_env["ANTHROPIC_UPSTREAM"] = f"http://127.0.0.1:{MOCK_PORT}"
        proxy_env["BENCH_PORT"] = str(PROXY_PORT)
        proxy_cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "_launcher.py")]

        with _spawn(mock_cmd, mock_env, "mock", f"http://127.0.0.1:{MOCK_PORT}/health"):
            with _spawn(proxy_cmd, proxy_env, "proxy", f"http://127.0.0.1:{PROXY_PORT}/health"):
                for case in cases:
                    print(f"\n[{case}] iters={args.iters} warmup={args.warmup} ...", flush=True)
                    _verify_unmask(case)  # raises if heavy round-trip is broken
                    a, b = _run_case(case, args.iters, args.warmup)
                    all_rows.append(a)
                    all_rows.append(b)
                    delta_ttfb = b["ttfb_mean"] - a["ttfb_mean"]
                    delta_total = b["total_mean"] - a["total_mean"]
                    pct_total = (delta_total / a["total_mean"]) * 100 if a["total_mean"] else 0
                    print(
                        f"  → ttfb +{delta_ttfb:.2f} ms, total +{delta_total:.2f} ms ({pct_total:+.1f}%)"
                    )

    print("\n" + _format_table(all_rows))


if __name__ == "__main__":
    main()
