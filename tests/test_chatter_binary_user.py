import base64
import threading

import pytest

from serialterminal.profiles.chatter.binary_user import (
    BINARY_USER_MAX_BYTES,
    BinaryUserParseError,
    ChatterBinaryUserAdapter,
    encode_binary_command,
    parse_binary_rx_line,
    parse_binary_tx_line,
)


def _rx_line(payload: bytes) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"< [-42/7 Q99] [BINARY] {encoded}"


def _tx_line(payload: bytes) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"> [BINARY] {encoded}"


def test_binary_user_all_byte_values_roundtrip_without_utf8():
    for value in range(256):
        payload = bytes([value])
        command = encode_binary_command(payload)
        assert command == "/bin " + base64.b64encode(payload).decode("ascii")
        assert parse_binary_rx_line(_rx_line(payload)) == payload
        assert parse_binary_tx_line(_tx_line(payload)) == payload


def test_binary_user_243_byte_boundary_roundtrip():
    payload = bytes(range(243))
    command = encode_binary_command(payload)
    assert parse_binary_rx_line(_rx_line(payload)) == payload
    assert parse_binary_tx_line(_tx_line(payload)) == payload
    assert len(base64.b64decode(command.split(" ", 1)[1])) == 243
    assert BINARY_USER_MAX_BYTES == 243
    assert len(command) == 5 + 324


@pytest.mark.parametrize("size", [0, 244])
def test_binary_user_rejects_out_of_range_payload(size):
    with pytest.raises(ValueError):
        encode_binary_command(b"x" * size)


def test_invalid_binary_base64_is_distinguished_from_non_binary_line():
    assert parse_binary_rx_line("< hello") is None
    with pytest.raises(BinaryUserParseError):
        parse_binary_rx_line("< [-42/7 Q99] [BINARY] !!!!")


def test_binary_adapter_waits_for_matching_delivery_ack():
    holder = {}
    sent = []

    def send_line(text):
        sent.append(text)
        if text.startswith("/bin "):
            adapter = holder["adapter"]
            adapter.feed_line(
                "telemetry",
                "DELIVERY WAIT_ACK user=A001/7 attempt=1/5 timeout=10ms queue=0",
            )
            adapter.feed_line(
                "telemetry",
                "DELIVERY ACK user=BEEF/9 attempts=1/5 elapsed=1ms queue=0",
            )
            adapter.feed_line(
                "telemetry",
                "DELIVERY ACK user=A001/7 attempts=1/5 elapsed=2ms queue=0",
            )
        return {"tx_id": 17, "state": "queued"}

    adapter = ChatterBinaryUserAdapter(send_line)
    holder["adapter"] = adapter
    payload = b"\x00\x0a\x0d\x7f\x80\xff"

    result = adapter.send_binary(payload)

    assert result.tx_id == 17
    assert result.user_id == "A001/7"
    assert sent == [encode_binary_command(payload)]


def test_binary_adapter_feeds_exact_received_bytes():
    adapter = ChatterBinaryUserAdapter(lambda _text: {"tx_id": 1})
    received = []
    adapter.set_receiver(received.append)

    payload = b"\x00abc\xff\n\r"
    adapter.feed_line("chat", _rx_line(payload))

    assert received == [payload]


def test_binary_adapter_cancel_requests_firmware_cancel():
    sent = []
    cancel = threading.Event()
    cancel.set()
    adapter = ChatterBinaryUserAdapter(
        lambda text: sent.append(text) or {"tx_id": len(sent)},
    )

    with pytest.raises(Exception) as caught:
        adapter.send_binary(b"x", cancel_event=cancel)

    assert getattr(caught.value, "code", None) == "cancelled"
    assert sent[0].startswith("/bin ")
    assert sent[-1] == "/cancel all"



def test_binary_adapter_checks_local_tx_outcome_before_link_delivery():
    holder = {}
    waited = []

    def send_line(text):
        adapter = holder["adapter"]
        adapter.feed_line(
            "telemetry",
            "DELIVERY WAIT_ACK user=A001/7 attempt=1/5 timeout=10ms queue=0",
        )
        adapter.feed_line(
            "telemetry",
            "DELIVERY ACK user=A001/7 attempts=1/5 elapsed=2ms queue=0",
        )
        return {"tx_id": 42}

    adapter = ChatterBinaryUserAdapter(
        send_line,
        wait_tx_outcome=lambda tx_id, timeout: waited.append((tx_id, timeout))
        or "written",
        connection_generation=lambda: 5,
    )
    holder["adapter"] = adapter

    result = adapter.send_binary(b"abc")

    assert result.tx_id == 42
    assert waited and waited[0][0] == 42


