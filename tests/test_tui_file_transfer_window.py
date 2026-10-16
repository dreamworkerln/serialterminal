from collections import deque
from types import SimpleNamespace
import curses

import pytest

from serialterminal.profiles import GENERIC_PROFILE
from serialterminal.profiles.chatter import CHATTER_PROFILE
from serialterminal.tui import TerminalTui, TuiOutputBuffer, TuiScrollback
from serialterminal.tui_file_transfer import FileTransferWindow
from serialterminal.tui_text import cell_width, fit_cells, middle_ellipsis, screen_safe_text, wrap_cells


def snapshot(**changes):
    return {"transfer_id": "0000000000000001", "state": "sending", "filename": "файл.bin",
            "direction": "TX", "percentage": 40, "bytes_completed": 40, "wire_bytes": 100,
            "chunks_completed": 1, "chunks_total": 3, "elapsed": 4.0,
            "presentation": {"active": True}, **changes}


class Manager:
    def __init__(self, value=None):
        self.value = value or snapshot()
        self.busy = self.value["state"] not in {"completed", "failed", "cancelled"}
        self.cancelled = []

    def display_snapshot(self):
        return dict(self.value)

    def cancel(self, ident):
        self.cancelled.append(ident)
        self.value["state"] = "cancelled"
        self.busy = False


def make_tui(value=None):
    tui = object.__new__(TerminalTui)
    tui._file_transfer = Manager(value)
    tui.profile = CHATTER_PROFILE
    tui._binary_adapter = None
    tui.panel = None
    tui.output = TuiOutputBuffer()
    tui.scrollback = TuiScrollback(tui.output)
    tui._file_rate_transfer_id = None
    tui._file_rate_samples = deque()
    tui.input_text = ""
    tui.input_cursor = 0
    tui.command_history = []
    tui.status = ""
    tui.running = True
    sent, actions = [], []
    tui.session = SimpleNamespace(_submit_interactive_line=sent.append,
                                  _queue_profile_action=lambda action: actions.append(action),
                                  write_output=tui.output.write,
                                  record_timing=lambda *args, **kwargs: None,
                                  _record_primary=lambda *args, **kwargs: None)
    tui.sent = sent
    tui.actions = actions
    return tui


class Canvas:
    def __init__(self, height=24, width=80):
        self.height, self.width = height, width
        self.calls = []

    def getmaxyx(self):
        return self.height, self.width

    def draw(self, screen, y, x, text, attr=0):
        assert 0 <= y < self.height
        assert 0 <= x < self.width
        assert cell_width(text) <= self.width - x - 1
        assert not any(ord(c) < 32 or 127 <= ord(c) < 160 for c in text)
        self.calls.append((y, x, text, attr))


def render(window, screen, value):
    window.draw(screen, screen.draw, value, bar=TerminalTui.render_progress_bar,
                state_label=TerminalTui.file_state_label, rate=2.5, attr=3, selected=9)


@pytest.mark.parametrize("state", ["sending", "receiving", "repairing", "waiting_result"])
@pytest.mark.parametrize("line", ["/tele", "/chat", "/both", "/id", "/config", "/errors"])
def test_console_presentation_and_queries_preserve_file_identity(state, line):
    tui = make_tui(snapshot(state=state))
    manager, session = tui._file_transfer, tui.session
    original = manager.value.copy()
    tui.input_text = line
    tui._handle_key(Canvas(), "\n", 12)
    assert tui.sent == [line]
    assert manager.value == original
    assert not manager.cancelled
    assert tui._file_transfer is manager and tui.session is session
    assert tui.input_text == ""


@pytest.mark.parametrize("key", ["1", "2", "3", "c", "t", "b"])
def test_profile_output_hotkeys_use_same_path_during_transfer(key):
    tui = make_tui()
    original = tui._file_transfer.value.copy()
    tui._handle_key(Canvas(), "\x14", 12)
    tui._handle_key(Canvas(), key, 12)
    assert len(tui.actions) == 1
    assert tui.actions[0] == CHATTER_PROFILE.human_actions()[dict(CHATTER_PROFILE.human_hotkeys())[key]]
    assert tui._file_transfer.value == original
    assert not tui._file_transfer.cancelled and not tui.sent


