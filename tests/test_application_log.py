from pathlib import Path
import subprocess
import sys
import threading

import pytest

from serialterminal.application_log import ApplicationLog, error_snapshot, report_exception
from serialterminal import cli


def test_error_traceback_is_written_and_fsynced_before_shutdown(tmp_path, monkeypatch):
    synced = []
    monkeypatch.setattr("serialterminal.application_log.os.fsync", lambda fd: synced.append(fd))
    with ApplicationLog(tmp_path / "app.log") as log:
        try:
            raise ValueError("original failure")
        except ValueError as exc:
            assert report_exception(exc, "test action") == log.path
        content = log.path.read_text()
        assert "Traceback (most recent call last)" in content
        assert "ValueError: original failure" in content
        assert error_snapshot() == (1, "ValueError: original failure", log.path)
        assert synced
    assert error_snapshot() == (0, "", None)


def test_cli_fatal_error_and_ctrl_c_have_no_console_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    def fail(argv):
        raise RuntimeError("main failed")
    monkeypatch.setattr(cli, "_dispatch_main", fail)
    assert cli.main([]) == 1
    stderr = capsys.readouterr().err
    assert "Application log:" in stderr
    assert "Traceback" not in stderr
    assert any("RuntimeError: main failed" in p.read_text() for p in (tmp_path / "logs").glob("*.log"))
    def interrupt(argv):
        raise KeyboardInterrupt()
    monkeypatch.setattr(cli, "_dispatch_main", interrupt)
    assert cli.main([]) == 130
    assert not capsys.readouterr().err


def test_unhandled_thread_error_is_logged_without_stderr_traceback(tmp_path, capsys):
    previous = threading.excepthook
    with ApplicationLog(tmp_path / "app.log") as log:
        def fail():
            raise RuntimeError("thread failed")
        thread = threading.Thread(target=fail, name="broken-worker")
        thread.start()
        thread.join()
        assert log.error_count == 1
        assert "thread:broken-worker" in log.path.read_text()
        assert "RuntimeError: thread failed" in log.path.read_text()
        assert "Traceback" not in capsys.readouterr().err
    assert threading.excepthook is previous


@pytest.mark.parametrize("basename", ["test.log", "capture", "capture.data"])
def test_agent_creates_all_four_logs_in_explicit_directory(tmp_path, basename):
    root = Path(__file__).resolve().parents[1]
    working = tmp_path / "unrelated-cwd"
    working.mkdir()
    directory = tmp_path / "experiment" / "nested"
    log_path = directory / basename
    result = subprocess.run(
        [sys.executable, str(root / "serialterminal.py"), "agent", "--log", str(log_path)],
        input="", capture_output=True, text=True, cwd=working, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    stem = basename[:-4] if basename.endswith(".log") else basename
    assert {p.name for p in directory.iterdir()} == {
        basename, f"{stem}.console.log", f"{stem}.fttiming.jsonl", f"{stem}.application.log",
    }
    app_text = (directory / f"{stem}.application.log").read_text()
    assert "START pid=" in app_text
    assert "STOP" in app_text
    assert log_path.stat().st_size > 0
    assert (directory / f"{stem}.fttiming.jsonl").stat().st_size > 0
    assert not (working / "logs").exists()


@pytest.mark.parametrize("mode", [[], ["auto"], ["serial"], ["ble"], ["spp"], ["agent"]])
@pytest.mark.parametrize("joined", [False, True])
def test_explicit_log_routes_startup_errors_for_every_frontend(tmp_path, monkeypatch, mode, joined):
    directory = tmp_path / "run"
    log_path = directory / "test.log"
    argv = [*mode, *([f"--log={log_path}"] if joined else ["--log", str(log_path)])]
    def fail(args):
        assert args == argv
        raise RuntimeError("startup failure")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_dispatch_main", fail)
    assert cli.main(argv) == 1
    assert "RuntimeError: startup failure" in (directory / "test.application.log").read_text()
    assert not (tmp_path / "logs").exists()


def test_log_selection_respects_last_option_and_option_terminator(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_dispatch_main", lambda args: 0)
    assert cli.main(["agent", "--log", "old.log", "--log=chosen.log"]) == 0
    assert (tmp_path / "chosen.application.log").exists()
    assert not (tmp_path / "old.application.log").exists()
    assert cli.main(["--", "--log=not-an-option.log"]) == 0
    assert not (tmp_path / "not-an-option.application.log").exists()
    assert list((tmp_path / "logs").glob("serialterminal-application-*.log"))


def test_application_log_open_failure_does_not_fall_back_to_cwd(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "blocked").write_text("file, not directory")
    monkeypatch.setattr(cli, "_dispatch_main", lambda args: pytest.fail("frontend must not start"))
    assert cli.main(["agent", "--log", "blocked/test.log"]) == 1
    assert "could not open application log" in capsys.readouterr().err
    assert not (tmp_path / "logs").exists()