def test_binary_adapter_reports_ambiguous_local_write():
    adapter = ChatterBinaryUserAdapter(
        lambda _text: {"tx_id": 9},
        wait_tx_outcome=lambda _tx_id, _timeout: "unknown",
        connection_generation=lambda: 1,
    )

    with pytest.raises(Exception) as caught:
        adapter.send_binary(b"abc")

    assert getattr(caught.value, "code", None) == "local_tx_unknown"


def test_binary_adapter_reports_disconnect_before_delivery_observation():
    generations = iter([10, 11])
    holder = {}

    def send_line(_text):
        holder["adapter"].feed_line(
            "telemetry",
            "DELIVERY WAIT_ACK user=A001/7 attempt=1/5 timeout=10ms queue=0",
        )
        return {"tx_id": 3}

    adapter = ChatterBinaryUserAdapter(
        send_line,
        wait_tx_outcome=lambda _tx_id, _timeout: "written",
        connection_generation=lambda: next(generations),
    )
    holder["adapter"] = adapter

    with pytest.raises(Exception) as caught:
        adapter.send_binary(b"abc")

    assert getattr(caught.value, "code", None) == "local_disconnect"



def test_binary_adapter_file_transfer_forces_both_and_restores_chat():
    holder = {}
    sent = []

    def send_line(text):
        sent.append(text)
        adapter = holder["adapter"]
        if text == "/both":
            adapter.feed_line("main", "[SYS] OUTPUT BOTH")
        elif text == "/chat":
            adapter.feed_line("main", "[SYS] OUTPUT CHAT")
        return {"tx_id": len(sent)}

    adapter = ChatterBinaryUserAdapter(
        send_line,
        wait_tx_outcome=lambda _tx_id, _timeout: "written",
    )
    holder["adapter"] = adapter

    adapter.begin_transfer()
    adapter.end_transfer()

    assert sent == ["/both", "/chat"]


def test_binary_adapter_file_transfer_restores_preexisting_telemetry_mode():
    holder = {}
    sent = []

    def send_line(text):
        sent.append(text)
        adapter = holder["adapter"]
        if text == "/both":
            adapter.feed_line("main", "[SYS] OUTPUT BOTH")
        elif text == "/tele":
            adapter.feed_line("main", "[SYS] OUTPUT TELEMETRY")
        return {"tx_id": len(sent)}

    adapter = ChatterBinaryUserAdapter(
        send_line,
        wait_tx_outcome=lambda _tx_id, _timeout: "written",
    )
    holder["adapter"] = adapter
    adapter.feed_line("main", "[SYS] OUTPUT TELEMETRY")

    adapter.begin_transfer()
    adapter.end_transfer()

    assert sent == ["/both", "/tele"]


def test_binary_adapter_reasserts_both_after_reconnect_during_transfer():
    holder = {}
    sent = []
    generation = {"value": 1}

    def send_line(text):
        sent.append(text)
        adapter = holder["adapter"]
        if text == "/both":
            adapter.feed_line("main", "[SYS] OUTPUT BOTH")
        elif text.startswith("/bin "):
            adapter.feed_line(
                "telemetry",
                "DELIVERY WAIT_ACK user=A001/7 attempt=1/5 timeout=10ms queue=0",
            )
            adapter.feed_line(
                "telemetry",
                "DELIVERY ACK user=A001/7 attempts=1/5 elapsed=2ms queue=0",
            )
        return {"tx_id": len(sent)}

    adapter = ChatterBinaryUserAdapter(
        send_line,
        wait_tx_outcome=lambda _tx_id, _timeout: "written",
        connection_generation=lambda: generation["value"],
    )
    holder["adapter"] = adapter

    adapter.begin_transfer()
    generation["value"] = 2
    result = adapter.send_binary(b"abc")

    assert result.user_id == "A001/7"
    assert sent[:3] == ["/both", "/both", encode_binary_command(b"abc")]
