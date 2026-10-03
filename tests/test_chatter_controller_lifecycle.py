import threading

import pytest

from serialterminal.profiles.chatter.binary_user import ChatterBinaryUserAdapter


def test_controller_lifecycle_deduplicates_boot_markers_into_one_epoch():
    generation = {"value": 7}
    adapter = ChatterBinaryUserAdapter(
        lambda _text: {"tx_id": 1},
        connection_generation=lambda: generation["value"],
    )

    initial = adapter.controller_status()
    assert initial["state"] == "ready"
    assert initial["epoch"] == 0
    assert initial["connection_generation"] == 7

    adapter.feed_line("chat", "[SYS] RADIO FATAL RX_RESTART (-16), rebooting")
    after_fatal = adapter.controller_status()
    assert after_fatal["state"] == "resetting"
    assert after_fatal["epoch"] == 1
    assert after_fatal["reset_generation"] == 7

    adapter.feed_line("chat", "ESP-ROM:esp32s3-20210327")
    adapter.feed_line("chat", "rst:0x3 (SW_RESET),boot:0x8")
    repeated = adapter.controller_status()
    assert repeated["state"] == "resetting"
    assert repeated["epoch"] == 1

    adapter.feed_line("chat", "[SYS] CHATTER READY")
    ready = adapter.controller_status()
    assert ready["state"] == "ready"
    assert ready["epoch"] == 1
    assert ready["reset_generation"] is None


def test_usb_reboot_same_generation_waits_for_ready_marker():
    holder = {}
    sent = []

    def send_line(text):
        sent.append(text)
        if text.startswith("/bin "):
            holder["adapter"].feed_line(
                "chat", "[SYS] RADIO FATAL RX_RESTART (-16), rebooting"
            )
            holder["adapter"].feed_line("chat", "ESP-ROM:esp32s3-20210327")
            holder["adapter"].feed_line("chat", "[SYS] CHATTER READY")
        return {"tx_id": len(sent)}

    adapter = ChatterBinaryUserAdapter(
        send_line,
        wait_tx_outcome=lambda _tx_id, _timeout: "written",
        connection_generation=lambda: 5,
        controller_ready_timeout_s=0.2,
    )
    holder["adapter"] = adapter
    adapter.feed_line("chat", "[SYS] current=CHAT")

    with pytest.raises(Exception) as caught:
        adapter.send_binary(b"abc")

    assert getattr(caught.value, "code", None) == "local_controller_reset"
    assert adapter.controller_status()["state"] == "ready"


def test_ble_reconnect_generation_allows_readiness_probe_after_reset():
    generation = {"value": 10}
    holder = {}
    sent = []

    def send_line(text):
        sent.append(text)
        if text == "/help":
            # A successful response from the new transport/controller proves
            # the controller is usable even if its boot-time READY line was
            # emitted before BLE notifications were re-subscribed.
            holder["adapter"].feed_line("chat", "[SYS] current=CHAT")
        elif text.startswith("/bin "):
            holder["adapter"].feed_line("chat", "> [BINARY] YWJj")
        return {"tx_id": len(sent)}

    adapter = ChatterBinaryUserAdapter(
        send_line,
        wait_tx_outcome=lambda _tx_id, _timeout: "written",
        connection_generation=lambda: generation["value"],
        controller_ready_timeout_s=0.2,
        mode_query_timeout_s=0.2,
    )
    holder["adapter"] = adapter
    adapter.feed_line("chat", "[SYS] current=CHAT")
    adapter.feed_line("chat", "[SYS] RADIO FATAL RX_RESTART (-16), rebooting")

    generation["value"] = 13
    receipt = adapter.send_binary(b"abc")

    assert receipt.tx_id == 2
    assert sent == ["/help", "/bin YWJj"]
    status = adapter.controller_status()
    assert status["state"] == "ready"
    assert status["epoch"] == 1
    assert status["connection_generation"] == 13


def test_controller_ready_wait_is_cancel_responsive():
    cancel = threading.Event()
    adapter = ChatterBinaryUserAdapter(
        lambda _text: {"tx_id": 1},
        connection_generation=lambda: 2,
        controller_ready_timeout_s=30.0,
    )
    adapter.feed_line("chat", "[SYS] RADIO FATAL RX_RESTART (-16), rebooting")
    cancel.set()

    with pytest.raises(Exception) as caught:
        adapter.wait_controller_ready(cancel_event=cancel)

    assert type(caught.value).__name__ == "BinaryUserCancelled"


def test_controller_ready_wait_times_out_boundedly_without_ready():
    adapter = ChatterBinaryUserAdapter(
        lambda _text: {"tx_id": 1},
        connection_generation=lambda: 2,
        controller_ready_timeout_s=0.01,
    )
    adapter.feed_line("chat", "[SYS] RADIO FATAL RX_RESTART (-16), rebooting")

    with pytest.raises(Exception) as caught:
        adapter.wait_controller_ready()

    assert getattr(caught.value, "code", None) == "controller_ready_timeout"
    assert adapter.controller_status()["state"] == "resetting"


def test_controller_lifecycle_timing_events_are_structured():
    events = []

    def timing(event, **fields):
        events.append((event, fields))

    adapter = ChatterBinaryUserAdapter(
        lambda _text: {"tx_id": 1},
        connection_generation=lambda: 4,
        timing_sink=timing,
    )
    adapter.feed_line("chat", "[SYS] RADIO FATAL RX_RESTART (-16), rebooting")
    adapter.feed_line("chat", "ESP-ROM:esp32s3-20210327")
    adapter.feed_line("chat", "[SYS] CHATTER READY")

    lifecycle = [(name, fields) for name, fields in events if name.startswith("controller_")]
    assert [name for name, _fields in lifecycle] == [
        "controller_reset_detected",
        "controller_ready",
    ]
    assert lifecycle[0][1]["epoch"] == 1
    assert lifecycle[0][1]["generation"] == 4
    assert lifecycle[1][1]["epoch"] == 1
