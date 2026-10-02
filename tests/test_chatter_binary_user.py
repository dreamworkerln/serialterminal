import base64
import threading

import pytest

from serialterminal.file_transfer import FileTransferManager
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


def test_binary_adapter_timing_marks_submit_write_presentation_and_return():
    holder = {}
    events = []

    def timing(event, **fields):
        events.append((event, fields))

    def send_line(text):
        if text.startswith("/bin "):
            holder["adapter"].feed_line("chat", _tx_line(b"payload"))
        return {"tx_id": 17, "state": "queued"}

    adapter = ChatterBinaryUserAdapter(
        send_line,
        wait_tx_outcome=lambda _tx_id, _timeout: "written",
        timing_sink=timing,
    )
    holder["adapter"] = adapter
    adapter.feed_line("main", "[SYS] current=CHAT")

    receipt = adapter.send_binary(b"payload")

    assert receipt.tx_id == 17
    names = [name for name, _fields in events]
    assert names.index("binary_submit") < names.index("binary_tx_queued")
    assert names.index("binary_tx_queued") < names.index("binary_tx_written")
    assert names.index("binary_tx_written") < names.index("binary_presentation_match")
    assert names.index("binary_presentation_match") < names.index("binary_return")
    presentation = next(
        fields for name, fields in events if name == "binary_presentation_line"
    )
    assert presentation["binary_seq"] == 1


def test_binary_adapter_settles_on_exact_local_presentation_without_telemetry():
    holder = {}
    sent = []

    def send_line(text):
        sent.append(text)
        if text.startswith("/bin "):
            adapter = holder["adapter"]
            adapter.feed_line("chat", _tx_line(b"other"))
            adapter.feed_line("chat", _tx_line(b"payload"))
        return {"tx_id": 17, "state": "queued"}

    adapter = ChatterBinaryUserAdapter(send_line)
    holder["adapter"] = adapter
    adapter.feed_line("main", "[SYS] current=CHAT")

    receipt = adapter.send_binary(b"payload")

    assert receipt.tx_id == 17
    assert sent == [encode_binary_command(b"payload")]


def test_binary_adapter_delivery_telemetry_is_not_send_settlement():
    holder = {}

    def send_line(_text):
        adapter = holder["adapter"]
        adapter.feed_line(
            "telemetry",
            "DELIVERY WAIT_ACK user=A001/7 attempt=1/5 timeout=10ms queue=0",
        )
        adapter.feed_line(
            "telemetry",
            "DELIVERY ACK user=A001/7 attempts=1/5 elapsed=2ms queue=0",
        )
        return {"tx_id": 3}

    adapter = ChatterBinaryUserAdapter(
        send_line,
        presentation_timeout_s=0.03,
        wait_tx_outcome=lambda _tx_id, _timeout: "written",
    )
    holder["adapter"] = adapter
    adapter.feed_line("main", "[SYS] current=CHAT")

    with pytest.raises(Exception) as caught:
        adapter.send_binary(b"abc")

    assert getattr(caught.value, "code", None) == "binary_presentation_timeout"


def test_binary_adapter_checks_local_tx_outcome_before_presentation():
    holder = {}
    waited = []

    def send_line(_text):
        holder["adapter"].feed_line("chat", _tx_line(b"abc"))
        return {"tx_id": 42}

    adapter = ChatterBinaryUserAdapter(
        send_line,
        wait_tx_outcome=lambda tx_id, timeout: waited.append((tx_id, timeout))
        or "written",
        connection_generation=lambda: 5,
    )
    holder["adapter"] = adapter
    adapter.feed_line("main", "[SYS] current=CHAT")

    receipt = adapter.send_binary(b"abc")

    assert receipt.tx_id == 42
    assert waited and waited[0][0] == 42


def test_binary_adapter_reports_ambiguous_local_write():
    adapter = ChatterBinaryUserAdapter(
        lambda _text: {"tx_id": 9},
        wait_tx_outcome=lambda _tx_id, _timeout: "unknown",
        connection_generation=lambda: 1,
    )
    adapter.feed_line("main", "[SYS] current=CHAT")

    with pytest.raises(Exception) as caught:
        adapter.send_binary(b"abc")

    assert getattr(caught.value, "code", None) == "local_tx_unknown"


def test_binary_adapter_reports_disconnect_before_presentation_without_mode_command():
    generation = {"value": 10}
    sent = []

    def send_line(text):
        sent.append(text)
        generation["value"] = 11
        return {"tx_id": 3}

    adapter = ChatterBinaryUserAdapter(
        send_line,
        wait_tx_outcome=lambda _tx_id, _timeout: "written",
        connection_generation=lambda: generation["value"],
    )
    adapter.feed_line("main", "[SYS] current=CHAT")

    with pytest.raises(Exception) as caught:
        adapter.send_binary(b"abc")

    assert getattr(caught.value, "code", None) == "local_disconnect"
    assert sent == [encode_binary_command(b"abc")]


