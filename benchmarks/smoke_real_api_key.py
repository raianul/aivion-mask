"""Smoke-test aivion-mask against api.anthropic.com using an Anthropic API key.

This is a **sanity probe**, not a performance benchmark. Use it to confirm the
proxy works end-to-end against the real Anthropic API (auth, streaming, error
handling) — not to measure latency. The numbers are too noisy to cite. For the
defensible proxy-overhead measurement, run `run.py` against the local mock.

Reads ANTHROPIC_API_KEY from the environment. Cross-platform — works anywhere
the proxy and Python run. For Claude Code subscription users without an API key,
see smoke_real_macos_oauth.py instead.

Each iteration costs real tokens. Defaults: Haiku, max_tokens=256, --iters 5.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-api03-...
    ~/.aivion-mask/venv/bin/python benchmarks/smoke_real_api_key.py
    ~/.aivion-mask/venv/bin/python benchmarks/smoke_real_api_key.py --iters 10 --case heavy-stream
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _runner import parse_args, run_benchmark  # noqa: E402


def _build_headers() -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("ANTHROPIC_API_KEY is not set. Export your API key first.", file=sys.stderr)
        sys.exit(1)
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


if __name__ == "__main__":
    sys.exit(run_benchmark(_build_headers, parse_args(prog="smoke_real_api_key.py")))
