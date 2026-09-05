import queue
import time

import pytest

from serialterminal.session import ManagedSession, SessionCursorExpired
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


def test_rx_events_preserve_stream_and_incremental_utf8_text_and_lines():
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

        raw, lines = session.observation_after(cursor)
        assert raw == events
        assert [(line.stream, line.text) for line in lines] == [
            ("telemetry", "T"),
            ("chat", "ж"),
        ]
        chat = lines[1]
        assert chat.seq_first == events[0].seq
        assert chat.seq_last == events[2].seq
    finally:
        session.stop()


def test_completed_line_can_start_before_observation_cursor():
    session = ManagedSession(FakeTransport())
    first = session._record_event(
        "rx",
        stream="main",
        data=b"DELIVERY WA",
        text="DELIVERY WA",
    )

    raw, lines = session.observation_after(0)
    assert raw == [first]
    assert lines == []
    cursor = first.seq

    second = session._record_event(
        "rx",
        stream="main",
        data=b"IT_ACK\n",
        text="IT_ACK\n",
    )
    raw, lines = session.observation_after(cursor)

    assert raw == [second]
    assert len(lines) == 1
    assert lines[0].seq_first == first.seq
    assert lines[0].seq_last == second.seq
    assert lines[0].text == "DELIVERY WAIT_ACK"


def test_lines_keep_streams_independent_and_normalize_only_line_view():
    session = ManagedSession(FakeTransport(streams=("chat", "telemetry")))
    chat = session._record_event(
        "rx",
        stream="chat",
        data=b"chat\r\n\n",
        text="chat\r\n\n",
    )
    telemetry = session._record_event(
        "rx",
        stream="telemetry",
        data=b"telemetry\n",
        text="telemetry\n",
    )

    raw, lines = session.observation_after(0)
    assert [event.data for event in raw] == [b"chat\r\n\n", b"telemetry\n"]
    assert [(line.stream, line.text, line.seq_first, line.seq_last) for line in lines] == [
        ("chat", "chat", chat.seq, chat.seq),
        ("chat", "", chat.seq, chat.seq),
        ("telemetry", "telemetry", telemetry.seq, telemetry.seq),
    ]


def test_utf8_split_empty_text_chunk_still_sets_line_seq_first():
    session = ManagedSession(FakeTransport())
    first = session._record_event(
        "rx",
        stream="main",
        data=b"\xe2",
        text="",
    )
    second = session._record_event(
        "rx",
        stream="main",
        data=b"\x82\xac\n",
        text="€\n",
    )

    _, lines = session.observation_after(0)
    assert len(lines) == 1
    assert lines[0].text == "€"
    assert lines[0].seq_first == first.seq
    assert lines[0].seq_last == second.seq


def test_disconnect_clears_incomplete_line_before_next_connection():
    transport = FakeTransport()
    session = ManagedSession(transport)
    transport.connected = True
    before = session._record_event(
        "rx",
        stream="main",
        data=b"before",
        text="before",
    )

    session._disconnect("test disconnect")
    assert session._connect()
    after = session._record_event(
        "rx",
        stream="main",
        data=b"after\n",
        text="after\n",
    )

    _, lines = session.observation_after(before.seq)
    assert [(line.text, line.seq_first, line.seq_last) for line in lines] == [
        ("after", after.seq, after.seq)
    ]


def test_line_retention_follows_raw_cursor_window():
    session = ManagedSession(FakeTransport(), event_limit=3)
    first = session._record_event("rx", stream="main", data=b"a", text="a")
    second = session._record_event("rx", stream="main", data=b"\n", text="\n")
    session._record_event("state", state="one")
    session._record_event("state", state="two")

    raw, lines = session.observation_after(first.seq)
    assert raw
    assert [(line.seq_first, line.seq_last, line.text) for line in lines] == [
        (first.seq, second.seq, "a")
    ]

    session._record_event("state", state="three")
    with pytest.raises(SessionCursorExpired):
        session.observation_after(first.seq)


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
