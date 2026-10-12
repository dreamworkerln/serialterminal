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
    assert [json.loads(line)["event"] for line in second.path.read_text().splitlines()] == ["first_session", "second_session"]


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