@pytest.mark.parametrize("line", ["hello radio", "/reboot", "/power 20", "/bw 125", "/cancel", "/cancel all", "/bin QQ=="])
def test_disruptive_input_is_rejected_without_cancelling_or_clearing_draft(line):
    tui = make_tui()
    tui.input_text = line
    tui._submit_input()
    assert not tui.sent and not tui._file_transfer.cancelled
    assert tui.input_text == line
    assert "после её завершения" in tui.status


def test_blank_enter_is_noop_in_command_input():
    tui = make_tui()
    tui._handle_key(Canvas(), "\n", 10)
    assert not tui.sent and not tui._file_transfer.cancelled


def test_confirmation_has_no_on_left_yes_on_right_default_yes_and_consumes_keys():
    tui = make_tui()
    tui.input_text = "draft"
    tui._handle_key(Canvas(), "\x1b", 10)
    view = tui._file_window()
    assert view.confirm_yes
    canvas = Canvas()
    render(view, canvas, tui._file_snapshot())
    no = next(call for call in canvas.calls if call[2] == "[ Нет ]")
    yes = next(call for call in canvas.calls if call[2] == "[ Да ]")
    assert no[1] < yes[1] and yes[3] == 9 and no[3] == 3
    tui._handle_key(canvas, "x", 10)
    tui._handle_key(canvas, curses.KEY_LEFT, 10)
    assert not view.confirm_yes
    tui._handle_key(canvas, "\n", 10)
    assert view.confirmation_id is None
    assert not tui._file_transfer.cancelled and not tui.sent
    assert tui.input_text == "draft"
    tui._handle_key(canvas, curses.KEY_F6, 10)
    assert view.confirm_yes
    tui._handle_key(canvas, "\n", 10)
    assert tui._file_transfer.cancelled == ["0000000000000001"]
    assert not tui.sent and tui.running
    assert tui._file_snapshot()["state"] == "cancelled"


@pytest.mark.parametrize("state,new_id", [("completed", "0000000000000001"), ("failed", "0000000000000001"), ("sending", "0000000000000002")])
def test_late_confirmation_never_cancels_new_or_terminal_operation(state, new_id):
    tui = make_tui()
    tui._handle_key(Canvas(), "\x1b", 10)
    tui._file_transfer.value.update(state=state, transfer_id=new_id)
    # Render между завершением и Enter не должен разорвать адресную привязку.
    render(tui._file_window(), Canvas(), tui._file_snapshot())
    tui._handle_key(Canvas(), "\n", 10)
    assert not tui._file_transfer.cancelled and not tui.sent
    assert tui._file_window().confirmation_id is None


def test_repeat_escape_returns_to_progress_and_transfer_continues():
    tui = make_tui()
    tui._handle_key(Canvas(), "\x1b", 10)
    tui._file_transfer.value["bytes_completed"] = 55
    tui._handle_key(Canvas(), "\x1b", 10)
    assert tui._file_window().visible
    assert tui._file_window().confirmation_id is None
    assert tui._file_snapshot()["bytes_completed"] == 55
    assert not tui._file_transfer.cancelled


def test_background_and_resize_preserve_root_and_full_filename():
    name = "Начало-" + "界e\u0301👩\u200d💻🇷🇺" * 60 + ".bin"
    value = snapshot(filename=name, repair={"depth": 3, "missing_total": 7})
    view = FileTransferWindow()
    for width, height in [(80, 24), (200, 40), (60, 12), (20, 6), (120, 30)]:
        canvas = Canvas(height, width)
        render(view, canvas, value)
        if width >= 60 and height >= 12:
            assert any("Передача файла" in call[2] for call in canvas.calls)
            assert max(cell_width(call[2]) for call in canvas.calls) >= width - 5
    view.handle_key(curses.KEY_F7, value)
    assert not view.visible
    view.handle_key(curses.KEY_F7, value)
    assert view.visible and view.transfer_id == value["transfer_id"]
    assert view.handle_key(curses.KEY_F10, value) == (False, None)
    assert view.visible and view.transfer_id == value["transfer_id"]
    assert value["filename"] == name


