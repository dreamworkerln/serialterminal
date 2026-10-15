import json

from serialterminal.timing import TimingTrace, timing_log_path


def test_timing_trace_buffers_partial_batch_and_uses_companion_name(tmp_path):
    raw = tmp_path / "serialterminal-test.log"
    trace = TimingTrace(raw)

    assert trace.path == timing_log_path(raw)
    assert trace.path == tmp_path / "serialterminal-test.fttiming.jsonl"
    trace.record("first", value=1)
    trace.record("second", value=2)
    assert trace.path.read_text() == ""

    trace.close()
    rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
    assert [row["event"] for row in rows] == ["first", "second"]
    assert [row["seq"] for row in rows] == [1, 2]
    assert all(isinstance(row["perf_ns"], int) for row in rows)
    assert all(isinstance(row["timestamp"], float) for row in rows)

    trace.record("ignored")
    trace.close()
    rows_after = [json.loads(line) for line in trace.path.read_text().splitlines()]
    assert rows_after == rows


def test_timing_batches_are_visible_before_close_and_final_tail_is_appended(tmp_path):
    trace = TimingTrace(tmp_path / "run.log", batch_size=3)
    try:
        for index in range(7):
            trace.record("probe", index=index)
        trace._queue.join()
        before = [json.loads(line) for line in trace.path.read_text().splitlines()]
        assert [row["index"] for row in before] == list(range(6))
        assert len(trace._events) == 1
        assert trace._queue.maxsize == 8
    finally:
        trace.close()
    after = [json.loads(line) for line in trace.path.read_text().splitlines()]
    assert [row["index"] for row in after] == list(range(7))
    assert [row["seq"] for row in after] == list(range(1, 8))
    assert not trace._worker.is_alive()


def test_timing_reopened_path_preserves_previous_session(tmp_path):
    raw = tmp_path / "run.log"
    first = TimingTrace(raw)
    first.record("first_session")
    first.close()
    second = TimingTrace(raw)
    second.record("second_session")
    second.close()
    rows = [json.loads(line) for line in second.path.read_text().splitlines()]
    assert [row["event"] for row in rows] == ["first_session", "second_session"]
    assert [row["seq"] for row in rows] == [1, 1]
    assert len({(row["segment_id"], row["seq"]) for row in rows}) == 2
    assert rows[0]["segment_id"] != rows[1]["segment_id"]


def test_timing_write_failure_is_reported_and_does_not_deadlock_close(tmp_path, monkeypatch):
    import pytest
    from serialterminal.application_log import ApplicationLog

    with ApplicationLog(tmp_path / "application.log") as log:
        trace = TimingTrace(tmp_path / "run.log", batch_size=1)
        real_file = trace._file

        class BrokenFile:
            def write(self, text):
                raise OSError("injected full disk")
            def close(self):
                real_file.close()

        trace._file = BrokenFile()
        trace.record("cannot_write")
        trace._queue.join()
        assert log.error_count == 1
        assert "injected full disk" in log.path.read_text()
        with pytest.raises(OSError, match="timing log incomplete"):
            trace.close()
        assert not trace._worker.is_alive()


def test_timing_caller_fields_cannot_override_event_identity_or_clocks(tmp_path):
    trace = TimingTrace(tmp_path / "run.log")
    trace.record("probe", segment_id="forged", seq=900, perf_ns=-1, timestamp=-1)
    trace.close()
    row = json.loads(trace.path.read_text())
    assert row["segment_id"] != "forged" and len(row["segment_id"]) == 32
    assert row["seq"] == 1 and row["perf_ns"] > 0 and row["timestamp"] > 0


def test_append_preserves_legacy_rows_without_assigning_them_a_segment(tmp_path):
    path = timing_log_path(tmp_path / "run.log")
    legacy = b'{"seq":1,"event":"legacy"}\n'
    path.write_bytes(legacy)
    trace = TimingTrace(tmp_path / "run.log")
    trace.record("current")
    trace.close()
    assert path.read_bytes().startswith(legacy)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert "segment_id" not in rows[0]
    assert len(rows[1]["segment_id"]) == 32


def test_append_after_truncated_utf8_fragment_keeps_new_record_parseable(tmp_path):
    path = timing_log_path(tmp_path / "run.log")
    fragment = b'{"seq":1,"event":"broken-\xd0'
    path.write_bytes(fragment)
    trace = TimingTrace(tmp_path / "run.log", batch_size=1)
    trace.record("after_crash")
    trace.close()
    raw = path.read_bytes()
    assert raw.startswith(fragment + b"\n")
    assert json.loads(raw.split(b"\n")[1])["event"] == "after_crash"


