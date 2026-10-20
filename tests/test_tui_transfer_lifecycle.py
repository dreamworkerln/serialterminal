"""Контракт окна на реальных FT1 admission/recovery/settlement без устройств."""
from contextlib import contextmanager
import curses
import threading

import pytest

from serialterminal.file_transfer import BinaryUserError, DataMessage, FileTransferError, FileTransferManager, ResumeMessage
from serialterminal.profiles.chatter.binary_user import ChatterBinaryUserAdapter
from serialterminal.tui_file_transfer import FileTransferWindow
from test_file_transfer_failure_retention import CaptureTransport, fixture, wait_until
from test_tui_file_transfer_window import Canvas, make_tui, render, snapshot


@contextmanager
def receiver(tmp_path):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path, local_recovery_retry_s=.001)
    tui = make_tui()
    tui._file_transfer = manager
    manager.event_sink = lambda event: tui._log_file_transfer_event(event, manager=manager)
    try:
        meta, chunks, end = fixture(manager, transfer_id=131)
        tui._file_window().sync(tui._file_snapshot())
        yield tui, manager, transport, meta, chunks, end
    finally:
        manager.close()


def fail_receiver(manager, meta):
    manager._fail_incoming(manager._incoming_for(meta.transfer_id),
                           FileTransferError("local_recovery_timeout", "offline injected failure"))
    assert manager._outbox.wait_idle(2)
    assert not manager.busy and manager.display_snapshot()["state"] == "failed"


def text(tui):
    canvas = Canvas()
    render(tui._file_window(), canvas, tui._file_snapshot())
    return "\n".join(call[2] for call in canvas.calls)


def test_boot_markers_without_transfer_never_enable_f7(tmp_path):
    adapter = ChatterBinaryUserAdapter(lambda line: {"tx_id": 1})
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    tui = make_tui()
    tui._file_transfer, tui._binary_adapter = manager, adapter
    try:
        for line in ("ESP-ROM:esp32s3-20210327", "[SYS] CHATTER READY") * 3:
            adapter.feed_line("chat", line)
            tui._handle_key(Canvas(), curses.KEY_F7, 10)
            assert tui._file_snapshot() is None
            assert "Передача файла" not in text(tui)
    finally:
        manager.close()


@pytest.mark.parametrize("state", ["suspended", "sending", "recovering_local_node", "unknown"])
@pytest.mark.parametrize("presentation", [{"active": False, "attempt": "old"}, {}])
def test_unowned_history_cannot_open_window_or_block_input(state, presentation):
    tui = make_tui(snapshot(state=state, presentation=presentation))
    tui._file_transfer.busy = False
    for _ in range(3):
        tui._handle_key(Canvas(), curses.KEY_F7, 10)
        assert not tui._file_transfer_active()
        assert text(tui) == "" and tui._file_header_lines(80) == ()


def test_old_confirmation_cannot_cancel_reopened_same_id(tmp_path):
    with receiver(tmp_path) as (tui, manager, _, meta, _, _):
        tui._handle_key(Canvas(), "\x1b", 10)
        fail_receiver(manager, meta)
        tui._file_window().sync(tui._file_snapshot())
        manager._handle_meta(meta)
        assert manager._outbox.wait_idle(2)
        assert manager.busy and manager.display_snapshot()["state"] == "receiving"
        assert "Операция завершилась или изменилась" in text(tui)
        tui._handle_key(Canvas(), "\n", 10)
        assert not manager._records[meta.transfer_id].cancel_event.is_set()
        assert not tui.sent and tui._file_window().confirmation_id is None
        assert tui._file_window().visible


def test_cancel_checks_attempt_atomically_after_ui_validation(tmp_path):
    with receiver(tmp_path) as (tui, manager, _, meta, _, _):
        previous = tui._file_snapshot()["presentation"]["attempt"]
        fail_receiver(manager, meta)
        manager._handle_meta(meta)
        assert manager._outbox.wait_idle(2)
        with pytest.raises(FileTransferError, match="attempt has changed"):
            manager.cancel(meta.transfer_id, expected_attempt=previous)
        assert not manager._records[meta.transfer_id].cancel_event.is_set()


