from serialterminal.profiles.chatter.tui import ChatterTuiPanel
from serialterminal.tui import TuiOutputBuffer, TuiScrollback


def test_tui_output_buffer_keeps_complete_and_partial_lines():
    buffer = TuiOutputBuffer(max_lines=4)
    buffer.write("one\ntwo")
    assert buffer.snapshot() == ["one", "two"]
    buffer.write(" continued\nthree\n")
    assert buffer.snapshot() == ["one", "two continued", "three"]


def test_tui_output_buffer_is_bounded_and_clearable():
    buffer = TuiOutputBuffer(max_lines=2)
    buffer.write("one\ntwo\nthree\n")
    assert buffer.snapshot() == ["two", "three"]
    buffer.clear()
    assert buffer.snapshot() == []


def test_chatter_tui_panel_tracks_radio_and_link_status():
    panel = ChatterTuiPanel()
    panel.consume_line("chat", "[SYS] CHATTER NODE LoRa-Chatter-1B44")
    panel.consume_line(
        "chat",
        "[SYS] CFG RADIO power=2 dBm freq=470 MHz sf=7 bw=500 kHz",
    )
    panel.consume_line(
        "telemetry",
        "[SYS] CFG LINK heartbeat=OFF retry=ON attempts=5 diag=OFF",
    )
    panel.consume_line(
        "telemetry",
        "RX USER session=118C seq=3 frame=20B user=8B RX=-42/7 Q96 disposition=0",
    )
    lines = panel.status_lines()
    assert "LoRa-Chatter-1B44" in lines[0]
    assert "470 MHz" in lines[0]
    assert "SF7" in lines[0]
    assert "BW 500 kHz" in lines[0]
    assert "2 dBm" in lines[0]
    assert "heartbeat=OFF" in lines[1]
    assert "retry=ON/5" in lines[1]
    assert "diag=OFF" in lines[1]
    assert "last RX -42/7 Q96" in lines[1]


def test_chatter_tui_panel_refresh_is_profile_owned():
    panel = ChatterTuiPanel()
    assert [action.text for action in panel.connected_actions()] == [
        "/id",
        "/config",
    ]



def test_tui_progress_bar_is_determinate_and_bounded():
    from serialterminal.tui import TerminalTui

    assert TerminalTui.render_progress_bar(0, 10) == "░" * 10
    assert TerminalTui.render_progress_bar(50, 10) == "█" * 5 + "░" * 5
    assert TerminalTui.render_progress_bar(100, 10) == "█" * 10
    assert TerminalTui.render_progress_bar(150, 10) == "█" * 10



def test_tui_file_recovery_states_are_human_readable():
    from serialterminal.tui import TerminalTui

    assert (
        TerminalTui.file_state_label("waiting_result")
        == "waiting for remote verification"
    )
    assert TerminalTui.file_state_label("repair_requested") == "repair requested"
    assert TerminalTui.file_state_label("repairing") == "repairing"
    assert TerminalTui.file_state_label("completed") == "completed"



def test_tui_output_buffer_assigns_stable_ids_across_partial_writes():
    buffer = TuiOutputBuffer(max_lines=4)
    buffer.write("hel")
    first = buffer.entries()
    assert [(item.line_id, item.text) for item in first] == [(1, "hel")]

    buffer.write("lo\nnext")
    second = buffer.entries()
    assert [(item.line_id, item.text) for item in second] == [
        (1, "hello"),
        (2, "next"),
    ]


def test_tui_output_wraps_long_logical_lines_into_visual_rows():
    buffer = TuiOutputBuffer()
    buffer.write("abcdefghij\n")

    rows = buffer.visual_rows(4)

    assert [(row.line_id, row.char_start, row.text) for row in rows] == [
        (1, 0, "abcd"),
        (1, 4, "efgh"),
        (1, 8, "ij"),
    ]


def test_tui_scrollback_freezes_anchor_while_new_output_arrives():
    buffer = TuiOutputBuffer()
    buffer.write("0\n1\n2\n3\n4\n")
    scroll = TuiScrollback(buffer)

    assert [row.text for row in scroll.visible_rows(20, 3)] == ["2", "3", "4"]
    scroll.scroll_up(2, width=20, body_rows=3)
    assert [row.text for row in scroll.visible_rows(20, 3)] == ["0", "1", "2"]

    buffer.write("5\n6\n")
    assert [row.text for row in scroll.visible_rows(20, 3)] == ["0", "1", "2"]
    assert scroll.new_line_count() == 2
    assert scroll.rows_above_bottom(width=20, body_rows=3) == 4


def test_tui_scrollback_page_down_returns_to_follow_tail():
    buffer = TuiOutputBuffer()
    buffer.write("0\n1\n2\n3\n4\n")
    scroll = TuiScrollback(buffer)
    scroll.scroll_up(2, width=20, body_rows=3)
    assert scroll.follow_tail is False

    scroll.scroll_down(20, width=20, body_rows=3)

    assert scroll.follow_tail is True
    assert [row.text for row in scroll.visible_rows(20, 3)] == ["2", "3", "4"]
    assert scroll.new_line_count() == 0


def test_tui_scrollback_anchor_survives_wrap_width_change():
    buffer = TuiOutputBuffer()
    buffer.write("abcdefghij\nsecond\nthird\n")
    scroll = TuiScrollback(buffer)
    scroll.scroll_up(2, width=4, body_rows=2)
    before = scroll.visible_rows(4, 2)
    assert before[0].line_id == 1

    after = scroll.visible_rows(6, 2)

    assert after[0].line_id == 1
    assert after[0].char_start <= before[0].char_start


def test_tui_mouse_wheel_direction_recognizes_button_masks(monkeypatch):
    from serialterminal.tui import TerminalTui

    monkeypatch.setattr("serialterminal.tui.curses.BUTTON4_PRESSED", 0x01)
    monkeypatch.setattr("serialterminal.tui.curses.BUTTON5_PRESSED", 0x02)

    assert TerminalTui._mouse_wheel_direction(0x01) == -1
    assert TerminalTui._mouse_wheel_direction(0x02) == 1
    assert TerminalTui._mouse_wheel_direction(0x00) == 0
