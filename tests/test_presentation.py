import pytest

from serialterminal.profiles.chatter.presentation import (
    ChatterPresentation,
    recognized_chatter_command,
)


def test_command_recognition_matches_firmware_boundary_trim():
    assert recognized_chatter_command("/reboot") == "/reboot"
    assert recognized_chatter_command("/version") == "/version"
    assert recognized_chatter_command("/firmware") == "/firmware"
    assert recognized_chatter_command("/power") == "/power"
    assert recognized_chatter_command("/power 10") == "/power 10"
    assert recognized_chatter_command("  /power 10  ") == "/power 10"
    assert recognized_chatter_command("/freq") == "/freq"
    assert recognized_chatter_command("/freq 480.355") == "/freq 480.355"
    assert recognized_chatter_command("/freq-oob on") == "/freq-oob on"
    assert recognized_chatter_command("/freq-oob off") == "/freq-oob off"
    assert recognized_chatter_command("/sf 9") == "/sf 9"
    assert recognized_chatter_command("/bw 31.25") == "/bw 31.25"
    assert recognized_chatter_command("/config") == "/config"
    assert recognized_chatter_command("/config reset") == "/config reset"
    assert recognized_chatter_command("/heartbeat") == "/heartbeat"
    assert recognized_chatter_command("/heartbeat on") == "/heartbeat on"
    assert recognized_chatter_command("/heartbeat nonsense") == "/heartbeat nonsense"
    assert recognized_chatter_command("/diag") == "/diag"
    assert recognized_chatter_command("/diag on") == "/diag on"
    assert recognized_chatter_command("/diag size 100") == "/diag size 100"
    assert recognized_chatter_command("/diag size 1") == "/diag size 1"
    assert recognized_chatter_command("/diag nonsense") == "/diag nonsense"
    assert recognized_chatter_command(" \t/reboot \x7f") == "/reboot"
    assert recognized_chatter_command("  /echo  ") == "/echo"
    assert recognized_chatter_command("\t/cancel\x7f") == "/cancel"
    assert recognized_chatter_command(" \x00/cancel all \x7f") == "/cancel all"
    assert recognized_chatter_command(" /cancel all now ") is None
    assert recognized_chatter_command(" /echo x ") is None
    assert recognized_chatter_command(" hello ") is None


def test_success_marker_resolves_sent_user_payload():
    tracker = ChatterPresentation()
    assert tracker.submit_payload("hello")
    tracker.mark_sent("hello")

    assert tracker.consume_firmware_line("> hello\n") is None
    assert tracker.pending_count() == 0


def test_echo_success_marker_resolves_sent_payload():
    tracker = ChatterPresentation()
    assert tracker.submit_payload("hello")
    tracker.mark_sent("hello")

    assert tracker.consume_firmware_line("> [ECHO TX] hello\n") is None
    assert tracker.pending_count() == 0


def test_user_payload_that_looks_like_echo_marker_still_resolves():
    tracker = ChatterPresentation()
    payload = "[ECHO TX] hello"
    assert tracker.submit_payload(payload)
    tracker.mark_sent(payload)

    assert tracker.consume_firmware_line("> [ECHO TX] hello\n") is None
    assert tracker.pending_count() == 0


def test_success_marker_does_not_resolve_unsent_payload():
    tracker = ChatterPresentation()
    assert tracker.submit_payload("hello")

    assert tracker.consume_firmware_line("> hello\n") is None
    assert tracker.pending_count() == 1


def test_rejection_reveals_oldest_sent_payload_only():
    tracker = ChatterPresentation()
    assert tracker.submit_payload("first")
    assert tracker.submit_payload("second")
    assert tracker.submit_payload("third")
    tracker.mark_sent("first")
    tracker.mark_sent("second")

    assert (
        tracker.consume_firmware_line(
            "[SYS] RADIO UNAVAILABLE, message not sent\n"
        )
        == "first"
    )
    assert tracker.pending_count() == 2

    assert (
        tracker.consume_firmware_line(
            "[ECHO] REQUEST PENDING, message not sent\n"
        )
        == "second"
    )
    assert tracker.pending_count() == 1


