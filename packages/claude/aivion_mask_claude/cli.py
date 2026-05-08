from __future__ import annotations
import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import httpx

from aivion_mask_core.auth import AUTH_TOKEN_PATH, get_or_create_token
from aivion_mask_core.config import AIVION_DIR, load_config

PID_FILE = AIVION_DIR / "sidecar.pid"
LOG_FILE = AIVION_DIR / "sidecar.log"


def _port() -> int:
    return load_config().sidecar.port


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except ValueError:
        return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _is_running() -> bool:
    pid = _read_pid()
    return pid is not None and _alive(pid)


def _wait_for_health(port: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.15)
    return False


def cmd_start(args) -> int:
    if _is_running():
        print(f"Already running (pid={_read_pid()})")
        return 0

    if getattr(args, "foreground", False):
        from .main import run
        run()
        return 0

    AIVION_DIR.mkdir(parents=True, exist_ok=True)
    log_fd = open(LOG_FILE, "a")
    self_path = shutil.which("aivion-mask") or sys.argv[0]
    proc = subprocess.Popen(
        [self_path, "start", "--foreground"],
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    if _wait_for_health(_port()):
        print(f"Started (pid={proc.pid}). Logs: {LOG_FILE}")
        return 0
    print(f"Started but health check failed. Check logs: {LOG_FILE}")
    return 1


def cmd_stop(args) -> int:
    pid = _read_pid()
    if pid is None or not _alive(pid):
        if PID_FILE.exists():
            PID_FILE.unlink()
        print("Not running.")
        return 0

    print(f"Stopping (pid={pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        print("Stopped.")
        return 0

    for _ in range(50):
        if not _alive(pid):
            PID_FILE.unlink(missing_ok=True)
            print("Stopped.")
            return 0
        time.sleep(0.1)

    print("Force killing...")
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    PID_FILE.unlink(missing_ok=True)
    print("Stopped.")
    return 0


def cmd_restart(args) -> int:
    cmd_stop(args)
    time.sleep(0.3)
    return cmd_start(args)


def cmd_status(args) -> int:
    if not _is_running():
        print("aivion-mask: not running")
        return 1
    pid = _read_pid()
    port = _port()
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
        info = r.json()
        print(f"aivion-mask: running (pid={pid}, version={info.get('version', '?')}, port={port})")
        return 0
    except Exception as exc:
        print(f"aivion-mask: pid file present (pid={pid}) but unreachable: {exc}")
        return 1


def cmd_logs(args) -> int:
    if not LOG_FILE.exists():
        print(f"No logs at {LOG_FILE}")
        return 1
    if args.follow:
        try:
            subprocess.run(["tail", "-f", str(LOG_FILE)])
        except KeyboardInterrupt:
            pass
        return 0
    print(LOG_FILE.read_text(), end="")
    return 0


def cmd_dashboard(args) -> int:
    if not _is_running():
        print("aivion-mask is not running. Start it first: aivion-mask start")
        return 1
    token = get_or_create_token()
    url = f"http://127.0.0.1:{_port()}/?token={token}"
    print(f"Opening {url}")
    webbrowser.open(url)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aivion-mask", description="Local credential masking proxy for Claude")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="Start the proxy (background by default)")
    p_start.add_argument("--foreground", action="store_true", help="Run in foreground (do not detach)")
    p_start.set_defaults(func=cmd_start)

    sub.add_parser("stop", help="Stop the running proxy").set_defaults(func=cmd_stop)
    sub.add_parser("restart", help="Restart the proxy").set_defaults(func=cmd_restart)
    sub.add_parser("status", help="Show whether the proxy is running").set_defaults(func=cmd_status)

    p_logs = sub.add_parser("logs", help="Print proxy logs")
    p_logs.add_argument("-f", "--follow", action="store_true", help="Follow new lines (tail -f)")
    p_logs.set_defaults(func=cmd_logs)

    sub.add_parser("dashboard", help="Open the dashboard in your browser").set_defaults(func=cmd_dashboard)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
