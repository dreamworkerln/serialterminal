"""Offline evidence: фиксирует поведение reviewed checkpoint, а не acceptance fixes."""
import curses

from serialterminal.file_transfer import DataMessage, FileTransferError, FileTransferManager
from serialterminal.tui_file_transfer import FileTransferWindow
from test_file_transfer_failure_retention import CaptureTransport, fixture
from test_tui_file_transfer_window import Canvas, make_tui, render, snapshot


def test_fresh_manager_has_no_f7_window(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    tui = make_tui()
    tui._file_transfer = manager
    try:
        assert not manager.busy and manager.display_snapshot() is None
        for _ in range(3):
            tui._handle_key(Canvas(), curses.KEY_F7, 10)
            canvas = Canvas()
            render(tui._file_window(), canvas, tui._file_snapshot())
            assert not canvas.calls and tui._file_header_lines(80) == ()
        print("CONTROL: fresh manager + F7 cannot create a transfer window")
    finally:
        manager.close()


def test_cancel_pending_can_return_through_header_and_f7():
    tui = make_tui(snapshot(direction="RX", state="receiving"))
    manager = tui._file_transfer
    manager.cancel = manager.cancelled.append
    tui._handle_key(Canvas(), "\x1b", 10)
    tui._handle_key(Canvas(), "\n", 10)
    assert not tui._file_window().visible
    assert len(tui._file_header_lines(80)) == 2
    tui._handle_key(Canvas(), curses.KEY_F7, 10)
    canvas = Canvas()
    render(tui._file_window(), canvas, tui._file_snapshot())
    assert tui._file_window().visible and canvas.calls
    print("OBSERVED: accepted asynchronous cancel hides window, shows DATA header, F7 reopens it")


def fail_and_resume(manager, meta, chunks):
    manager._handle_data(DataMessage(meta.transfer_id, 0, chunks[0]))
    manager._fail_incoming(
        manager._incoming_for(meta.transfer_id),
        FileTransferError("local_recovery_timeout", "offline injected failure"),
    )
    assert manager._outbox.wait_idle(2)
    assert not manager.busy and manager.display_snapshot()["state"] == "failed"


def test_old_confirmation_cancels_new_same_id_attempt(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    tui = make_tui()
    tui._file_transfer = manager
    try:
        meta, chunks, _ = fixture(manager, transfer_id=131)
        tui._handle_key(Canvas(), "\x1b", 10)
        assert tui._file_window().confirmation_id == "0000000000000083"
        fail_and_resume(manager, meta, chunks)
        tui._file_window().sync(manager.display_snapshot())
        manager._handle_meta(meta)
        assert manager._outbox.wait_idle(2)
        assert manager.busy and manager.display_snapshot()["state"] == "receiving"
        record = manager._records[meta.transfer_id]
        assert not record.cancel_event.is_set()
        tui._handle_key(Canvas(), "\n", 10)
        assert record.cancel_event.is_set()
        print("OBSERVED: confirmation from failed attempt cancels resumed RX with same transfer_id")
    finally:
        manager.close()


def test_dismissed_same_id_attempt_does_not_auto_open_on_readmission(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    tui = make_tui()
    tui._file_transfer = manager
    try:
        meta, chunks, _ = fixture(manager, transfer_id=133)
        tui._file_window().sync(manager.display_snapshot())
        fail_and_resume(manager, meta, chunks)
        tui._handle_key(Canvas(), "\x1b", 10)
        assert not tui._file_window().visible
        manager._handle_meta(meta)
        assert manager._outbox.wait_idle(2)
        assert manager.busy and manager.display_snapshot()["state"] == "receiving"
        tui._file_window().sync(manager.display_snapshot())
        assert not tui._file_window().visible
        print("OBSERVED: re-admitted same-ID RX inherits dismissed previous attempt visibility")
    finally:
        manager.close()


def test_nonterminal_history_is_treated_as_active(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    tui = make_tui()
    tui._file_transfer = manager
    meta, _, _ = fixture(manager, transfer_id=135)
    tui._file_window().sync(manager.display_snapshot())
    manager.close()
    assert not manager.busy
    value = manager.display_snapshot()
    assert value["transfer_id"] == f"{meta.transfer_id:016x}" and value["state"] == "suspended"
    tui._handle_key(Canvas(), curses.KEY_F7, 10)
    tui._handle_key(Canvas(), curses.KEY_F7, 10)
    assert tui._file_window().visible and tui._file_transfer_active()
    print("BOUNDARY: closed manager suspended history passes F7 and action-admission active checks")
    print("LIMIT: normal TUI close detaches manager; this alone does not reproduce node reboot")


def test_missing_snapshot_leaves_invisible_confirmation():
    window = FileTransferWindow()
    window.request_cancel(snapshot())
    canvas = Canvas()
    render(window, canvas, None)
    assert not canvas.calls and window.confirmation_id is not None
    assert window.handle_key("x", None) == (True, None)
    print("BOUNDARY: snapshot None hides confirmation but it still consumes ordinary keys")