def test_confirmation_selection_survives_resize_and_tiny_terminal_cannot_confirm():
    tui = make_tui()
    tui._handle_key(Canvas(), "\x1b", 10)
    tui._handle_key(Canvas(), curses.KEY_LEFT, 10)
    for width, height in [(200, 40), (60, 12), (25, 7), (120, 30)]:
        render(tui._file_window(), Canvas(height, width), tui._file_snapshot())
        assert not tui._file_window().confirm_yes
    tui._handle_key(Canvas(), curses.KEY_RIGHT, 10)
    tui._handle_key(Canvas(7, 25), "\n", 1)
    assert not tui._file_transfer.cancelled
    tui._handle_key(Canvas(), "\x1b", 10)
    assert not tui._file_transfer.cancelled


def test_mutation_remains_blocked_until_terminal_ownership_released():
    tui = make_tui(snapshot(state="failed"))
    tui._file_transfer.busy = True
    tui.input_text = "/reboot"
    tui._submit_input()
    assert not tui.sent
    tui._file_transfer.busy = False
    tui._submit_input()
    assert tui.sent == ["/reboot"]


@pytest.mark.parametrize("text", ["A界e\u0301👩\u200d💻🇷🇺.bin", "я" * 255, "x\x00\t\x1b[2J.txt"])
@pytest.mark.parametrize("width", [1, 2, 8, 40])
def test_unicode_layout_respects_terminal_cells(text, width):
    safe = screen_safe_text(text)
    assert cell_width(fit_cells(safe, width)) <= width
    assert cell_width(middle_ellipsis(safe, width)) <= width
    assert all(cell_width(row) <= width for row in wrap_cells(safe, width))


def test_terminal_window_keeps_result_and_no_fake_eta_during_repair():
    for state in ("repairing", "waiting_result", "completed", "failed", "cancelled"):
        canvas = Canvas(30, 120)
        value = snapshot(state=state)
        if state == "failed": value["failure"] = {"code": "remote_failed", "message": "remote storage"}
        view = FileTransferWindow()
        view.sync(snapshot())
        view.sync(value)
        if state == "completed":
            view.handle_key(curses.KEY_F7, value)
            assert not view.visible
            render(view, canvas, value)
            assert not canvas.calls
            continue
        render(view, canvas, value)
        text = "\n".join(call[2] for call in canvas.calls)
        assert TerminalTui.file_state_label(state) in text
        assert "ETA DATA —" in text
        if state == "failed": assert "remote_failed" in text


def test_generic_profile_never_claims_knowledge_of_chatter_commands():
    from serialterminal.profiles.base import SendLine
    assert not GENERIC_PROFILE.human_action_is_non_disruptive(SendLine("/tele"))


def test_filename_preflight_failure_is_written_to_console_without_false_start(monkeypatch, tmp_path):
    from serialterminal.file_transfer import FileTransferError
    tui = make_tui(snapshot(state="completed"))
    path = tmp_path / ("a" * 163)
    path.write_bytes(b"payload")
    monkeypatch.setattr("serialterminal.tui_core.browse_file", lambda *args, **kwargs: path)
    def reject(source):
        assert source == path
        raise FileTransferError("filename_too_long", "Имя файла слишком длинное: 163 байт UTF-8, максимум 162")
    tui._file_transfer.start_send = reject
    tui._choose_file(Canvas())
    assert any("Имя файла слишком длинное" in line for line in tui.output.snapshot())
    assert "started" not in tui.status
    assert not tui._file_transfer.cancelled and not tui.sent


