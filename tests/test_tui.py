from serialterminal.profiles.chatter.tui import ChatterTuiPanel
from serialterminal.tui import TuiOutputBuffer


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