def test_queue_full_rejection_reveals_and_removes_pending_payload():
    tracker = ChatterPresentation()
    assert tracker.submit_payload("overflow")
    tracker.mark_sent("overflow")

    assert (
        tracker.consume_firmware_line(
            "[SYS] SEND QUEUE FULL: message not accepted\n"
        )
        == "overflow"
    )
    assert tracker.pending_count() == 0


def test_inflight_cancellation_reveals_status_unknown_payload():
    tracker = ChatterPresentation()
    assert tracker.submit_payload("in-flight")
    tracker.mark_sent("in-flight")

    assert (
        tracker.consume_firmware_line(
            "[SYS] DELIVERY CANCELLED: status unknown\n"
        )
        == "in-flight"
    )
    assert tracker.pending_count() == 0


def test_cancellation_prefix_resolves_one_pending_payload_only():
    tracker = ChatterPresentation()
    assert tracker.submit_payload("cancelled")
    assert tracker.submit_payload("still-pending")
    tracker.mark_sent("cancelled")
    tracker.mark_sent("still-pending")

    assert (
        tracker.consume_firmware_line(
            "[SYS] DELIVERY CANCELLED: queued item not transmitted\n"
        )
        == "cancelled"
    )
    assert tracker.pending_count() == 1

    assert tracker.consume_firmware_line("> still-pending\n") is None
    assert tracker.pending_count() == 0


def test_unrelated_telemetry_does_not_change_pending_state():
    tracker = ChatterPresentation()
    assert tracker.submit_payload("hello")
    tracker.mark_sent("hello")

    assert tracker.consume_firmware_line("SESSION t=60s TX ok=1\n") is None
    assert tracker.pending_count() == 1


def test_disconnect_reveals_sent_and_preserves_unsent():
    tracker = ChatterPresentation()
    assert tracker.submit_payload("sent")
    assert tracker.submit_payload("queued")
    tracker.mark_sent("sent")

    assert tracker.consume_sent_on_disconnect() == ["sent"]
    assert tracker.pending_count() == 1

    tracker.mark_sent("queued")
    assert tracker.consume_firmware_line("> queued\n") is None
    assert tracker.pending_count() == 0


def test_duplicate_payloads_resolve_one_at_a_time():
    tracker = ChatterPresentation()
    assert tracker.submit_payload("same")
    assert tracker.submit_payload("same")
    tracker.mark_sent("same")
    tracker.mark_sent("same")

    assert tracker.consume_firmware_line("> same\n") is None
    assert tracker.pending_count() == 1
    assert tracker.consume_firmware_line("> same\n") is None
    assert tracker.pending_count() == 0


def test_presentation_queue_is_bounded():
    tracker = ChatterPresentation(limit=2)
    assert tracker.submit_payload("one")
    assert tracker.submit_payload("two")
    assert not tracker.submit_payload("three")
    assert tracker.pending_count() == 2

    with pytest.raises(ValueError):
        ChatterPresentation(limit=0)



def test_controller_fatal_releases_all_sent_pending_presentations():
    tracker = ChatterPresentation(limit=4)
    for text in ("one", "two", "three", "four"):
        assert tracker.submit_payload(text)
        tracker.mark_sent(text)

    reveal = tracker.consume_firmware_line(
        "[SYS] RADIO FATAL RX_RESTART after TX (-16), rebooting\n"
    )

    assert reveal == "one\ntwo\nthree\nfour"
    assert tracker.pending_count() == 0
    assert tracker.submit_payload("after-reset")


def test_controller_ready_releases_stale_sent_without_dropping_unsent():
    tracker = ChatterPresentation(limit=4)
    assert tracker.submit_payload("sent-old-epoch")
    assert tracker.submit_payload("queued-not-written")
    tracker.mark_sent("sent-old-epoch")

    assert (
        tracker.consume_firmware_line("[SYS] CHATTER READY\n")
        == "sent-old-epoch"
    )
    assert tracker.pending_count() == 1

    tracker.mark_sent("queued-not-written")
    assert tracker.consume_firmware_line("> queued-not-written\n") is None
    assert tracker.pending_count() == 0


def test_boot_banner_is_controller_epoch_boundary_for_pending_presentations():
    tracker = ChatterPresentation()
    assert tracker.submit_payload("ambiguous")
    tracker.mark_sent("ambiguous")

    assert tracker.consume_firmware_line("ESP-ROM:esp32s3-20210327\n") == "ambiguous"
    assert tracker.pending_count() == 0