@pytest.mark.parametrize("line", ["/diag on", "/heartbeat on", "/radio repair config", "/errors clear"])
def test_controller_mutations_are_not_admitted_during_file(line):
    tui = make_tui()
    tui.input_text = line
    tui._submit_input()
    assert not tui.sent and not tui._file_transfer.cancelled


def test_preparation_is_not_presented_as_wire_throughput():
    canvas = Canvas(30, 120)
    render(FileTransferWindow(), canvas, snapshot(state="compressing", original_bytes=100))
    text = "\n".join(call[2] for call in canvas.calls)
    assert "Подготовка 40/100 source bytes" in text
    assert "wire bytes" not in text and "kbit/s" not in text
    assert "ETA DATA —" in text


@pytest.mark.parametrize("operation", ["fit", "wrap", "ellipsis"])
def test_unicode_layout_work_is_linear_in_text_length(monkeypatch, operation):
    from serialterminal import tui_text
    text = "я界e\u0301👩\u200d💻🇷🇺" * 100
    calls = 0
    original = tui_text._wcwidth
    def counted(char):
        nonlocal calls
        calls += 1
        return original(char)
    monkeypatch.setattr(tui_text, "_wcwidth", counted)
    if operation == "fit":
        assert fit_cells(text, 10000) == text
    elif operation == "wrap":
        assert "".join(wrap_cells(text, 80)) == text
    else:
        result = middle_ellipsis(text, 200)
        assert "…" in result and cell_width(result) <= 200
    assert calls <= len(text) * 4


@pytest.mark.parametrize("state", ["sending", "completed"])
def test_f10_does_not_control_transfer_or_change_command_input(state):
    tui = make_tui(snapshot(state=state))
    tui.input_text = "draft"
    before = tui._file_snapshot()
    tui._handle_key(Canvas(), curses.KEY_F10, 10)
    assert tui._file_snapshot() == before
    assert tui.input_text == "draft" and not tui.sent and not tui._file_transfer.cancelled
    canvas = Canvas()
    render(tui._file_window(), canvas, before)
    assert not any("F10" in call[2] for call in canvas.calls)


@pytest.mark.parametrize("colors,expected", [(256, [(8, 255, 236), (9, 141, 236), (10, 236, 141)]),
                                          (8, [(8, 7, 0), (9, 5, 0), (10, 0, 5)])])
def test_file_window_dracula_palette_is_separate_from_general_tui(monkeypatch, colors, expected):
    from serialterminal.tui_file_transfer import init_file_transfer_colors
    calls = []
    monkeypatch.setattr(curses, "COLORS", colors, raising=False)
    monkeypatch.setattr(curses, "init_pair", lambda *args: calls.append(args))
    monkeypatch.setattr(curses, "color_pair", lambda pair: pair << 8)
    attrs = init_file_transfer_colors()
    assert calls == expected
    assert attrs == {"file": 8 << 8, "file_border": 9 << 8,
                     "file_selected": (10 << 8) | curses.A_BOLD}


def test_file_window_title_border_body_and_selected_button_have_distinct_styles():
    view, canvas, value = FileTransferWindow(), Canvas(), snapshot()
    view.request_cancel(value)
    view.draw(canvas, canvas.draw, value, bar=TerminalTui.render_progress_bar,
              state_label=TerminalTui.file_state_label, rate=0, attr=3, border=5, selected=9)
    assert all(call[3] == (5 | curses.A_BOLD) for call in canvas.calls if call[2].startswith("┌"))
    assert all(call[3] == 5 for call in canvas.calls if call[2] in {"│"} or call[2].startswith("└"))
    assert any("файл.bin" in call[2] and call[3] == 3 for call in canvas.calls)
    assert next(call[3] for call in canvas.calls if call[2] == "[ Да ]") == 9


