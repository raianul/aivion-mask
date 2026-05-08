"""Boot the aivion-mask Claude proxy with the upstream pointed at the mock.

Designed to run as a subprocess from run.py. Reads HOME (set by parent),
ANTHROPIC_UPSTREAM, and BENCH_PORT from the environment before importing
the proxy modules so all path/URL constants resolve to bench-local values.
"""
from __future__ import annotations
import logging
import os
import sys

UPSTREAM = os.environ["ANTHROPIC_UPSTREAM"]
PORT = int(os.environ.get("BENCH_PORT", "47476"))

# Patch the upstream constant before main imports it.
import aivion_mask_claude.anthropic as _anth  # noqa: E402
_anth.ANTHROPIC_UPSTREAM = UPSTREAM

# Write a minimal config.toml at the bench HOME so the proxy listens on PORT
# and skips response unmasking only if the user asks (via env).
from aivion_mask_core.config import AIVION_DIR  # noqa: E402

AIVION_DIR.mkdir(parents=True, exist_ok=True)
unmask = "true" if os.environ.get("BENCH_UNMASK", "1") == "1" else "false"
(AIVION_DIR / "config.toml").write_text(
    f"[sidecar]\nport = {PORT}\nsession_ttl_hours = 8\nunmask_response = {unmask}\n"
)

import uvicorn  # noqa: E402

logging.basicConfig(level=logging.WARNING)
sys.stderr.write(f"[launcher] proxy on :{PORT} → {UPSTREAM}, HOME={os.environ.get('HOME')}\n")
uvicorn.run("aivion_mask_claude.main:app", host="127.0.0.1", port=PORT, log_level="warning")
