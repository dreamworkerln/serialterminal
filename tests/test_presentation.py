import pytest

from serialterminal.presentation import (
    PresentationTracker,
    recognized_chatter_command,
)


def test_command_recognition_matches_firmware_boundary_trim():
    assert recognized_chatter_command("/reboot") == "/reboot"
    assert recognized_chatter_command(" \t/reboot \x7f") == "/reboot"
    assert recognized_chatter_command("  /echo  ") == "/echo"
    assert recognized_chatter_command(" /echo x ") is None
    assert recognized_chatter_command(" hello ") is None


def test_success_marker_resolves_sent_user_payload():
    tracker = PresentationTracker()
    assert tracker.submit_payload("hello")
    tracker.mark_sent("hello")

    assert tracker.consume_firmware_line("> hello\n") is None
    assert tracker.pending_count() == 0


def test_echo_success_marker_resolves_sent_payload():
    tracker = PresentationTracker()
    assert tracker.submit_payload("hello")
    tracker.mark_sent("hello")

    assert tracker.consume_firmware_line("> [ECHO TX] hello\n") is None
    assert tracker.pending_count() == 0


def test_user_payload_that_looks_like_echo_marker_still_resolves():
    tracker = PresentationTracker()
    payload = "[ECHO TX] hello"
    assert tracker.submit_payload(payload)
    tracker.mark_sent(payload)

    assert tracker.consume_firmware_line("> [ECHO TX] hello\n") is None
    assert tracker.pending_count() == 0


def test_success_marker_does_not_resolve_unsent_payload():
    tracker = PresentationTracker()
    assert tracker.submit_payload("hello")

    assert tracker.consume_firmware_line("> hello\n") is None
    assert tracker.pending_count() == 1


def test_rejection_reveals_oldest_sent_payload_only():
    tracker = PresentationTracker()
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


def test_unrelated_telemetry_does_not_change_pending_state():
    tracker = PresentationTracker()
    assert tracker.submit_payload("hello")
    tracker.mark_sent("hello")

    assert tracker.consume_firmware_line("SESSION t=60s TX ok=1\n") is None
    assert tracker.pending_count() == 1


def test_disconnect_reveals_sent_and_preserves_unsent():
    tracker = PresentationTracker()
    assert tracker.submit_payload("sent")
    assert tracker.submit_payload("queued")
    tracker.mark_sent("sent")

    assert tracker.consume_sent_on_disconnect() == ["sent"]
    assert tracker.pending_count() == 1

    tracker.mark_sent("queued")
    assert tracker.consume_firmware_line("> queued\n") is None
    assert tracker.pending_count() == 0


def test_duplicate_payloads_resolve_one_at_a_time():
    tracker = PresentationTracker()
    assert tracker.submit_payload("same")
    assert tracker.submit_payload("same")
    tracker.mark_sent("same")
    tracker.mark_sent("same")

    assert tracker.consume_firmware_line("> same\n") is None
    assert tracker.pending_count() == 1
    assert tracker.consume_firmware_line("> same\n") is None
    assert tracker.pending_count() == 0


def test_presentation_queue_is_bounded():
    tracker = PresentationTracker(limit=2)
    assert tracker.submit_payload("one")
    assert tracker.submit_payload("two")
    assert not tracker.submit_payload("three")
    assert tracker.pending_count() == 2

    with pytest.raises(ValueError):
        PresentationTracker(limit=0)