@pytest.mark.parametrize("direction", ["TX", "RX"])
def test_success_closes_progress_and_f7_cannot_reopen_retained_result(direction):
    tui = make_tui(snapshot(direction=direction))
    view = tui._file_window()
    view.sync(tui._file_snapshot())
    assert view.visible
    tui._file_transfer.value["state"] = "completed"
    canvas = Canvas()
    render(view, canvas, tui._file_snapshot())
    assert not view.visible and not canvas.calls
    assert tui._file_header_lines(80) == ()
    assert tui._file_snapshot()["state"] == "completed"
    tui._handle_key(Canvas(), curses.KEY_F7, 10)
    canvas = Canvas()
    render(view, canvas, tui._file_snapshot())
    assert not view.visible and not canvas.calls


@pytest.mark.parametrize("state", ["failed", "cancelled"])
def test_unsuccessful_outcome_does_not_auto_close(state):
    view = FileTransferWindow()
    view.sync(snapshot())
    canvas = Canvas()
    render(view, canvas, snapshot(state=state))
    assert view.visible and any("Передача файла" in call[2] for call in canvas.calls)


def test_success_during_confirmation_closes_progress_but_keeps_visible_stale_enter_guard():
    tui = make_tui()
    tui._handle_key(Canvas(), "\x1b", 10)
    tui._file_transfer.value["state"] = "completed"
    canvas = Canvas()
    render(tui._file_window(), canvas, tui._file_snapshot())
    text = "\n".join(call[2] for call in canvas.calls)
    assert "Передача файла" not in text and "Операция завершилась" in text
    tui._handle_key(canvas, "\n", 10)
    assert not tui.sent and not tui._file_transfer.cancelled
    assert tui._file_window().confirmation_id is None


@pytest.mark.parametrize("direction,state", [("TX", "sending"), ("RX", "receiving")])
def test_confirmed_cancel_keeps_result_until_explicit_escape(direction, state):
    tui = make_tui(snapshot(direction=direction, state=state))
    tui.input_text = "draft"
    tui._handle_key(Canvas(), "\x1b", 10)
    tui._handle_key(Canvas(), "\n", 10)
    view = tui._file_window()
    canvas = Canvas()
    render(view, canvas, tui._file_snapshot())
    assert tui._file_transfer.cancelled == ["0000000000000001"]
    assert tui._file_snapshot()["state"] == "cancelled"
    assert view.confirmation_id is None and view.visible and canvas.calls
    assert tui._file_header_lines(80) == ()
    assert tui.input_text == "draft" and not tui.sent
    tui._handle_key(Canvas(), curses.KEY_F7, 10)
    assert view.visible
    tui._handle_key(Canvas(), "\x1b", 10)
    canvas = Canvas()
    render(view, canvas, tui._file_snapshot())
    assert not view.visible and not canvas.calls


@pytest.mark.parametrize("outcome", ["cancelled", "failed"])
def test_confirmed_async_receiver_cancel_keeps_pending_and_terminal_visible(outcome):
    tui = make_tui(snapshot(direction="RX", state="receiving"))
    manager = tui._file_transfer
    # Настоящий RX cancel сначала ставит событие в очередь, worker завершает позже.
    manager.cancel = manager.cancelled.append
    tui._handle_key(Canvas(), "\x1b", 10)
    tui._handle_key(Canvas(), "\n", 10)
    view = tui._file_window()
    canvas = Canvas()
    render(view, canvas, tui._file_snapshot())
    assert manager.busy and tui._file_transfer_active()
    assert view.visible and any("отмена: ожидание завершения" in call[2] for call in canvas.calls)
    manager.value["state"] = outcome
    manager.busy = False
    canvas = Canvas()
    render(view, canvas, tui._file_snapshot())
    assert view.visible and any("Передача файла" in c[2] for c in canvas.calls)
    assert tui._file_header_lines(80) == ()
    tui._handle_key(Canvas(), "\x1b", 10)
    tui._handle_key(Canvas(), curses.KEY_F7, 10)
    canvas = Canvas()
    render(view, canvas, tui._file_snapshot())
    assert not view.visible and not canvas.calls
    manager.value.update(transfer_id="0000000000000002", state="receiving")
    render(view, Canvas(), tui._file_snapshot())
    assert view.visible and view.transfer_id == "0000000000000002"


