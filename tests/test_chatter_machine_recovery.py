"""Восстановление local M1 после временно занятого owner; без радио/USB/BLE."""
import threading
import time

import pytest

from serialterminal.file_transfer.transport import BinaryUserError
from serialterminal.profiles.chatter.machine_codec import Frame, Kind, decode, encode
from test_chatter_machine_client import setup_node


def busy_node(monkeypatch):
    client, node = setup_node()
    busy = threading.Event()
    busy.set()
    send = node.send

    def respond(text):
        frame = decode(text.lstrip("\n"))
        if frame.kind == Kind.HELLO and busy.is_set():
            node.frames.append(frame)
            client.feed_line("chat", encode(Frame(Kind.REJECTED, 0, frame.request, b"\x01")).decode())
            return {"tx_id": len(node.frames)}
        return send(text)

    client.legacy._send_line = respond
    negotiate = client._negotiate

    def short_negotiate(deadline, cancel_event=None):
        return negotiate(min(deadline, time.monotonic() + .03), cancel_event)

    monkeypatch.setattr(client, "_negotiate", short_negotiate)
    return client, node, busy


def wait_for(predicate):
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.002)
    pytest.fail("machine state did not change within bounded wait")


def test_busy_hello_reports_owner_timeout_not_expired_write(monkeypatch):
    client, node, busy = busy_node(monkeypatch)
    try:
        with pytest.raises(BinaryUserError) as caught:
            client._ready(time.monotonic() + .03)
        assert caught.value.code == "machine_owner_busy"
        assert all(frame.kind == Kind.HELLO for frame in node.frames)
    finally:
        client.close()


def test_explicit_send_retries_failed_bootstrap_without_duplicate_rf(monkeypatch):
    client, node, busy = busy_node(monkeypatch)
    try:
        client.start()
        wait_for(lambda: client.mode == "failed")
        assert not client.pending
        busy.clear()
        receipt = client.send_binary(b"new FT1 META")
        assert receipt.tx_id is not None
        assert client.mode == "machine"
        assert sum(frame.kind == Kind.SUBMIT for frame in node.frames) == 1
        assert not client.pending
    finally:
        client.close()


def test_idle_receiver_recovers_failed_bootstrap_without_file_send(monkeypatch):
    client, node, busy = busy_node(monkeypatch)
    received = []
    client.set_receiver(received.append)
    try:
        client.start()
        wait_for(lambda: client.mode == "failed")
        busy.clear()
        wait_for(lambda: client.mode == "machine")
        client.feed_line("chat", encode(Frame(Kind.RX, node.epoch, 0, b"remote FT1 META")).decode())
        assert received == [b"remote FT1 META"]
        assert not any(frame.kind == Kind.SUBMIT for frame in node.frames)
    finally:
        client.close()


@pytest.mark.parametrize("code", ["machine_version_mismatch", "local_tx_unsettled"])
def test_fatal_machine_state_does_not_negotiate_around_error(code):
    client, node = setup_node()
    try:
        client.mode = "failed"
        client.error = BinaryUserError(code, "must remain visible")
        with pytest.raises(BinaryUserError) as caught:
            client.send_binary(b"blocked")
        assert caught.value.code == code
        assert not node.frames
    finally:
        client.close()


def test_busy_error_with_pending_ticket_cannot_release_old_submission():
    client, node = setup_node()
    try:
        node.drop_link = True
        ticket = client.submit_binary(b"unresolved RF")
        count = len(node.frames)
        client.mode = "failed"
        client.error = BinaryUserError("machine_owner_busy", "old submission remains")
        with pytest.raises(BinaryUserError):
            client.send_binary(b"blocked")
        assert client.pending[ticket.request] is ticket
        assert len(node.frames) == count
    finally:
        client.close()


def test_nonbusy_hello_rejection_is_not_automatically_retried():
    client, node = setup_node()

    def reject(text):
        frame = decode(text.lstrip("\n"))
        node.frames.append(frame)
        client.feed_line("chat", encode(Frame(Kind.REJECTED, 0, frame.request, b"\x04")).decode())
        return {"tx_id": len(node.frames)}

    client.legacy._send_line = reject
    try:
        with pytest.raises(BinaryUserError):
            client._ready(time.monotonic() + .1)
        before = len(node.frames)
        with pytest.raises(BinaryUserError):
            client.send_binary(b"invalid negotiation must stay blocked")
        assert len(node.frames) == before
        assert all(frame.kind == Kind.HELLO for frame in node.frames)
    finally:
        client.close()
