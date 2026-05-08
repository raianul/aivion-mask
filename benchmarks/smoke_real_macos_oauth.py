"""Smoke-test aivion-mask against api.anthropic.com using a Claude Code OAuth token.

This is a **sanity probe**, not a performance benchmark. Use it to confirm the
proxy works end-to-end against the real Anthropic API (auth, streaming, error
handling) — not to measure latency. The numbers are too noisy to cite. For the
defensible proxy-overhead measurement, run `run.py` against the local mock.

macOS only — reads the token from the keychain entry "Claude Code-credentials"
that Claude Code creates on first login. Token stays in process memory; never
written to disk or logged.

For Linux / non-Claude-Code users, see smoke_real_api_key.py instead.

Each iteration costs real tokens. Defaults: Haiku, max_tokens=256, --iters 5.

Usage:
    ~/.aivion-mask/venv/bin/python benchmarks/smoke_real_macos_oauth.py
    ~/.aivion-mask/venv/bin/python benchmarks/smoke_real_macos_oauth.py --iters 10 --case heavy-stream
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _runner import parse_args, run_benchmark  # noqa: E402


def _build_headers() -> dict:
    raw = subprocess.check_output(
        ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
        text=True,
    ).strip()
    oauth = json.loads(raw)["claudeAiOauth"]
    token = oauth["accessToken"]
    expires_at = int(oauth.get("expiresAt", 0))
    if expires_at and expires_at < int(time.time() * 1000):
        print("WARNING: OAuth token appears expired. Run Claude Code once to refresh.", file=sys.stderr)
    # OAuth tokens require this beta header to authenticate against /v1/messages.
    return {
        "Authorization": f"Bearer {token}",
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "oauth-2025-04-20",
        "Content-Type": "application/json",
    }


if __name__ == "__main__":
    sys.exit(run_benchmark(_build_headers, parse_args(prog="smoke_real_macos_oauth.py")))
