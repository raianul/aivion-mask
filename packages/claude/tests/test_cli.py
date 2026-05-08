import os
from unittest.mock import patch

from aivion_mask_claude import cli


def test_read_pid_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "PID_FILE", tmp_path / "missing.pid")
    assert cli._read_pid() is None


def test_read_pid_returns_int(tmp_path, monkeypatch):
    pidfile = tmp_path / "sidecar.pid"
    pidfile.write_text("12345\n")
    monkeypatch.setattr(cli, "PID_FILE", pidfile)
    assert cli._read_pid() == 12345


def test_read_pid_handles_garbage(tmp_path, monkeypatch):
    pidfile = tmp_path / "sidecar.pid"
    pidfile.write_text("not-a-number")
    monkeypatch.setattr(cli, "PID_FILE", pidfile)
    assert cli._read_pid() is None


def test_alive_self():
    assert cli._alive(os.getpid()) is True


def test_alive_dead():
    # PID 1 might be alive; pick something extremely unlikely
    assert cli._alive(2_147_483_646) is False


def test_is_running_false_when_no_pid_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "PID_FILE", tmp_path / "no.pid")
    assert cli._is_running() is False


def test_is_running_false_when_stale_pid(tmp_path, monkeypatch):
    pidfile = tmp_path / "sidecar.pid"
    pidfile.write_text("2147483646")
    monkeypatch.setattr(cli, "PID_FILE", pidfile)
    assert cli._is_running() is False


def test_main_dispatches_status_when_not_running(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "PID_FILE", tmp_path / "no.pid")
    rc = cli.main(["status"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "not running" in out


def test_main_dispatches_stop_when_not_running(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "PID_FILE", tmp_path / "no.pid")
    rc = cli.main(["stop"])
    assert rc == 0
    assert "Not running" in capsys.readouterr().out


def test_main_dashboard_refuses_when_not_running(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "PID_FILE", tmp_path / "no.pid")
    rc = cli.main(["dashboard"])
    assert rc == 1
    assert "not running" in capsys.readouterr().out


def test_cmd_start_handles_restart_args_namespace(tmp_path, monkeypatch):
    """Regression: restart reuses argparse namespace from `restart`, which has no --foreground."""
    monkeypatch.setattr(cli, "PID_FILE", tmp_path / "no.pid")
    monkeypatch.setattr(cli, "_wait_for_health", lambda *_: True)

    class FakePopen:
        def __init__(self, *a, **kw):
            self.pid = 42

    monkeypatch.setattr(cli.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(cli.shutil, "which", lambda *_: "/usr/bin/aivion-mask")

    import argparse
    args = argparse.Namespace(cmd="restart")  # no `foreground` attr
    rc = cli.cmd_start(args)
    assert rc == 0
