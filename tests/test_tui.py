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
    panel.consume_line(
        "telemetry",
        (
            "RX HEARTBEAT PONG request=118C/4 frame=16B "
            "RX=-116/-18 TX=-111/-12 Q87"
        ),
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
    assert panel.header_status() == "RX -116/-18 | TX -111/-12 | Q87"


def test_chatter_tui_panel_refresh_is_profile_owned():
    panel = ChatterTuiPanel()
    assert [action.text for action in panel.connected_actions()] == [
        "/config",
    ]


def test_chatter_tui_panel_uses_transport_identity_before_id_response():
    panel = ChatterTuiPanel()

    panel.set_transport_identity("LoRa-Chatter-1B44")

    assert panel.status_lines()[0].startswith(
        "Radio  LoRa-Chatter-1B44 |"
    )


def test_chatter_tui_firmware_identity_overrides_transport_seed():
    panel = ChatterTuiPanel()
    panel.set_transport_identity("Advertised-Name")

    panel.consume_line(
        "chat",
        "[SYS] CHATTER NODE LoRa-Chatter-72E0",
    )

    assert panel.status_lines()[0].startswith(
        "Radio  LoRa-Chatter-72E0 |"
    )



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
    scroll.scroll_up(3, width=4, body_rows=2)
    before = scroll.visible_rows(4, 2)
    assert before[0].line_id == 1
    assert before[0].char_start == 8

    after = scroll.visible_rows(6, 2)

    assert after[0].line_id == 1
    assert after[0].char_start == 6


def test_tui_mouse_wheel_direction_recognizes_button_masks(monkeypatch):
    from serialterminal.tui import TerminalTui

    monkeypatch.setattr("serialterminal.tui.curses.BUTTON4_PRESSED", 0x01)
    monkeypatch.setattr("serialterminal.tui.curses.BUTTON5_PRESSED", 0x02)

    assert TerminalTui._mouse_wheel_direction(0x01) == -1
    assert TerminalTui._mouse_wheel_direction(0x02) == 1
    assert TerminalTui._mouse_wheel_direction(0x00) == 0



def test_chatter_tui_header_status_tracks_diag_directional_metrics():
    panel = ChatterTuiPanel()

    panel.consume_line(
        "chat",
        "[LNK OK]   RX -116/-18  TX -111/-12  Q87 ",
    )
    assert panel.header_status() == "RX -116/-18 | TX -111/-12 | Q87"

    panel.consume_line(
        "chat",
        "[LNK NRP]  RX  ---/---  TX  ---/---  Q82 ",
    )
    assert panel.header_status() == "RX ---/--- | TX ---/--- | Q82"


def test_chatter_tui_header_status_updates_q_on_normal_heartbeat_timeout():
    panel = ChatterTuiPanel()
    panel.consume_line(
        "telemetry",
        (
            "RX HEARTBEAT PONG request=118C/4 frame=16B "
            "RX=-116/-18 TX=-111/-12 Q87"
        ),
    )
    panel.consume_line(
        "telemetry",
        "HEARTBEAT TIMEOUT request=118C/5 outcome=NRP Q=82 recovery=1 jitter<=10ms",
    )

    assert panel.header_status() == "RX -116/-18 | TX -111/-12 | Q82"


def test_tui_header_composition_keeps_profile_status_right_aligned():
    from serialterminal.tui import TerminalTui

    header = TerminalTui._compose_header(
        " SerialTerminal | very-long-device | profile:chatter",
        "CONNECTED | RX -116/-18 | TX -111/-12 | Q87",
        90,
    )

    assert len(header) == 90
    assert header.endswith(" CONNECTED | RX -116/-18 | TX -111/-12 | Q87 ")



def test_tui_scrollback_scrollbar_geometry_tracks_viewport():
    from serialterminal.tui import TerminalTui

    assert TerminalTui._scrollbar_geometry(5, 0, 10) is None
    top = TerminalTui._scrollbar_geometry(100, 0, 20)
    middle = TerminalTui._scrollbar_geometry(100, 40, 20)
    bottom = TerminalTui._scrollbar_geometry(100, 80, 20)

    assert top == (0, 4)
    assert middle == (8, 4)
    assert bottom == (16, 4)


def test_tui_scrollback_scroll_to_row_and_follow():
    buffer = TuiOutputBuffer()
    buffer.write("0\n1\n2\n3\n4\n5\n")
    scroll = TuiScrollback(buffer)

    scroll.scroll_to_row(1, width=20, body_rows=3)
    assert scroll.follow_tail is False
    assert [row.text for row in scroll.visible_rows(20, 3)] == ["1", "2", "3"]

    scroll.scroll_to_row(99, width=20, body_rows=3)
    assert scroll.follow_tail is True
    assert [row.text for row in scroll.visible_rows(20, 3)] == ["3", "4", "5"]


def test_tui_command_history_up_down_restores_draft():
    from serialterminal.tui import TerminalTui

    tui = object.__new__(TerminalTui)
    tui.command_history = ["/help", "/config"]
    tui.history_index = None
    tui.history_draft = ""
    tui.input_text = "draft"
    tui.input_cursor = len(tui.input_text)

    tui._history_up()
    assert tui.input_text == "/config"
    tui._history_up()
    assert tui.input_text == "/help"
    tui._history_down()
    assert tui.input_text == "/config"
    tui._history_down()
    assert tui.input_text == "draft"
    assert tui.history_index is None


def test_tui_command_history_is_bounded_and_deduplicates_adjacent():
    from serialterminal.tui import TerminalTui

    tui = object.__new__(TerminalTui)
    tui.command_history = []
    tui.history_index = None
    tui.history_draft = ""

    tui._remember_command("/help")
    tui._remember_command("/help")
    for index in range(600):
        tui._remember_command(f"/x {index}")

    assert len(tui.command_history) == 500
    assert tui.command_history[-1] == "/x 599"



class _FenceSession:
    def capture_tx_fence(self):
        return 17

    def wait_tx_fence(self, fence, timeout):
        assert fence == 17
        assert timeout == 10.0


def test_tui_file_transfer_mutes_session_screen_until_release():
    import threading

    from serialterminal.tui import TerminalTui

    tui = object.__new__(TerminalTui)
    tui.output = TuiOutputBuffer()
    tui.session = _FenceSession()
    tui._file_transfer_screen_muted = threading.Event()

    tui._write_session_screen("before\n")
    tui._claim_file_transfer(1, "TX")
    tui._write_session_screen(
        "DELIVERY ACK user=1234/1 attempts=1/5 elapsed=49ms queue=0\n"
    )
    tui._write_session_screen("[SYS] OUTPUT BOTH\n")
    assert tui.output.snapshot() == ["before"]

    tui._write_session_screen(
        "[SYS] RADIO FATAL RX_RESTART after TX (-16), rebooting\n"
    )
    tui._write_session_screen("ESP-ROM:esp32s3-20210327\n")
    tui._write_session_screen("[SYS] CHATTER READY\n")
    assert tui.output.snapshot() == [
        "before",
        "[SYS] RADIO FATAL RX_RESTART after TX (-16), rebooting",
        "ESP-ROM:esp32s3-20210327",
        "[SYS] CHATTER READY",
    ]

    tui._release_file_transfer(1, "TX")
    tui._write_session_screen("after\n")
    assert tui.output.snapshot() == [
        "before",
        "[SYS] RADIO FATAL RX_RESTART after TX (-16), rebooting",
        "ESP-ROM:esp32s3-20210327",
        "[SYS] CHATTER READY",
        "after",
    ]


def test_tui_file_transfer_screen_mute_does_not_block_line_observer():
    import threading

    from serialterminal.session import SessionLine
    from serialterminal.tui import TerminalTui

    class _Panel:
        def __init__(self):
            self.lines = []

        def consume_line(self, stream, line):
            self.lines.append((stream, line))

    class _Adapter:
        def __init__(self):
            self.lines = []

        def feed_line(self, stream, line):
            self.lines.append((stream, line))

    tui = object.__new__(TerminalTui)
    tui.output = TuiOutputBuffer()
    tui._file_transfer_screen_muted = threading.Event()
    tui._file_transfer_screen_muted.set()
    tui.panel = _Panel()
    tui._binary_adapter = _Adapter()

    line = SessionLine(
        stream="main",
        seq_first=1,
        seq_last=1,
        text="DELIVERY ACK user=1234/1 attempts=1/5 elapsed=49ms queue=0",
        timestamp=1.0,
    )
    tui._observe_line(line)
    tui._write_session_screen(line.text + "\n")

    assert tui.output.snapshot() == []
    assert tui.panel.lines == [("main", line.text)]
    assert tui._binary_adapter.lines == [("main", line.text)]



def test_tui_file_wire_rate_uses_recent_wire_bytes():
    from collections import deque

    from serialterminal.tui import TerminalTui

    tui = object.__new__(TerminalTui)
    tui._file_rate_transfer_id = None
    tui._file_rate_samples = deque()

    snapshot = {"transfer_id": "abc", "bytes_completed": 0}
    assert tui._file_wire_rate_kbit_s(snapshot, now=10.0) == 0.0

    snapshot["bytes_completed"] = 1000
    assert tui._file_wire_rate_kbit_s(snapshot, now=11.0) == 8.0

    snapshot["bytes_completed"] = 2000
    assert tui._file_wire_rate_kbit_s(snapshot, now=12.0) == 8.0


def test_tui_file_wire_rate_resets_for_new_transfer():
    from collections import deque

    from serialterminal.tui import TerminalTui

    tui = object.__new__(TerminalTui)
    tui._file_rate_transfer_id = None
    tui._file_rate_samples = deque()

    first = {"transfer_id": "one", "bytes_completed": 0}
    tui._file_wire_rate_kbit_s(first, now=1.0)
    first["bytes_completed"] = 1000
    assert tui._file_wire_rate_kbit_s(first, now=2.0) == 8.0

    second = {"transfer_id": "two", "bytes_completed": 500}
    assert tui._file_wire_rate_kbit_s(second, now=3.0) == 0.0


def test_tui_file_status_shows_wire_rate_right_of_wire_bytes(monkeypatch):
    from collections import deque

    from serialterminal.tui import TerminalTui

    tui = object.__new__(TerminalTui)
    tui._file_rate_transfer_id = None
    tui._file_rate_samples = deque()
    snapshots = [
        {
            "transfer_id": "abc",
            "direction": "TX",
            "filename": "Ritta02.webp",
            "percentage": 6.5,
            "state": "sending",
            "chunks_completed": 32,
            "chunks_total": 495,
            "bytes_completed": 0,
            "wire_bytes": 112208,
        },
        {
            "transfer_id": "abc",
            "direction": "TX",
            "filename": "Ritta02.webp",
            "percentage": 6.5,
            "state": "sending",
            "chunks_completed": 32,
            "chunks_total": 495,
            "bytes_completed": 1000,
            "wire_bytes": 112208,
        },
    ]
    tui._file_transfer = object()
    monkeypatch.setattr(tui, "_file_snapshot", lambda: snapshots.pop(0))
    monkeypatch.setattr("serialterminal.tui.time.monotonic", lambda: 10.0)
    tui._file_status_lines(120)
    monkeypatch.setattr("serialterminal.tui.time.monotonic", lambda: 11.0)
    lines = tui._file_status_lines(120)

    assert lines[1].endswith("1000/112208 wire bytes  8.0 kbit/s")



def test_chatter_tui_header_updates_rx_and_q_from_user_traffic():
    now = {"value": 100.0}
    panel = ChatterTuiPanel(clock=lambda: now["value"])

    panel.consume_line(
        "telemetry",
        "RX USER session=792D seq=204 frame=255B user=243B RX=-16/5 Q100 disposition=0",
    )

    assert panel.header_status() == "RX -16/5 | TX ---/--- | Q100"


def test_chatter_tui_link_metrics_expire_independently_by_ttl():
    now = {"value": 0.0}
    panel = ChatterTuiPanel(
        link_metric_ttl_s=15.0,
        clock=lambda: now["value"],
    )

    panel.consume_line(
        "telemetry",
        (
            "RX HEARTBEAT PONG request=118C/4 frame=16B "
            "RX=-116/-18 TX=-111/-12 Q87"
        ),
    )
    assert panel.header_status() == "RX -116/-18 | TX -111/-12 | Q87"

    now["value"] = 10.0
    panel.consume_line(
        "telemetry",
        "RX USER session=792D seq=204 frame=255B user=243B RX=-16/5 Q100 disposition=0",
    )

    now["value"] = 16.0
    assert panel.header_status() == "RX -16/5 | TX ---/--- | Q100"

    now["value"] = 26.0
    assert panel.header_status() == "RX ---/--- | TX ---/--- | Q---"


def test_chatter_tui_heartbeat_timeout_refreshes_only_q_ttl():
    now = {"value": 0.0}
    panel = ChatterTuiPanel(
        link_metric_ttl_s=15.0,
        clock=lambda: now["value"],
    )
    panel.consume_line(
        "telemetry",
        (
            "RX HEARTBEAT PONG request=118C/4 frame=16B "
            "RX=-116/-18 TX=-111/-12 Q87"
        ),
    )

    now["value"] = 16.0
    panel.consume_line(
        "telemetry",
        "HEARTBEAT TIMEOUT request=118C/5 outcome=NRP Q=82 recovery=1 jitter<=10ms",
    )

    assert panel.header_status() == "RX ---/--- | TX ---/--- | Q82"

    now["value"] = 32.0
    assert panel.header_status() == "RX ---/--- | TX ---/--- | Q---"



def test_tui_completed_file_status_shows_only_saved_filename(monkeypatch):
    from collections import deque

    from serialterminal.tui import TerminalTui

    tui = object.__new__(TerminalTui)
    tui._file_rate_transfer_id = None
    tui._file_rate_samples = deque()
    tui._file_transfer = object()
    snapshot = {
        "transfer_id": "done",
        "direction": "RX",
        "filename": "Ritta02.webp",
        "percentage": 100.0,
        "state": "completed",
        "chunks_completed": 495,
        "chunks_total": 495,
        "bytes_completed": 112208,
        "wire_bytes": 112208,
        "final_path": "/home/dream/coding/python/serialterminal/files/Ritta02 (1).webp",
    }
    monkeypatch.setattr(tui, "_file_snapshot", lambda: snapshot)
    monkeypatch.setattr("serialterminal.tui.time.monotonic", lambda: 10.0)

    lines = tui._file_status_lines(160)

    assert lines[1].endswith(
        "112208/112208 wire bytes  0.0 kbit/s  -> Ritta02 (1).webp"
    )
    assert "/home/dream/" not in lines[1]



def test_tui_file_transfer_mute_keeps_reconnect_status_visible():
    import threading

    from serialterminal.tui import TerminalTui

    tui = object.__new__(TerminalTui)
    tui.output = TuiOutputBuffer()
    tui._file_transfer_screen_muted = threading.Event()
    tui._file_transfer_screen_muted.set()

    tui._write_session_screen("[disconnected: serial:/dev/fake]\n")
    tui._write_session_screen("ordinary chatter line\n")
    tui._write_session_screen("[waiting for selected device...]\n")
    tui._write_session_screen("[connected: serial:/dev/fake]\n")

    assert tui.output.snapshot() == [
        "[disconnected: serial:/dev/fake]",
        "[waiting for selected device...]",
        "[connected: serial:/dev/fake]",
    ]



def test_tui_ft1_event_logger_skips_progress_and_records_send_stage():
    from serialterminal.tui import TerminalTui

    class _Session:
        def __init__(self):
            self.records = []

        def _record_primary(self, marker, text):
            self.records.append((marker, text))

    tui = object.__new__(TerminalTui)
    tui.session = _Session()

    tui._log_file_transfer_event(
        {
            "transfer_id": "1234",
            "direction": "TX",
            "filename": "x.bin",
            "kind": "progress",
        }
    )
    tui._log_file_transfer_event(
        {
            "transfer_id": "1234",
            "direction": "TX",
            "filename": "x.bin",
            "kind": "binary_send_start",
            "message_type": "DATA",
            "chunk_index": 7,
        }
    )

    assert len(tui.session.records) == 1
    marker, text = tui.session.records[0]
    assert marker == "FT1"
    assert '"kind":"binary_send_start"' in text
    assert '"chunk_index":7' in text
    assert "base64" not in text



def test_tui_syncs_panel_identity_from_transport():
    from serialterminal.tui import TerminalTui
    from serialterminal.transports.base import Transport

    class _Transport(Transport):
        @property
        def is_connected(self):
            return False

        @property
        def description(self):
            return "fake"

        @property
        def identity_label(self):
            return "LoRa-Chatter-1B44"

        def connect(self):
            return False

        def disconnect(self):
            pass

        def read(self, size=512):
            return b""

        def write(self, data):
            pass

    class _Panel:
        def __init__(self):
            self.identity = None

        def set_transport_identity(self, label):
            self.identity = label

    tui = object.__new__(TerminalTui)
    tui.panel = _Panel()
    tui._sync_panel_transport_identity(_Transport())

    assert tui.panel.identity == "LoRa-Chatter-1B44"



def test_tui_manual_input_preempts_active_file_transfer_instead_of_locking():
    from serialterminal.tui import TerminalTui

    submitted = []

    class _Session:
        def _submit_interactive_line(self, line):
            submitted.append(line)

    tui = object.__new__(TerminalTui)
    tui.input_text = "/config"
    tui.input_cursor = len(tui.input_text)
    tui.command_history = []
    tui.history_index = None
    tui.history_draft = ""
    tui.scrollback = type("_Scroll", (), {"follow": lambda self: None})()
    tui.session = _Session()
    tui.status = ""
    tui._abort_and_reconnect_same_target = lambda: True

    tui._submit_input()

    assert submitted == ["/config"]
    assert tui.input_text == ""
    assert "File transfer aborted" in tui.status


def test_tui_f6_uses_local_abort_path_not_process_exit():
    from serialterminal.tui import TerminalTui

    tui = object.__new__(TerminalTui)
    tui.status = ""
    tui._file_transfer_active = lambda: True
    tui._file_snapshot = lambda: {"state": "sending"}
    calls = []
    tui._abort_and_reconnect_same_target = lambda: calls.append("abort") or True

    tui._cancel_file()

    assert calls == ["abort"]
    assert tui.status == "File transfer aborted locally; reconnecting same target"


def test_tui_ctrl_c_keeps_default_quit_semantics():
    from serialterminal.tui import TerminalTui

    tui = object.__new__(TerminalTui)
    tui.running = True
    tui._handle_key(None, "\x03", 10)

    assert tui.running is False



def test_tui_f2_preempts_active_transfer_and_switches_device(monkeypatch):
    from serialterminal.tui import TerminalTui

    class _Transport:
        def __init__(self, key):
            self.device_key = key
            self.closed = False

        def close(self):
            self.closed = True

    class _Session:
        def __init__(self, transport):
            self.transport = transport

        def _current_transport(self):
            return self.transport

    class _Selector:
        def __init__(self, selected):
            self.selected = selected
            self.calls = 0

        def choose_transport_menu(self):
            self.calls += 1
            return self.selected

    class _Screen:
        def refresh(self):
            pass

    old = _Transport("old")
    new = _Transport("new")
    tui = object.__new__(TerminalTui)
    tui.session = _Session(old)
    tui.selector = _Selector(new)
    tui.status = ""
    tui._file_transfer_active = lambda: True
    events = []
    tui._abort_file_transfer_for_operator = lambda: events.append("abort") or True
    tui._replace_tui_session = lambda transport: events.append(
        ("replace", transport.device_key)
    )
    monkeypatch.setattr("serialterminal.tui.curses.endwin", lambda: None)

    tui._choose_device(_Screen())

    assert tui.selector.calls == 1
    assert events == ["abort", ("replace", "new")]
    assert tui.status == "File transfer aborted; switching device"


def test_tui_f2_cancel_keeps_active_transfer_running(monkeypatch):
    from serialterminal.tui import TerminalTui

    class _Transport:
        device_key = "old"

    class _Session:
        def _current_transport(self):
            return _Transport()

    class _Selector:
        def choose_transport_menu(self):
            return None

    class _Screen:
        def refresh(self):
            pass

    tui = object.__new__(TerminalTui)
    tui.session = _Session()
    tui.selector = _Selector()
    tui.status = ""
    tui._file_transfer_active = lambda: True
    tui._abort_file_transfer_for_operator = lambda: (_ for _ in ()).throw(
        AssertionError("cancelled chooser must not abort transfer")
    )
    monkeypatch.setattr("serialterminal.tui.curses.endwin", lambda: None)

    tui._choose_device(_Screen())

    assert tui.status == "Device selection cancelled; file transfer continues"