def test_rejected_cancel_keeps_progress_visible():
    from serialterminal.file_transfer import FileTransferError
    tui = make_tui(snapshot(direction="RX", state="receiving"))
    def reject(ident):
        raise FileTransferError("cancel_failed", "Не удалось отменить")
    tui._file_transfer.cancel = reject
    tui._handle_key(Canvas(), "\x1b", 10)
    tui._handle_key(Canvas(), "\n", 10)
    canvas = Canvas()
    render(tui._file_window(), canvas, tui._file_snapshot())
    assert tui._file_window().visible and canvas.calls
    assert "Отмена не выполнена" in tui.status


@pytest.mark.parametrize("direction", ["TX", "RX"])
@pytest.mark.parametrize("state,text", [("completed", "успешно"), ("failed", "ошибка"),
                                        ("cancelled", "прервано пользователем")])
@pytest.mark.parametrize("visible", [True, False])
def test_terminal_record_writes_one_white_status_without_render_or_window_close(direction, state, text, visible):
    from serialterminal.file_transfer.core import _TransferRecord, FileTransferError
    tui = make_tui(snapshot(direction=direction))
    tui._file_window().visible = visible
    record = _TransferRecord(1, direction=direction, filename="ERROR\nFAILED.bin",
                             event_retention=32,
                             event_sink=lambda e: tui._log_file_transfer_event(e, manager=tui._file_transfer))
    record.event("progress", progress={"percentage": 100.0})
    record.event("remote_result", ok=True)
    assert tui.output.snapshot() == []
    failure = FileTransferError("storage_failed", "FAILED\x1b[2J\nдиск полон") if state == "failed" else None
    record.terminal(state, failure=failure)
    record.terminal(state, failure=failure)
    lines = [line for line in tui.output.snapshot() if line.startswith("[FT1] ")]
    assert len(lines) == 1
    line = lines[0]
    assert line.startswith(f"[FT1] {direction} «ERROR\\nFAILED.bin»: {text}")
    if state == "failed":
        assert "storage_failed" in line and "диск полон" in line and "\\x1b" in line
    colors = {"normal": 1, "error": 2, "status": 3, "panel": 4}
    assert tui._line_attr(line, colors) == colors["normal"]
    assert tui._file_window().visible is visible


def test_recursive_service_completion_is_logged_but_not_announced_as_file_success():
    tui = make_tui()
    primary = []
    tui.session._record_primary = lambda marker, text: primary.append((marker, text))
    tui._log_file_transfer_event({"kind": "transfer_completed", "transfer_id": "0000000000000002",
                                  "direction": "TX", "filename": "missing-list", "progress": {}},
                                 manager=tui._file_transfer)
    assert len(primary) == 1 and primary[0][0] == "FT1"
    assert tui.output.snapshot() == []


def test_new_attempt_with_same_transfer_id_announces_its_own_terminal_outcome():
    from serialterminal.file_transfer.core import _TransferRecord
    tui = make_tui()
    for state in ("failed", "completed"):
        record = _TransferRecord(1, direction="TX", filename="file.bin", event_retention=16,
                                 event_sink=lambda e: tui._log_file_transfer_event(e, manager=tui._file_transfer))
        record.terminal(state)
    lines = [line for line in tui.output.snapshot() if line.startswith("[FT1] ")]
    assert len(lines) == 2
    assert "ошибка" in lines[0] and "успешно" in lines[1]


