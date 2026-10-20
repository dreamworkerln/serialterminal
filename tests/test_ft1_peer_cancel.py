"""Отмена между двумя настоящими FT1 managers без физических transport."""
import random
import threading

import pytest

from serialterminal.file_transfer import (
    BinarySendReceipt, BinaryUserCancelled, DataMessage, FileTransferManager,
    ResultMessage, decode_message, encode_message,
)
from test_file_transfer_failure_retention import CaptureTransport, fixture, wait_until
from test_ft1_recursive_missing import Wire
from test_tui_file_transfer_window import Canvas, make_tui, render


class PausedWire(Wire):
    def __init__(self, *, pause=False, drop_cancel=False, **kwargs):
        super().__init__(**kwargs)
        self.pause = pause
        self.drop_cancel = drop_cancel
        self.entered = threading.Event()
        self.release = threading.Event()

    def send_binary(self, payload, *, cancel_event=None):
        message = decode_message(payload)
        if self.drop_cancel and isinstance(message, ResultMessage) and message.code == "cancelled":
            self.messages.append(message)
            return BinarySendReceipt(len(self.messages))
        if self.pause and isinstance(message, DataMessage):
            self.entered.set()
            while not self.release.wait(.005):
                if cancel_event is not None and cancel_event.is_set():
                    raise BinaryUserCancelled()
        return super().send_binary(payload, cancel_event=cancel_event)


def attach_tui(manager):
    tui = make_tui()
    tui._file_transfer = manager
    manager.event_sink = lambda event: tui._log_file_transfer_event(event, manager=manager)
    return tui


def draw(tui):
    canvas = Canvas()
    render(tui._file_window(), canvas, tui._file_snapshot())
    return "\n".join(call[2] for call in canvas.calls)


@pytest.mark.parametrize("initiator", ["TX", "RX"])
@pytest.mark.parametrize("repair", [False, True])
def test_cancel_closes_initiator_retains_stopped_peer_and_logs_once(tmp_path, initiator, repair):
    source = tmp_path / "ERROR-source.bin"
    source.write_bytes(random.Random(41).randbytes(227 * 12))
    left = PausedWire(pause=not repair, holes={2} if repair else ())
    right = PausedWire(pause=repair)
    left.peer, right.peer = right, left
    tx = FileTransferManager(left, receive_dir=tmp_path / "tx", resume_handshake_timeout_s=.02)
    rx = FileTransferManager(right, receive_dir=tmp_path / "rx", resume_handshake_timeout_s=.02)
    uis = {"TX": attach_tui(tx), "RX": attach_tui(rx)}
    try:
        started = tx.start_send(source)
        assert (right if repair else left).entered.wait(2)
        assert wait_until(lambda: rx.display_snapshot() is not None)
        for tui in uis.values():
            assert "Передача файла" in draw(tui)
        local, peer = uis[initiator], uis["RX" if initiator == "TX" else "TX"]
        local._handle_key(Canvas(), "\x1b", 10)
        assert local._file_window().confirmation_id == started["transfer_id"]
        local._handle_key(Canvas(), "\n", 10)
        assert not local._file_window().visible
        assert local._file_window().confirmation_id is None
        assert wait_until(lambda: all(m.display_snapshot()["state"] == "cancelled" and not m.busy for m in (tx, rx)))
        assert tx._outbox.wait_idle(1) and rx._outbox.wait_idle(1)
        assert "Передача файла" not in draw(local)
        peer_text = draw(peer)
        assert "Передача файла" in peer_text
        origin = "отправителем" if initiator == "TX" else "получателем"
        assert "отменено " + origin in peer_text
        assert peer._file_snapshot()["presentation"]["cancelled_by_peer"]
        peer._handle_key(Canvas(), "\x1b", 10)
        assert not peer._file_window().visible and peer._file_window().confirmation_id is None
        assert "Передача файла" not in draw(peer)
        for role, tui in uis.items():
            lines = [line for line in tui.output.snapshot() if line.startswith("[FT1]") and ": отменена " in line]
            assert len(lines) == 1
            assert "отменена " + ("пользователем" if role == initiator else origin) in lines[0]
            assert tui._line_attr(lines[0], {"normal": 17}) == 17
            assert not tui.sent
        root_id = int(started["transfer_id"], 16)
        notices = [m for w in (left, right) for m in w.messages
                   if isinstance(m, ResultMessage) and m.transfer_id == root_id and m.code == "cancelled"]
        assert len(notices) == 1
        assert not list((tmp_path / "rx").glob("ERROR-source*"))
        # После cleanup следующий ROOT получает свои окна и завершается,
        # несмотря на закрытые окна и сохранённый исход прежней отмены.
        left.pause, right.pause = True, False
        left.entered.clear()
        restarted = tx.start_send(source)
        assert restarted["transfer_id"] != started["transfer_id"]
        assert left.entered.wait(2)
        assert wait_until(lambda: rx.display_snapshot()["transfer_id"] == restarted["transfer_id"])
        for tui in uis.values():
            assert "Передача файла" in draw(tui)
            assert tui._file_window().confirmation_id is None
        left.release.set()
        assert wait_until(lambda: all(m.display_snapshot()["state"] == "completed" and not m.busy for m in (tx, rx)))
        assert (tmp_path / "rx" / source.name).read_bytes() == source.read_bytes()
        for tui in uis.values():
            draw(tui)
            assert tui._file_window().transfer_id == restarted["transfer_id"]
            assert tui._file_window().confirmation_id is None
            assert not tui._file_window().visible
            assert not tui.sent
    finally:
        left.release.set()
        right.release.set()
        tx.close()
        rx.close()


