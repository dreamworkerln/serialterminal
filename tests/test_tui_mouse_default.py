from serialterminal import tui as tui_module


def test_terminal_mouse_mode_is_default_and_f8_can_enable_capture(monkeypatch):
    def fake_base_init(self, *args, **kwargs):
        del args, kwargs
        self.mouse_capture = True

    calls: list[bool] = []

    def fake_set_mouse_capture(self, enabled: bool):
        calls.append(enabled)
        self.mouse_capture = enabled

    monkeypatch.setattr(tui_module._core.TerminalTui, "__init__", fake_base_init)
    monkeypatch.setattr(
        tui_module._core.TerminalTui,
        "_set_mouse_capture",
        fake_set_mouse_capture,
    )

    tui = tui_module.TerminalTui()
    assert tui.mouse_capture is False
    assert tui._startup_mouse_mode_pending is True

    # Base run() asks for capture at startup; the public TUI suppresses only that
    # first request so terminal selection and RMB work without Shift immediately.
    tui._set_mouse_capture(True)
    assert calls == [False]
    assert tui.mouse_capture is False
    assert tui._startup_mouse_mode_pending is False

    # The next request is the normal F8 toggle and must still enable curses mouse.
    tui._set_mouse_capture(True)
    assert calls == [False, True]
    assert tui.mouse_capture is True