@pytest.mark.parametrize("state", ["completed", "failed", "cancelled"])
def test_f7_never_opens_a_hidden_terminal_window(state):
    tui = make_tui(snapshot(state=state))
    view = tui._file_window()
    view.sync(tui._file_snapshot())
    tui._handle_key(Canvas(), "\x1b", 10)
    for _ in range(2):
        tui._handle_key(Canvas(), curses.KEY_F7, 10)
        canvas = Canvas()
        render(view, canvas, tui._file_snapshot())
        assert not view.visible and not canvas.calls
        assert tui._file_header_lines(80) == ()


def test_terminal_chat_status_is_separate_from_unfinished_received_line():
    tui = make_tui()
    tui.output.write("RX fragment ERROR without newline")
    tui._log_file_transfer_event({"kind": "transfer_completed", "transfer_id": "0000000000000001",
                                  "direction": "TX", "filename": "file.bin", "progress": {}},
                                 manager=tui._file_transfer)
    assert tui.output.snapshot() == ["RX fragment ERROR without newline", "[FT1] TX «file.bin»: успешно"]


@pytest.mark.parametrize("state", ["sending", "receiving", "repairing", "recovering_local_node",
                                    "waiting_result", "completed", "failed", "cancelled"])
@pytest.mark.parametrize("command", ["/clear", "  /clear\t"])
def test_local_clear_empties_chat_and_scrollback_without_touching_transfer(state, command):
    tui = make_tui(snapshot(state=state))
    manager, session = tui._file_transfer, tui.session
    original = manager.value.copy()
    tui.output.write("old line\n" * 40 + "partial")
    tui.scrollback.scroll_up(5, width=78, body_rows=10)
    assert not tui.scrollback.follow_tail
    tui.input_text = command
    tui.input_cursor = len(command)
    tui._handle_key(Canvas(), "\n", 10)
    assert tui.output.snapshot() == []
    assert tui.scrollback.follow_tail
    assert tui.input_text == "" and tui.input_cursor == 0
    assert tui.command_history == [command]
    assert "Screen cleared" in tui.status
    assert not tui.sent and not tui.actions and not manager.cancelled
    assert tui._file_transfer is manager and tui.session is session
    assert manager.value == original


def test_clear_is_frontend_local_for_generic_profile_too():
    tui = make_tui()
    tui.profile = GENERIC_PROFILE
    tui.input_text = "/clear"
    tui.output.write("old output\n")
    tui._submit_input()
    assert tui.output.snapshot() == [] and not tui.sent


def test_clear_command_requires_exact_command_without_arguments():
    tui = make_tui(snapshot(state="completed"))
    tui.output.write("keep\n")
    tui.input_text = "/clear anything"
    tui._submit_input()
    assert tui.output.snapshot() == ["keep"]
    assert tui.sent == ["/clear anything"]


def test_f4_and_clear_share_screen_action_but_f4_preserves_input_draft():
    tui = make_tui()
    tui.input_text = "draft"
    tui.input_cursor = 3
    tui.output.write("old\n")
    tui._handle_key(Canvas(), curses.KEY_F4, 10)
    assert tui.output.snapshot() == [] and tui.scrollback.follow_tail
    assert tui.input_text == "draft" and tui.input_cursor == 3
    assert not tui.sent and not tui._file_transfer.cancelled


def test_f9_help_includes_local_clear_command():
    tui = make_tui()
    shown = []
    tui.session._show_full_help = lambda: shown.append(True)
    tui._handle_key(Canvas(), curses.KEY_F9, 10)
    assert shown == [True]
    text = "\n".join(tui.output.snapshot())
    assert "/clear" in text and "F4" in text
    assert not tui.sent and not tui._file_transfer.cancelled


def test_local_clear_does_not_release_settling_transfer_ownership():
    tui = make_tui(snapshot(state="completed"))
    tui._file_transfer.busy = True
    tui.input_text = "/clear"
    tui.output.write("old\n")
    tui._submit_input()
    assert tui.output.snapshot() == []
    assert tui._file_transfer.busy and tui._file_transfer_active()
    assert not tui.sent and not tui._file_transfer.cancelled