def test_binary_adapter_known_telemetry_mode_fails_without_mutating_output_mode():
    sent = []
    adapter = ChatterBinaryUserAdapter(
        lambda text: sent.append(text) or {"tx_id": len(sent)},
    )
    adapter.feed_line("main", "[SYS] OUTPUT TELEMETRY")

    with pytest.raises(Exception) as caught:
        adapter.send_binary(b"abc")

    assert getattr(caught.value, "code", None) == "binary_presentation_unavailable"
    assert sent == []


def test_binary_adapter_feeds_exact_received_bytes():
    adapter = ChatterBinaryUserAdapter(lambda _text: {"tx_id": 1})
    received = []
    adapter.set_receiver(received.append)

    payload = b"\x00abc\xff\n\r"
    adapter.feed_line("chat", _rx_line(payload))

    assert received == [payload]


class _ChatterPairEndpoint:
    def __init__(self):
        self.peer = None
        self.sent = []
        self.adapter = ChatterBinaryUserAdapter(
            self._send_line,
            wait_tx_outcome=lambda _tx_id, _timeout: "written",
            presentation_timeout_s=1.0,
        )

    def _send_line(self, text):
        self.sent.append(text)
        if text == "/help":
            self.adapter.feed_line("chat", "[SYS] current=CHAT")
        elif text.startswith("/bin "):
            payload = base64.b64decode(text.split(" ", 1)[1], validate=True)
            self.adapter.feed_line("chat", _tx_line(payload))
            if self.peer is not None:
                self.peer.adapter.feed_line("chat", _rx_line(payload))
        return {"tx_id": len(self.sent), "state": "queued"}


def test_ft1_end_to_end_succeeds_without_delivery_telemetry_or_mode_commands(tmp_path):
    left = _ChatterPairEndpoint()
    right = _ChatterPairEndpoint()
    left.peer = right
    right.peer = left

    tx = FileTransferManager(
        left.adapter,
        receive_dir=tmp_path / "left",
        id_factory=lambda: 0x101,
        result_timeout_s=2.0,
        control_replay_interval_s=0.05,
    )
    rx = FileTransferManager(
        right.adapter,
        receive_dir=tmp_path / "right",
        id_factory=lambda: 0x202,
        result_timeout_s=2.0,
        control_replay_interval_s=0.05,
    )
    source = tmp_path / "payload.bin"
    source.write_bytes(bytes(range(256)) * 4)
    try:
        tx.start_send(source)
        deadline = __import__("time").monotonic() + 3.0
        done = None
        while __import__("time").monotonic() < deadline:
            done = tx.display_snapshot()
            if done is not None and done["state"] in {"completed", "failed"}:
                break
            __import__("time").sleep(0.01)

        assert done is not None
        assert done["state"] == "completed"
        received = rx.display_snapshot()
        assert received is not None
        assert received["state"] == "completed"
        assert open(received["final_path"], "rb").read() == source.read_bytes()

        all_commands = left.sent + right.sent
        assert all(
            command == "/help" or command.startswith("/bin ")
            for command in all_commands
        )
        assert all_commands.count("/help") == 2
        assert not any(
            command in {"/both", "/chat", "/tele"}
            for command in all_commands
        )
    finally:
        tx.close()
        rx.close()


def test_binary_adapter_cancelled_before_send_has_no_controller_side_effect():
    cancel = threading.Event()
    cancel.set()
    sent = []
    adapter = ChatterBinaryUserAdapter(
        lambda text: sent.append(text) or {"tx_id": len(sent)},
    )

    with pytest.raises(Exception) as caught:
        adapter.send_binary(b"x", cancel_event=cancel)

    assert getattr(caught.value, "code", None) == "cancelled"
    assert sent == []



def test_binary_adapter_queries_unknown_mode_without_changing_it():
    holder = {}
    sent = []

    def send_line(text):
        sent.append(text)
        if text == "/help":
            holder["adapter"].feed_line("main", "[SYS] current=CHAT")
        elif text.startswith("/bin "):
            holder["adapter"].feed_line("main", _tx_line(b"abc"))
        return {"tx_id": len(sent)}

    adapter = ChatterBinaryUserAdapter(
        send_line,
        wait_tx_outcome=lambda _tx_id, _timeout: "written",
        mode_query_timeout_s=0.2,
    )
    holder["adapter"] = adapter

    receipt = adapter.send_binary(b"abc")

    assert receipt.tx_id == 2
    assert sent == ["/help", encode_binary_command(b"abc")]
    assert not any(command in {"/chat", "/tele", "/both"} for command in sent)


