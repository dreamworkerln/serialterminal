from __future__ import annotations

import codecs
from collections import deque
from dataclasses import dataclass
import queue
import threading
import time
from typing import Callable, Iterable

from .transports.base import ReceivedChunk, Transport, TransportError


ConnectPreamble = Callable[[Transport], bytes | None]
EventNotifier = Callable[[], None]


def encode_line(line: str, line_ending: str = "\n") -> bytes:
    return (line + line_ending).encode("utf-8")


class SessionClosedError(RuntimeError):
    """Raised when new work is submitted to a stopped managed session."""


class SessionCursorExpired(RuntimeError):
    """Raised when an event cursor points before the retained event window."""

    def __init__(self, requested_seq: int, oldest_seq: int):
        super().__init__(
            f"event cursor {requested_seq} expired; oldest available seq is {oldest_seq}"
        )
        self.requested_seq = requested_seq
        self.oldest_seq = oldest_seq


@dataclass(frozen=True)
class SessionEvent:
    seq: int
    kind: str
    timestamp: float
    state: str | None = None
    stream: str | None = None
    data: bytes | None = None
    text: str | None = None
    tx_id: int | None = None
    tx_state: str | None = None
    error: str | None = None
    device_key: str | None = None
    description: str | None = None


class _QueuedLine(str):
    """Queue item that preserves string compatibility for existing callers/tests."""

    def __new__(
        cls,
        text: str,
        *,
        tx_id: int,
        data: bytes,
    ) -> _QueuedLine:
        value = str.__new__(cls, text)
        value.tx_id = tx_id
        value.data = data
        return value


class _QueuedBytes(bytes):
    def __new__(cls, data: bytes, *, tx_id: int) -> _QueuedBytes:
        value = bytes.__new__(cls, data)
        value.tx_id = tx_id
        value.data = bytes(data)
        return value


QueuedTx = _QueuedLine | _QueuedBytes