def test_reopened_same_id_opens_after_dismissed_failure(tmp_path):
    with receiver(tmp_path) as (tui, manager, _, meta, _, _):
        previous = tui._file_snapshot()["presentation"]["attempt"]
        fail_receiver(manager, meta)
        tui._handle_key(Canvas(), "\x1b", 10)
        assert not tui._file_window().visible
        manager._handle_meta(meta)
        assert manager._outbox.wait_idle(2)
        assert tui._file_snapshot()["presentation"]["attempt"] != previous
        assert "Передача файла" in text(tui)


def test_cancel_pending_closes_window_and_cannot_be_confirmed_again(tmp_path):
    with receiver(tmp_path) as (tui, manager, transport, meta, _, _):
        entered, proceed = threading.Event(), threading.Event()
        def drain(timeout):
            entered.set()
            assert proceed.wait(3)
            return {}
        transport.drain_binary = drain
        try:
            tui._handle_key(Canvas(), "\x1b", 10)
            tui._handle_key(Canvas(), "\n", 10)
            assert entered.wait(2)
            assert manager.busy
            assert "Передача файла" not in text(tui)
            for key in (curses.KEY_F7, curses.KEY_F6, "\x1b"):
                tui._handle_key(Canvas(), key, 10)
                assert not tui._file_window().visible
                assert tui._file_window().confirmation_id is None
                assert tui._file_header_lines(80) == ()
        finally:
            proceed.set()
        assert manager._outbox.wait_idle(2)
        assert manager.display_snapshot()["state"] == "cancelled"
        assert "Передача файла" not in text(tui)
        tui._handle_key(Canvas(), curses.KEY_F7, 10)
        assert "Передача файла" not in text(tui)


def test_real_local_recovery_between_redraws_restores_foreground(tmp_path):
    with receiver(tmp_path) as (tui, manager, transport, meta, chunks, _):
        tui._handle_key(Canvas(), curses.KEY_F7, 10)
        manager._handle_data(DataMessage(meta.transfer_id, 0, chunks[0]))
        assert "Передача файла" not in text(tui)
        count = 0
        def reset_once(message):
            nonlocal count
            count += 1
            if count == 1:
                raise BinaryUserError("local_controller_reset", "offline reset")
        transport.on_send = reset_once
        record = manager._records[meta.transfer_id]
        manager._send_message(ResumeMessage(meta.transfer_id, 0), cancel_event=record.cancel_event)
        assert count == 2 and record.state == "receiving"
        assert "Передача файла" in text(tui)
        tui._handle_key(Canvas(), curses.KEY_F7, 10)
        for _ in range(3):
            assert "Передача файла" not in text(tui)
        chat = "\n".join(tui.output.snapshot())
        assert "восстановление связи" in chat and "передача возобновлена" in chat


def test_rx_boot_ready_needs_real_ft1_activity_to_restore_window(tmp_path):
    with receiver(tmp_path) as (tui, manager, _, meta, chunks, _):
        adapter = ChatterBinaryUserAdapter(lambda line: {"tx_id": 1})
        adapter.feed_line("chat", "[SYS] CHATTER READY")
        tui._binary_adapter = adapter
        text(tui)
        tui._handle_key(Canvas(), curses.KEY_F7, 10)
        adapter.feed_line("chat", "ESP-ROM:esp32s3-20210327")
        assert "Передача файла" not in text(tui)
        assert any("восстановление связи с нодой" in line for line in tui._file_header_lines(100))
        adapter.feed_line("chat", "[SYS] CHATTER READY")
        assert "Передача файла" not in text(tui)
        manager._handle_data(DataMessage(meta.transfer_id, 0, chunks[0]))
        assert "Передача файла" in text(tui)