def test_concurrent_segments_append_complete_json_and_unique_keys(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    traces = [TimingTrace(tmp_path / "run.log", batch_size=3) for _ in range(2)]
    def record(trace):
        for number in range(30):
            trace.record("concurrent", number=number, padding="x" * 10000)
        trace.close()
    with ThreadPoolExecutor(2) as workers:
        list(workers.map(record, traces))
    rows = [json.loads(line) for line in traces[0].path.read_text().splitlines()]
    assert len(rows) == 60
    assert len({(row["segment_id"], row["seq"]) for row in rows}) == 60
    segments = {row["segment_id"] for row in rows}
    assert len(segments) == 2
    for segment in segments:
        assert [row["seq"] for row in rows if row["segment_id"] == segment] == list(range(1, 31))


def _timing_process(log_path, number):
    trace = TimingTrace(log_path, batch_size=2)
    for index in range(20):
        trace.record("process", number=number, index=index, padding="x" * 10000)
    trace.close()


def test_two_process_timing_writers_keep_segments_and_lines_distinct(tmp_path):
    import multiprocessing
    context = multiprocessing.get_context("fork")
    path = str(tmp_path / "run.log")
    processes = [context.Process(target=_timing_process, args=(path, number)) for number in range(2)]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(5)
            assert not process.is_alive() and process.exitcode == 0
        rows = [json.loads(line) for line in timing_log_path(path).read_text().splitlines()]
        assert len(rows) == 40
        assert len({(row["segment_id"], row["seq"]) for row in rows}) == 40
        assert len({row["segment_id"] for row in rows}) == 2
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(2)


def test_tui_session_and_profile_replacement_preserve_distinct_timing_segments(tmp_path):
    from types import SimpleNamespace
    from serialterminal.profiles import resolve_profile
    from serialterminal.tui_core import TerminalTui
    from test_agent import FakeTransport

    profile = resolve_profile('generic')
    selector = SimpleNamespace(profile=profile, choose_transport_menu=lambda: None)
    terminal = TerminalTui(transport=FakeTransport('first'), log_path=str(tmp_path / 'run.log'),
                           line_ending='\n', reconnect_delay=.01, selector=selector,
                           profile=profile, receive_dir=str(tmp_path / 'received'))
    try:
        terminal.session.record_timing('before_replacement')
        terminal._replace_tui_session(FakeTransport('second'), profile=resolve_profile('chatter'))
        terminal.session.record_timing('after_replacement')
    finally:
        terminal._close_file_transfer_manager()
        terminal.session.stop()
        terminal.session.close_logs()
    rows = [json.loads(line) for line in timing_log_path(tmp_path / 'run.log').read_text().splitlines()]
    markers = [row for row in rows if row['event'] in {'before_replacement', 'after_replacement'}]
    assert [row['event'] for row in markers] == ['before_replacement', 'after_replacement']
    assert markers[0]['segment_id'] != markers[1]['segment_id']
    assert len({(row['segment_id'], row['seq']) for row in rows}) == len(rows)
    assert len([row for row in rows if row['event'] == 'run_start']) == 2
    for segment in {row['segment_id'] for row in rows}:
        sequence = [row['seq'] for row in rows if row['segment_id'] == segment]
        assert sequence == list(range(1, len(sequence) + 1))


def test_timing_import_and_append_without_posix_capabilities(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    raw = tmp_path / 'portable.log'
    path = timing_log_path(raw)
    fragment = b'{"event":"broken-\xd0'
    path.write_bytes(fragment)
    script = """
import os
import sys
sys.path.insert(0, sys.argv[2])
sys.modules['fcntl'] = None
if hasattr(os, 'pread'):
    del os.pread
from serialterminal.timing import TimingTrace
trace = TimingTrace(sys.argv[1], batch_size=1)
trace.record('portable')
trace.close()
"""
    subprocess.run([sys.executable, '-c', script, str(raw), str(Path(__file__).resolve().parents[1] / 'src')],
                   check=True, capture_output=True, text=True, timeout=5)
    content = path.read_bytes()
    assert content.startswith(fragment + b'\n')
    row = json.loads(content.split(b'\n')[1])
    assert row['event'] == 'portable' and row['seq'] == 1 and len(row['segment_id']) == 32