@pytest.mark.parametrize("initiator", ["TX", "RX"])
def test_lost_cancel_notice_leaves_manual_peer_confirmation(tmp_path, initiator):
    source = tmp_path / "payload.bin"
    source.write_bytes(random.Random(14).randbytes(227 * 3))
    left = PausedWire(pause=True, drop_cancel=initiator == "TX")
    right = PausedWire(drop_cancel=initiator == "RX")
    left.peer, right.peer = right, left
    tx = FileTransferManager(left, receive_dir=tmp_path / "tx", resume_handshake_timeout_s=.02)
    rx = FileTransferManager(right, receive_dir=tmp_path / "rx", resume_handshake_timeout_s=.02)
    local, peer = (tx, rx) if initiator == "TX" else (rx, tx)
    try:
        tx.start_send(source)
        assert left.entered.wait(2)
        assert wait_until(lambda: rx.display_snapshot() is not None)
        local.cancel(local.display_snapshot()["transfer_id"])
        assert wait_until(lambda: local.display_snapshot()["state"] == "cancelled" and not local.busy)
        assert peer.display_snapshot()["state"] in {"sending", "receiving"}
        tui = attach_tui(peer)
        draw(tui)
        tui._handle_key(Canvas(), "\x1b", 10)
        assert tui._file_window().confirmation_id is not None
        tui._handle_key(Canvas(), "\n", 10)
        assert not tui._file_window().visible
        assert wait_until(lambda: peer.display_snapshot()["state"] == "cancelled" and not peer.busy)
    finally:
        left.release.set()
        tx.close()
        rx.close()


@pytest.mark.parametrize("direction", ["TX", "RX"])
def test_duplicate_peer_cancel_is_idempotent_and_never_echoed(tmp_path, direction):
    source = tmp_path / "payload.bin"
    source.write_bytes(random.Random(14).randbytes(227 * 3))
    left, right = PausedWire(pause=True), PausedWire()
    left.peer, right.peer = right, left
    tx = FileTransferManager(left, receive_dir=tmp_path / "tx", resume_handshake_timeout_s=.02)
    rx = FileTransferManager(right, receive_dir=tmp_path / "rx", resume_handshake_timeout_s=.02)
    manager = tx if direction == "TX" else rx
    tui = attach_tui(manager)
    try:
        started = tx.start_send(source)
        assert left.entered.wait(2)
        assert wait_until(lambda: rx.display_snapshot() is not None)
        draw(tui)
        payload = encode_message(ResultMessage(int(started["transfer_id"], 16), False, "cancelled", ""), 243)
        for _ in range(10):
            manager.feed_binary(payload)
        assert wait_until(lambda: manager.display_snapshot()["state"] == "cancelled" and not manager.busy)
        manager.feed_binary(payload)
        assert manager._outbox.wait_idle(1)
        draw(tui)
        assert tui._file_window().visible
        lines = [line for line in tui.output.snapshot() if ": отменена " in line]
        assert len(lines) == 1
        assert not any(isinstance(m, ResultMessage) and m.code == "cancelled"
                       for wire in (left, right) for m in wire.messages)
    finally:
        left.release.set()
        tx.close()
        rx.close()


def test_unknown_or_late_cancel_cannot_erase_completed_file(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    try:
        meta, chunks, end = fixture(manager)
        manager.feed_binary(encode_message(ResultMessage(meta.transfer_id + 1, False, "cancelled", ""), 243))
        assert not manager._records[meta.transfer_id].cancel_event.is_set()
        for index, chunk in enumerate(chunks):
            manager._handle_data(DataMessage(meta.transfer_id, index, chunk))
        manager._handle_end(end)
        assert wait_until(lambda: manager._records[meta.transfer_id].state == "completed")
        manager.feed_binary(encode_message(ResultMessage(meta.transfer_id, False, "cancelled", ""), 243))
        assert manager._records[meta.transfer_id].state == "completed"
        assert (tmp_path / meta.filename).read_bytes() == b"".join(chunks)
    finally:
        manager.close()