@pytest.mark.parametrize("foreground", [False, True])
@pytest.mark.parametrize("outcome", ["completed", "failed", "cancelled"])
def test_terminal_window_policy_and_chat(tmp_path, foreground, outcome):
    with receiver(tmp_path) as (tui, manager, _, meta, chunks, end):
        if not foreground:
            tui._handle_key(Canvas(), curses.KEY_F7, 10)
        if outcome == "completed":
            for index, chunk in enumerate(chunks):
                manager._handle_data(DataMessage(meta.transfer_id, index, chunk))
            manager._handle_end(end)
        elif outcome == "failed":
            fail_receiver(manager, meta)
        else:
            manager.cancel(meta.transfer_id)
        assert wait_until(lambda: manager.display_snapshot()["state"] == outcome)
        assert manager._outbox.wait_idle(2)
        value = manager.display_snapshot()
        assert value["state"] == outcome and not tui._file_transfer_active()
        assert ("Передача файла" in text(tui)) == (foreground and outcome != "completed")
        assert tui._file_header_lines(80) == ()
        tui._handle_key(Canvas(), "\x1b", 10)
        for _ in range(2):
            tui._handle_key(Canvas(), curses.KEY_F7, 10)
            assert "Передача файла" not in text(tui)
        expected = {"completed": "успешно", "failed": "ошибка", "cancelled": "отменена пользователем"}[outcome]
        assert sum(expected in line for line in tui.output.snapshot()) == 1


def test_confirmation_remains_visible_if_snapshot_disappears():
    view = FileTransferWindow()
    view.request_cancel(snapshot())
    canvas = Canvas()
    render(view, canvas, None)
    assert any("Операция завершилась или изменилась" in call[2] for call in canvas.calls)
    assert view.handle_key("\n", None) == (True, None)
    assert view.confirmation_id is None


def test_background_is_one_line_with_shortened_name_and_no_second_bar():
    tui = make_tui(snapshot(filename="界" * 120 + ".bin"))
    tui._handle_key(Canvas(), curses.KEY_F7, 10)
    lines = tui._file_header_lines(80)
    assert len(lines) == 1
    assert "40.0%" in lines[0] and "kbit/s" in lines[0] and "F7: подробнее" in lines[0]
    assert "█" not in lines[0] and "chunks" not in lines[0] and "wire bytes" not in lines[0]


def test_late_queued_cancel_cannot_target_new_attempt(tmp_path):
    with receiver(tmp_path) as (tui, manager, _, meta, _, _):
        previous = tui._file_snapshot()["presentation"]["attempt"]
        fail_receiver(manager, meta)
        manager._handle_meta(meta)
        assert manager._outbox.wait_idle(2)
        manager._cancel_incoming(meta.transfer_id, expected_attempt=previous)
        assert manager.display_snapshot()["state"] == "receiving" and manager.busy


def test_same_id_new_attempt_resets_wire_rate():
    tui = make_tui()
    first = snapshot(bytes_completed=0, presentation={"attempt": "first"})
    tui._file_wire_rate_kbit_s(first, now=10)
    first["bytes_completed"] = 1000
    assert tui._file_wire_rate_kbit_s(first, now=11) == 8
    retried = snapshot(bytes_completed=1000, presentation={"attempt": "retry"})
    assert tui._file_wire_rate_kbit_s(retried, now=12) == 0


def test_new_admission_replaces_old_root_before_sender_worker_starts(tmp_path, monkeypatch):
    with receiver(tmp_path) as (tui, manager, _, meta, _, _):
        fail_receiver(manager, meta)
        source = tmp_path / "new.bin"
        source.write_bytes(b"new file")
        # Останавливаем только scheduling boundary; admission остаётся production.
        entered, proceed = threading.Event(), threading.Event()
        original = manager._send_worker
        def worker(record, path):
            entered.set()
            assert proceed.wait(3)
            original(record, path)
        monkeypatch.setattr(manager, "_send_worker", worker)
        admitted = manager.start_send(source)
        try:
            assert entered.wait(2)
            current = manager.presentation_snapshot()
            assert current["transfer_id"] == admitted["transfer_id"] != f"{meta.transfer_id:016x}"
            assert current["state"] == "preparing" and current["presentation"]["active"]
            assert "new.bin" in text(tui)
        finally:
            manager.cancel(admitted["transfer_id"])
            proceed.set()
            manager.join_all(2)


def test_runtime_window_identity_does_not_leak_into_agent_snapshots(tmp_path):
    with receiver(tmp_path) as (tui, manager, _, meta, _, _):
        assert "presentation" in tui._file_snapshot()
        assert "presentation" not in manager.display_snapshot()
        assert "presentation" not in manager.observe(meta.transfer_id)["progress"]
        assert all("presentation" not in value for value in manager.snapshots())
