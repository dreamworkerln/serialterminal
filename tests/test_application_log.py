import threading

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
