"""Проверки видимой записи и перехода в существующее окно FT1 без аппаратуры."""
import curses
import threading
from types import SimpleNamespace

import pytest

from serialterminal.voice_service import VoiceSnapshot
from test_tui_file_transfer_window import Canvas, make_tui, snapshot
from test_tui_voice import FakeVoice


RED = (7 << 8) | curses.A_BOLD
COLORS = {name: 0 for name in ("normal", "header", "panel", "status", "error", "input",
                              "error_badge", "dim", "file", "file_border", "file_selected")}
COLORS["voice_recording"] = RED


class PanelVoice(FakeVoice):
    def __init__(self, state="RECORDING"):
        super().__init__(active=True)
        self.state = state
        self.seconds = 12.4

    def snapshot(self):
        return VoiceSnapshot(self.state, self.seconds, None, False, ())

    def local_operation_active(self):
        return self.state in {"STARTING", "RECORDING", "FINALIZING", "ADMITTING"}

    def toggle_recording(self):
        self.toggle_calls += 1
        self.state = "FINALIZING"
        return True


class Screen(Canvas):
    def erase(self):
        self.calls.clear()

    def refresh(self):
        pass

    def move(self, y, x):
        assert 0 <= y < self.height and 0 <= x < self.width

    def addnstr(self, y, x, text, length, attr):
        self.draw(self, y, x, text[:length], attr)

    @property
    def text(self):
        return "\n".join(call[2] for call in self.calls)


def panel_tui(monkeypatch, state="RECORDING"):
    tui = make_tui(snapshot(state="completed"))
    tui._voice_service = PanelVoice(state)
    tui._colors = lambda: COLORS
    tui.session._current_transport = lambda: SimpleNamespace(description="OFFLINE TEST")
    tui.session.connected_event = threading.Event()
    tui.session.log_path, tui.session.console_path = "offline.log", "offline.console.log"
    monkeypatch.setattr(curses, "curs_set", lambda _value: None)
    return tui


def test_recording_panel_is_large_solid_red_and_keeps_command_input(monkeypatch):
    tui, screen = panel_tui(monkeypatch), Screen()
    tui.input_text, tui.input_cursor = "draft", 5
    tui._render(screen)
    assert "● ЗАПИСЬ С МИКРОФОНА    00:12" in screen.text
    assert "F12 — остановить и отправить" in screen.text
    assert "Передача файла" not in screen.text
    red_rows = [call for call in screen.calls if call[3] == RED]
    assert len(red_rows) == 7
    assert len({call[0] for call in red_rows}) == 7
    assert all(call[1] == 2 and len(call[2]) == 76 for call in red_rows)
    assert "> draft" in screen.text
    assert tui.input_text == "draft"


def test_timer_and_red_panel_survive_scrolling_f7_and_output_flood(monkeypatch):
    tui, screen = panel_tui(monkeypatch), Screen()
    tui.output.write("history\n" * 100)
    tui.scrollback.scroll_up(20, width=tui._output_width(80), body_rows=10)
    tui._handle_key(screen, curses.KEY_F7, 10)
    tui.output.write("new output\n" * 100)
    tui._voice_service.seconds = 73.0
    tui._render(screen)
    assert "01:13" in screen.text and "SCROLL" in screen.text
    assert "ЗАПИСЬ С МИКРОФОНА" in screen.text
    assert any(call[3] == RED for call in screen.calls)


@pytest.mark.parametrize("state,text", [("STARTING", "Подготовка микрофона"),
                                       ("FINALIZING", "Завершение записи"),
                                       ("ADMITTING", "к передаче")])
def test_preparation_panel_is_neutral(monkeypatch, state, text):
    tui, screen = panel_tui(monkeypatch, state), Screen()
    tui._render(screen)
    assert text in screen.text
    assert "Голосовое сообщение" in screen.text
    assert "ЗАПИСЬ С МИКРОФОНА" not in screen.text
    assert not any(call[3] == RED for call in screen.calls)


def test_f12_preparation_then_existing_ft1_window_then_completion(monkeypatch):
    tui, screen = panel_tui(monkeypatch), Screen()
    tui._render(screen)
    tui._handle_key(screen, curses.KEY_F12, 10)
    tui._render(screen)
    assert "Завершение записи" in screen.text
    assert "ЗАПИСЬ С МИКРОФОНА" not in screen.text
    tui._voice_service.state = "ADMITTING"
    tui._render(screen)
    assert "к передаче" in screen.text
    tui._voice_service.state = "IDLE"
    tui._file_transfer.value = snapshot(transfer_id="0000000000000002", filename="voice.stvoice.c2")
    tui._file_transfer.busy = True
    tui._render(screen)
    assert "Передача файла" in screen.text and "voice.stvoice.c2" in screen.text
    assert "Голосовое сообщение" not in screen.text
    tui._file_transfer.value["state"] = "completed"
    tui._file_transfer.busy = False
    tui._render(screen)
    assert "Передача файла" not in screen.text
    assert not any(call[3] == RED for call in screen.calls)