def test_binary_adapter_unknown_telemetry_mode_fails_before_bin_without_mode_change():
    holder = {}
    sent = []

    def send_line(text):
        sent.append(text)
        if text == "/help":
            holder["adapter"].feed_line("main", "[SYS] current=TELEMETRY")
        return {"tx_id": len(sent)}

    adapter = ChatterBinaryUserAdapter(
        send_line,
        wait_tx_outcome=lambda _tx_id, _timeout: "written",
        mode_query_timeout_s=0.2,
    )
    holder["adapter"] = adapter

    with pytest.raises(Exception) as caught:
        adapter.send_binary(b"abc")

    assert getattr(caught.value, "code", None) == "binary_presentation_unavailable"
    assert sent == ["/help"]


def test_binary_adapter_controller_reboot_breaks_presentation_wait_after_ready():
    holder = {}
    sent = []

    def send_line(text):
        sent.append(text)
        if text.startswith("/bin "):
            holder["adapter"].feed_line(
                "main",
                "[SYS] RADIO FATAL RX_RESTART after TX (-16), rebooting",
            )
            holder["adapter"].feed_line("main", "ESP-ROM:esp32s3-20210327")
            holder["adapter"].feed_line("main", "[SYS] CHATTER READY")
        return {"tx_id": len(sent)}

    adapter = ChatterBinaryUserAdapter(
        send_line,
        wait_tx_outcome=lambda _tx_id, _timeout: "written",
        controller_ready_timeout_s=0.2,
    )
    holder["adapter"] = adapter
    adapter.feed_line("main", "[SYS] current=CHAT")

    with pytest.raises(Exception) as caught:
        adapter.send_binary(b"abc")

    assert getattr(caught.value, "code", None) == "local_controller_reset"
    assert sent == [encode_binary_command(b"abc")]


def test_ft1_replays_same_message_after_controller_reboot_and_ready(tmp_path):
    class RebootOnceEndpoint(_ChatterPairEndpoint):
        def __init__(self):
            super().__init__()
            self.rebooted = False

        def _send_line(self, text):
            self.sent.append(text)
            if text == "/help":
                self.adapter.feed_line("chat", "[SYS] current=CHAT")
                return {"tx_id": len(self.sent), "state": "queued"}
            if text.startswith("/bin "):
                payload = base64.b64decode(text.split(" ", 1)[1], validate=True)
                if not self.rebooted:
                    self.rebooted = True
                    if self.peer is not None:
                        self.peer.adapter.feed_line("chat", _rx_line(payload))
                    self.adapter.feed_line(
                        "chat",
                        "[SYS] RADIO FATAL RX_RESTART after TX (-16), rebooting",
                    )
                    self.adapter.feed_line("chat", "ESP-ROM:esp32s3-20210327")
                    self.adapter.feed_line("chat", "[SYS] CHATTER READY")
                    return {"tx_id": len(self.sent), "state": "queued"}
                self.adapter.feed_line("chat", _tx_line(payload))
                if self.peer is not None:
                    self.peer.adapter.feed_line("chat", _rx_line(payload))
            return {"tx_id": len(self.sent), "state": "queued"}

    left = RebootOnceEndpoint()
    right = _ChatterPairEndpoint()
    left.peer = right
    right.peer = left
    tx = FileTransferManager(
        left.adapter,
        receive_dir=tmp_path / "left",
        id_factory=lambda: 0xA01,
        result_timeout_s=2.0,
        control_replay_interval_s=0.05,
    )
    rx = FileTransferManager(
        right.adapter,
        receive_dir=tmp_path / "right",
        id_factory=lambda: 0xA02,
        result_timeout_s=2.0,
        control_replay_interval_s=0.05,
    )
    source = tmp_path / "reboot.bin"
    source.write_bytes(b"reboot-recovery" * 100)
    try:
        tx.start_send(source)
        deadline = __import__("time").monotonic() + 3.0
        done = None
        while __import__("time").monotonic() < deadline:
            done = tx.display_snapshot()
            if done is not None and done["state"] in {"completed", "failed"}:
                break
            __import__("time").sleep(0.01)

        assert done is not None
        assert done["state"] == "completed"
        assert left.rebooted is True
        assert left.sent.count("/help") == 2
        received = rx.display_snapshot()
        assert received is not None
        assert received["state"] == "completed"
    finally:
        tx.close()
        rx.close()



def test_binary_adapter_local_tx_wait_is_cancel_responsive():
    cancel = __import__("threading").Event()
    waits = []

    def wait_tx(_tx_id, timeout):
        waits.append(timeout)
        cancel.set()
        return None

    adapter = ChatterBinaryUserAdapter(
        lambda _text: {"tx_id": 1},
        wait_tx_outcome=wait_tx,
        connection_generation=lambda: 1,
        presentation_timeout_s=30.0,
    )
    adapter.feed_line("main", "[SYS] current=CHAT")

    with pytest.raises(Exception) as caught:
        adapter.send_binary(b"abc", cancel_event=cancel)

    assert type(caught.value).__name__ == "BinaryUserCancelled"
    assert waits
    assert max(waits) <= 0.1