class ManagedSession:
    """Headless reconnecting session shared by human and machine frontends."""

    def __init__(
        self,
        transport: Transport,
        *,
        line_ending: str = "\n",
        reconnect_delay: float = 0.5,
        connect_preamble: ConnectPreamble | None = None,
        event_limit: int = 4096,
        event_notifier: EventNotifier | None = None,
    ):
        if event_limit <= 0:
            raise ValueError("event_limit must be positive")

        self.transport = transport
        self.line_ending = line_ending
        self.reconnect_delay = reconnect_delay
        self.connect_preamble = connect_preamble
        self.event_notifier = event_notifier

        self.stop_event = threading.Event()
        self.connected_event = threading.Event()
        self.connection_paused = threading.Event()
        self.transport_lock = threading.Lock()
        self.outgoing: queue.Queue[QueuedTx] = queue.Queue()

        self._event_limit = event_limit
        self._events: deque[SessionEvent] = deque(maxlen=event_limit)
        self._event_condition = threading.Condition()
        self._next_event_seq = 1
        self._next_tx_id = 1
        self._tx_id_lock = threading.Lock()
        self._event_decode_lock = threading.Lock()
        self._event_decoders: dict[str, codecs.IncrementalDecoder] = {}

        self._thread_lock = threading.Lock()
        self._rx_thread: threading.Thread | None = None
        self._tx_thread: threading.Thread | None = None

    def _current_transport(self) -> Transport:
        with self.transport_lock:
            return self.transport

    def _next_tx(self) -> int:
        with self._tx_id_lock:
            tx_id = self._next_tx_id
            self._next_tx_id += 1
            return tx_id

    def _record_event(self, kind: str, **fields) -> SessionEvent:
        with self._event_condition:
            event = SessionEvent(
                seq=self._next_event_seq,
                kind=kind,
                timestamp=time.time(),
                **fields,
            )
            self._next_event_seq += 1
            self._events.append(event)
            self._event_condition.notify_all()

        notifier = self.event_notifier
        if notifier is not None:
            # Внешний wakeup вызывается только после освобождения session condition:
            # manager-level waiter может держать свой condition и читать event ring
            # без обратного порядка блокировок и без второго буфера событий.
            notifier()
        return event

    def _decode_event_text(self, stream: str, data: bytes) -> str:
        if not data:
            return ""
        with self._event_decode_lock:
            decoder = self._event_decoders.get(stream)
            if decoder is None:
                decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
                self._event_decoders[stream] = decoder
            return decoder.decode(data, final=False)

    def _reset_event_decoders(self) -> None:
        with self._event_decode_lock:
            self._event_decoders.clear()

    def latest_event_seq(self) -> int:
        with self._event_condition:
            return self._next_event_seq - 1

    def events_after(
        self,
        after_seq: int = 0,
        *,
        timeout: float = 0.0,
        streams: Iterable[str] | None = None,
        kinds: Iterable[str] | None = None,
    ) -> list[SessionEvent]:
        """Return retained events after a cursor, optionally waiting for a match."""
        if after_seq < 0:
            raise ValueError("after_seq must be non-negative")
        if timeout < 0:
            raise ValueError("timeout must be non-negative")

        stream_filter = set(streams) if streams is not None else None
        kind_filter = set(kinds) if kinds is not None else None
        deadline = time.monotonic() + timeout

        with self._event_condition:
            while True:
                if self._events:
                    oldest_seq = self._events[0].seq
                    if after_seq < oldest_seq - 1:
                        raise SessionCursorExpired(after_seq, oldest_seq)

                result = [
                    event
                    for event in self._events
                    if event.seq > after_seq
                    and (kind_filter is None or event.kind in kind_filter)
                    and (stream_filter is None or event.stream in stream_filter)
                ]
                if result or timeout == 0:
                    return result

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return []
                self._event_condition.wait(timeout=remaining)

    def wait_connected(self, timeout: float | None = None) -> bool:
        return self.connected_event.wait(timeout=timeout)

    def queue_line(self, line: str, *, line_ending: str | None = None) -> int:
        if self.stop_event.is_set():
            raise SessionClosedError("managed session is stopped")
        tx_id = self._next_tx()
        ending = self.line_ending if line_ending is None else line_ending
        item = _QueuedLine(line, tx_id=tx_id, data=encode_line(line, ending))
        self.outgoing.put(item)
        self._record_event(
            "tx",
            tx_id=tx_id,
            tx_state="queued",
            data=item.data,
            text=str(item),
            device_key=self._current_transport().device_key,
        )
        return tx_id

    def queue_bytes(self, data: bytes) -> int:
        if self.stop_event.is_set():
            raise SessionClosedError("managed session is stopped")
        tx_id = self._next_tx()
        item = _QueuedBytes(bytes(data), tx_id=tx_id)
        self.outgoing.put(item)
        self._record_event(
            "tx",
            tx_id=tx_id,
            tx_state="queued",
            data=item.data,
            device_key=self._current_transport().device_key,
        )
        return tx_id

    def on_waiting(self) -> None:
        """Frontend hook called once for each disconnected retry interval."""

    def on_connected(self, transport: Transport) -> None:
        """Frontend hook called after transport connect and connect preamble."""

    def on_received(self, chunk: ReceivedChunk) -> None:
        """Frontend hook called after an RX event is recorded."""

    def on_disconnected(self, description: str, error: str | None) -> None:
        """Frontend hook called for an unexpected/send-failure disconnect."""

    def on_tx_written(self, item: QueuedTx) -> None:
        """Frontend hook called after one queued item is written to transport."""

    def on_send_failed(self, error: str | None) -> None:
        """Frontend hook called before retrying the same TX item after reconnect."""

    def _connect(self) -> bool:
        if self.connection_paused.is_set() or self.stop_event.is_set():
            return False

        transport = self._current_transport()
        if not transport.connect():
            return False

        if (
            self.connection_paused.is_set()
            or self.stop_event.is_set()
            or transport is not self._current_transport()
        ):
            transport.disconnect()
            return False

        if self.connect_preamble is not None:
            try:
                preamble = self.connect_preamble(transport)
                if preamble:
                    transport.write(preamble)
                    self._record_event(
                        "tx",
                        tx_state="connect-preamble-written",
                        data=preamble,
                        device_key=transport.device_key,
                        description=transport.description,
                    )
            except (TransportError, OSError) as exc:
                transport.disconnect()
                self._record_event(
                    "error",
                    error=str(exc),
                    state="connect-preamble-failed",
                    device_key=transport.device_key,
                    description=transport.description,
                )
                return False

        self._reset_event_decoders()
        self.connected_event.set()
        self._record_event(
            "state",
            state="connected",
            device_key=transport.device_key,
            description=transport.description,
        )
        self.on_connected(transport)
        return True

    def _disconnect(self, error: str | None = None) -> None:
        transport = self._current_transport()
        description = transport.description
        self.connected_event.clear()
        transport.disconnect()
        self._reset_event_decoders()
        self._record_event(
            "state",
            state="disconnected",
            error=error,
            device_key=transport.device_key,
            description=description,
        )
        self.on_disconnected(description, error)

    def rx_loop(self) -> None:
        waiting_printed = False

        while not self.stop_event.is_set():
            if self.connection_paused.is_set():
                time.sleep(0.05)
                continue

            if not self.connected_event.is_set():
                if not waiting_printed:
                    self._record_event(
                        "state",
                        state="reconnecting",
                        device_key=self._current_transport().device_key,
                        description=self._current_transport().description,
                    )
                    self.on_waiting()
                    waiting_printed = True

                if self._connect():
                    waiting_printed = False
                else:
                    time.sleep(self.reconnect_delay)
                    continue

            transport = self._current_transport()
            try:
                chunk = transport.read_chunk(512)
                if not chunk.data:
                    continue
                text = self._decode_event_text(chunk.stream, chunk.data)
                self._record_event(
                    "rx",
                    stream=chunk.stream,
                    data=chunk.data,
                    text=text,
                    device_key=transport.device_key,
                    description=transport.description,
                )
                self.on_received(chunk)
            except (TransportError, OSError) as exc:
                if self.stop_event.is_set():
                    break
                self._disconnect(str(exc))
                time.sleep(0.3)

    def tx_loop(self) -> None:
        """Write queued line/raw items in order, retrying the current item after reconnect."""
        while not self.stop_event.is_set():
            try:
                item = self.outgoing.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                while not self.stop_event.is_set():
                    if not self.connected_event.wait(timeout=0.1):
                        continue

                    try:
                        transport = self._current_transport()
                        transport.write(item.data)
                        self._record_event(
                            "tx",
                            tx_id=item.tx_id,
                            tx_state="written",
                            data=item.data,
                            text=str(item) if isinstance(item, _QueuedLine) else None,
                            device_key=transport.device_key,
                            description=transport.description,
                        )
                        self.on_tx_written(item)
                        break
                    except (TransportError, OSError) as exc:
                        self._disconnect(str(exc))
                        self._record_event(
                            "error",
                            error=str(exc),
                            state="send-failed",
                            tx_id=item.tx_id,
                            device_key=self._current_transport().device_key,
                        )
                        self.on_send_failed(str(exc))
                        time.sleep(self.reconnect_delay)
            finally:
                self.outgoing.task_done()

    def start(self) -> None:
        with self._thread_lock:
            if self.stop_event.is_set():
                raise SessionClosedError("managed session cannot be restarted after stop")
            if self._rx_thread is not None and self._rx_thread.is_alive():
                return

            self._rx_thread = threading.Thread(
                target=self.rx_loop,
                name=f"serialterminal-rx-{id(self):x}",
                daemon=True,
            )
            self._tx_thread = threading.Thread(
                target=self.tx_loop,
                name=f"serialterminal-tx-{id(self):x}",
                daemon=True,
            )
            self._rx_thread.start()
            self._tx_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.connection_paused.clear()
        self.connected_event.clear()

        rx = self._rx_thread
        tx = self._tx_thread
        if rx is not None:
            rx.join(timeout=1.0)
        if tx is not None:
            tx.join(timeout=1.0)

        self._current_transport().close()
        self._reset_event_decoders()
        self._record_event(
            "state",
            state="closed",
            device_key=self._current_transport().device_key,
            description=self._current_transport().description,
        )

    close = stop