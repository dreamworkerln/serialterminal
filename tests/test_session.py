import queue
import time

import pytest

from serialterminal.session import (
    ManagedSession,
    SessionCursorExpired,
)
from serialterminal.transports.base import ReceivedChunk, Transport, TransportError


class FakeTransport(Transport):
    def __init__(self, *, fail_writes=0, streams=("main",)):
        self.connected = False
        self.fail_writes = fail_writes
        self.connect_count = 0
        self.disconnect_count = 0
        self.writes = []
        self.reads = queue.Queue()
        self._streams = streams

    @property
    def is_connected(self):
        return self.connected

    @property
    def description(self):
        return "fake-device"

    @property
    def device_key(self):
        return "fake:device"

    @property
    def stream_capabilities(self):
        return self._streams

    def connect(self):
        self.connect_count += 1
        self.connected = True
        return True

    def disconnect(self):
        self.disconnect_count += 1
        self.connected = False

    def read_chunk(self, size=512):
        if not self.connected:
            raise TransportError("not connected")
        try:
            return self.reads.get(timeout=0.02)
        except queue.Empty:
            return ReceivedChunk(self._streams[0], b"")

    def read(self, size=512):
        return self.read_chunk(size).data

    def write(self, data):
        if not self.connected:
            raise TransportError("not connected")
        if self.fail_writes:
            self.fail_writes -= 1
            self.connected = False
            raise TransportError("injected write failure")
        self.writes.append(bytes(data))


def _wait_until(predicate, timeout=1.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_connect_preamble_is_written_before_connected_state():
    transport = FakeTransport()
    session = ManagedSession(
        transport,
        connect_preamble=lambda _transport: b"/id\n",
    )

    assert session._connect()
    assert transport.writes == [b"/id\n"]

    events = session.events_after(0)
    assert [(event.kind, event.tx_state, event.state) for event in events] == [
        ("tx", "connect-preamble-written", None),
        ("state", None, "connected"),
    ]


def test_reconnect_safe_tx_retries_current_item_and_preserves_order():
    transport = FakeTransport(fail_writes=1)
    session = ManagedSession(transport, reconnect_delay=0.01)
    first = session.queue_line("one")
    second = session.queue_line("two")

    session.start()
    try:
        assert _wait_until(lambda: transport.writes == [b"one\n", b"two\n"])
        assert transport.connect_count >= 2

        written = [
            event
            for event in session.events_after(0, kinds=["tx"])
            if event.tx_state == "written"
        ]
        assert [event.tx_id for event in written] == [first, second]
        assert [event.data for event in written] == [b"one\n", b"two\n"]
    finally:
        session.stop()


def test_rx_events_preserve_stream_and_incremental_utf8_text():
    transport = FakeTransport(streams=("chat", "telemetry"))
    session = ManagedSession(transport, reconnect_delay=0.01)
    letter = "ж".encode("utf-8")

    session.start()
    try:
        assert session.wait_connected(1.0)
        cursor = session.latest_event_seq()
        transport.reads.put(ReceivedChunk("chat", letter[:1]))
        transport.reads.put(ReceivedChunk("telemetry", b"T\n"))
        transport.reads.put(ReceivedChunk("chat", letter[1:] + b"\n"))

        assert _wait_until(
            lambda: len(session.events_after(cursor, kinds=["rx"])) >= 3
        )
        events = session.events_after(cursor, kinds=["rx"])
        assert [event.stream for event in events] == [
            "chat",
            "telemetry",
            "chat",
        ]
        assert events[0].text == ""
        assert events[1].text == "T\n"
        assert events[2].text == "ж\n"
        assert b"".join(
            event.data for event in events if event.stream == "chat"
        ) == letter + b"\n"
    finally:
        session.stop()


def test_events_after_waits_for_new_matching_event():
    transport = FakeTransport()
    session = ManagedSession(transport)
    cursor = session.latest_event_seq()

    started = time.monotonic()
    assert session.events_after(cursor, timeout=0.03, kinds=["rx"]) == []
    assert time.monotonic() - started >= 0.02


def test_event_cursor_reports_expired_retention_window():
    transport = FakeTransport()
    session = ManagedSession(transport, event_limit=2)
    session.queue_line("one")
    session.queue_line("two")
    session.queue_line("three")

    with pytest.raises(SessionCursorExpired) as caught:
        session.events_after(0)

    assert caught.value.oldest_seq == 2


def test_raw_bytes_share_same_reconnect_safe_tx_queue():
    transport = FakeTransport()
    session = ManagedSession(transport, reconnect_delay=0.01)
    tx_id = session.queue_bytes(b"\x14\x31")

    session.start()
    try:
        assert _wait_until(lambda: transport.writes == [b"\x14\x31"])
        written = [
            event
            for event in session.events_after(0, kinds=["tx"])
            if event.tx_id == tx_id and event.tx_state == "written"
        ]
        assert len(written) == 1
        assert written[0].data == b"\x14\x31"
    finally:
        session.stop()
