from types import SimpleNamespace
import curses

from serialterminal.profiles.base import SendLine
from serialterminal.tui import TerminalTui, TuiOutputBuffer, TuiScrollback
from serialterminal.tui_file_transfer import FileTransferWindow


class FakeVoice:
    def __init__(self, *, active=False, available=True, accept=True, playback=False):
        self.active = active
        self.available = available
        self.accept = accept
        self.playback = playback
        self.toggle_calls = 0
        self.events = []
        self.notifications = []

    def local_operation_active(self):
        return self.active

    def availability(self):
        return (self.available, "" if self.available else "unavailable")

    def toggle_recording(self):
        self.toggle_calls += 1
        return self.accept

    def status_line(self):
        return "VOICE PLAYBACK · F12 waits" if self.playback else "VOICE REC 1.0s · F12 send"

    def drain_notifications(self):
        values = list(self.notifications)
        self.notifications.clear()
        return values

    def on_ft1_event(self, event, manager):
        self.events.append((event, manager))


class FakeProfile:
    def human_action_is_non_disruptive(self, action):
        return isinstance(action, SendLine) and action.line == "/safe"


def make_tui(voice):
    tui = object.__new__(TerminalTui)
    tui._voice_service = voice
    tui._file_transfer = None
    tui._binary_adapter = None
    tui._transfer_window = FileTransferWindow()
    tui._profile_prefix_pending = False
    tui.status = ""
    tui.running = True
    tui.output = TuiOutputBuffer()
    tui.scrollback = TuiScrollback(tui.output)
    tui.input_text = ""
    tui.input_cursor = 0
    tui.command_history = []
    tui.profile = FakeProfile()
    tui.session = SimpleNamespace(
        write_output=tui.output.write,
        _show_full_help=lambda: None,
    )
    return tui


def test_f12_routes_to_voice_service_without_profile_branch():
    voice = FakeVoice()
    tui = make_tui(voice)

    tui._handle_key(SimpleNamespace(), curses.KEY_F12, 10)

    assert voice.toggle_calls == 1
    assert tui.status.startswith("VOICE REC")


def test_voice_local_operation_blocks_disruptive_actions_but_not_profile_safe_action():
    voice = FakeVoice(active=True)
    tui = make_tui(voice)

    assert tui._allow_human_action(SendLine("/safe")) is True
    assert tui._allow_human_action(SendLine("/reboot")) is False
    assert "disruptive" in tui.status


def test_f2_f3_f5_are_guarded_while_voice_local_operation_active(monkeypatch):
    voice = FakeVoice(active=True)
    tui = make_tui(voice)
    screen = SimpleNamespace(refresh=lambda: (_ for _ in ()).throw(AssertionError("must not refresh")))

    tui._handle_key(screen, curses.KEY_F2, 10)
    assert "device change is blocked" in tui.status
    tui._handle_key(screen, curses.KEY_F3, 10)
    assert "profile change is blocked" in tui.status
    tui._handle_key(screen, curses.KEY_F5, 10)
    assert "F5 send is blocked" in tui.status


def test_ft1_event_logging_failure_does_not_suppress_voice_dispatch():
    voice = FakeVoice()
    tui = make_tui(voice)
    manager = object()
    event = {"kind": "transfer_completed", "transfer_id": "abc"}

    def fail_log(*_args, **_kwargs):
        raise RuntimeError("log failure")

    tui._log_file_transfer_event = fail_log
    tui._dispatch_file_transfer_event(event, session=object(), manager=manager)

    assert voice.events == [(event, manager)]


def test_help_advertises_f12_only_when_voice_capability_available():
    voice = FakeVoice(available=True)
    tui = make_tui(voice)
    tui._show_tui_help()
    assert "F12" in "\n".join(tui.output.snapshot())

    voice.available = False
    tui.output.clear()
    tui._show_tui_help()
    assert "F12" not in "\n".join(tui.output.snapshot())