@pytest.mark.parametrize("size", [(12, 60), (8, 35), (2, 20)])
def test_recording_remains_visible_on_small_terminal(monkeypatch, size):
    tui, screen = panel_tui(monkeypatch), Screen(*size)
    tui._render(screen)
    assert "ЗАПИСЬ" in screen.text
    assert any(call[3] == RED for call in screen.calls)
    assert "Terminal is too small" not in screen.text


def test_hidden_old_ft1_confirmation_does_not_capture_f12(monkeypatch):
    tui, screen = panel_tui(monkeypatch), Screen()
    old = snapshot()
    tui._file_window().request_cancel(old)
    tui._render(screen)
    assert "Подтверждение" not in screen.text
    tui._handle_key(screen, curses.KEY_F12, 10)
    assert tui._voice_service.toggle_calls == 1
    assert tui._voice_service.state == "FINALIZING"


@pytest.mark.parametrize("state", ["IDLE", "READY_FILE", "CLOSED"])
def test_inactive_voice_does_not_cover_existing_file_window(monkeypatch, state):
    tui, screen = panel_tui(monkeypatch, state), Screen()
    tui._file_transfer.value = snapshot()
    tui._file_transfer.busy = True
    tui._render(screen)
    assert "Передача файла" in screen.text
    assert "Голосовое сообщение" not in screen.text


def playback_tui(monkeypatch):
    tui = panel_tui(monkeypatch, "IDLE")
    voice = tui._voice_service
    voice.cancelled, voice.cancel_calls = False, 0
    voice.snapshot = lambda: VoiceSnapshot("IDLE", 0.0, None, True, (), 7.2, 19.0, voice.cancelled)

    def cancel():
        voice.cancel_calls += 1
        voice.cancelled = True
        return True

    voice.cancel_playback = cancel
    tui._colors = lambda: {**COLORS, "voice_playback": 11 << 8, "voice_button": (12 << 8) | curses.A_BOLD}
    return tui


def test_playback_panel_has_progress_and_centered_cancel(monkeypatch):
    tui, screen = playback_tui(monkeypatch), Screen()
    tui._render(screen)
    assert "ВОСПРОИЗВЕДЕНИЕ" in screen.text
    assert "00:07 / 00:19" in screen.text and "38%" in screen.text
    button = next(call for call in screen.calls if call[2] == "[ Cancel ]")
    assert button[1] == 35 and button[3] == (12 << 8) | curses.A_BOLD
    assert "Передача файла" not in screen.text
    assert not any(call[3] == RED for call in screen.calls)


@pytest.mark.parametrize("key", ["\x1b", "\n", curses.KEY_ENTER])
def test_playback_cancel_keys_do_not_submit_draft_or_cancel_ft1(monkeypatch, key):
    tui, screen = playback_tui(monkeypatch), Screen()
    tui.input_text, tui.input_cursor = "draft", 5
    tui._file_window().request_cancel(snapshot())
    tui._handle_key(screen, key, 10)
    assert tui._voice_service.cancel_calls == 1
    assert tui.input_text == "draft" and not tui.sent and not tui._file_transfer.cancelled
    tui._render(screen)
    assert "ВОСПРОИЗВЕДЕНИЕ" not in screen.text


def test_playback_cancel_button_accepts_mouse_click(monkeypatch):
    from serialterminal.tui_voice import playback_button_rect
    tui, screen = playback_tui(monkeypatch), Screen()
    y, x, _ = playback_button_rect(24, 80)
    monkeypatch.setattr(curses, "getmouse", lambda: (0, x + 2, y, 0, curses.BUTTON1_CLICKED))
    tui._handle_mouse(screen, 15)
    assert tui._voice_service.cancel_calls == 1


def test_f5_still_routes_to_file_picker_during_playback(monkeypatch):
    tui = playback_tui(monkeypatch)
    selected = []
    tui._choose_file = selected.append
    screen = Screen()
    tui._handle_key(screen, curses.KEY_F5, 10)
    assert selected == [screen] and tui._voice_service.cancel_calls == 0


@pytest.mark.parametrize("size", [(12, 60), (8, 35)])
def test_playback_resize_preserves_stop_control(monkeypatch, size):
    tui, screen = playback_tui(monkeypatch), Screen(*size)
    tui._render(screen)
    assert "Esc" in screen.text
    tui._handle_key(screen, "\x1b", 1)
    assert tui._voice_service.cancel_calls == 1


@pytest.mark.parametrize("palette", [8, 256])
def test_playback_palette_uses_muted_background_and_shared_purple_accent(monkeypatch, palette):
    from serialterminal.tui_voice import init_voice_colors
    calls = []
    monkeypatch.setattr(curses, "COLORS", palette, raising=False)
    monkeypatch.setattr(curses, "init_pair", lambda *args: calls.append(args))
    monkeypatch.setattr(curses, "color_pair", lambda pair: pair << 8)
    colors = init_voice_colors()
    assert calls == [(11, 255 if palette == 256 else curses.COLOR_WHITE,
                      60 if palette == 256 else curses.COLOR_BLUE),
                     (12, 236 if palette == 256 else curses.COLOR_BLACK,
                      141 if palette == 256 else curses.COLOR_MAGENTA)]
    assert colors["voice_button"] == (12 << 8) | curses.A_BOLD
