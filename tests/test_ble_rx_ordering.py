import queue
import threading

from serialterminal.transports.base import ReceivedChunk
from serialterminal.transports.ble_nus import BleNusTransport


def _bare_transport():
    transport = object.__new__(BleNusTransport)
    transport._rx_queue = queue.Queue()
    transport._rx_pending = None
    transport.read_timeout = 0.01
    transport._connected = threading.Event()
    transport._connected.set()
    transport._default_stream = "main"
    transport.target_name = "ordering-test"
    return transport


def test_split_tail_stays_before_later_notification():
    transport = _bare_transport()
    transport._rx_queue.put(ReceivedChunk("primary", b"abcdef"))
    transport._rx_queue.put(ReceivedChunk("secondary", b"XYZ"))

    first = transport.read_chunk(4)
    second = transport.read_chunk(4)
    third = transport.read_chunk(4)

    assert (first.stream, first.data) == ("primary", b"abcd")
    assert (second.stream, second.data) == ("primary", b"ef")
    assert (third.stream, third.data) == ("secondary", b"XYZ")


def test_oversized_notification_keeps_order_across_more_than_two_fragments():
    transport = _bare_transport()
    transport._rx_queue.put(ReceivedChunk("chat", b"ABCDEFGHIJ"))
    transport._rx_queue.put(ReceivedChunk("telemetry", b"later"))

    chunks = [transport.read_chunk(3) for _ in range(5)]

    assert [(chunk.stream, chunk.data) for chunk in chunks] == [
        ("chat", b"ABC"),
        ("chat", b"DEF"),
        ("chat", b"GHI"),
        ("chat", b"J"),
        ("telemetry", b"lat"),
    ]
    assert transport.read_chunk(3) == ReceivedChunk("telemetry", b"er")
