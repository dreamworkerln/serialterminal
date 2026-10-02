import json

from serialterminal.timing import TimingTrace, timing_log_path


def test_timing_trace_is_deferred_and_uses_companion_name(tmp_path):
    raw = tmp_path / "serialterminal-test.log"
    trace = TimingTrace(raw)

    assert trace.path == timing_log_path(raw)
    assert trace.path == tmp_path / "serialterminal-test.fttiming.jsonl"
    trace.record("first", value=1)
    trace.record("second", value=2)
    assert not trace.path.exists()

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
