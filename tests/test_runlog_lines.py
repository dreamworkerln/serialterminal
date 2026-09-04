import json

from serialterminal.runlog import RunLog


def _records(path):
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        _, tagged = line.split(" [", 1)
        tag, rendered = tagged.split("] ", 1)
        records.append((tag, json.loads(rendered)))
    return records


def test_run_log_keeps_raw_rx_and_adds_complete_line_view(tmp_path):
    log_path = tmp_path / "agent.log"
    with RunLog(log_path) as run_log:
        run_log.record(
            "RX chat",
            {
                "session": "s2",
                "stream": "chat",
                "seq": 282,
                "text": "SESSION t=540s TX o",
                "data_b64": "YQ==",
            },
        )
        run_log.record(
            "RX chat",
            {
                "session": "s2",
                "stream": "chat",
                "seq": 283,
                "text": "k=1 user=0 err=0\r",
                "data_b64": "Yg==",
            },
        )
        run_log.record(
            "RX chat",
            {
                "session": "s2",
                "stream": "chat",
                "seq": 284,
                "text": "\n",
                "data_b64": "Cg==",
            },
        )

    records = _records(log_path)
    raw = [payload for tag, payload in records if tag == "RX chat"]
    lines = [payload for tag, payload in records if tag == "RX LINE chat"]

    assert [item["seq"] for item in raw] == [282, 283, 284]
    assert [item["text"] for item in raw] == [
        "SESSION t=540s TX o",
        "k=1 user=0 err=0\r",
        "\n",
    ]
    assert lines == [
        {
            "session": "s2",
            "stream": "chat",
            "text": "SESSION t=540s TX ok=1 user=0 err=0",
            "seq_first": 282,
            "seq_last": 284,
        }
    ]


def test_run_log_keeps_streams_separate_and_preserves_empty_lines(tmp_path):
    log_path = tmp_path / "agent.log"
    with RunLog(log_path) as run_log:
        run_log.record(
            "RX chat",
            {
                "session": "s1",
                "stream": "chat",
                "seq": 10,
                "text": "chat",
                "data_b64": "YQ==",
            },
        )
        run_log.record(
            "RX telemetry",
            {
                "session": "s1",
                "stream": "telemetry",
                "seq": 11,
                "text": "telemetry\n",
                "data_b64": "Yg==",
            },
        )
        run_log.record(
            "RX chat",
            {
                "session": "s1",
                "stream": "chat",
                "seq": 12,
                "text": "\n\n",
                "data_b64": "Cg==",
            },
        )

    records = _records(log_path)
    line_records = [
        (tag, payload) for tag, payload in records if tag.startswith("RX LINE ")
    ]
    assert line_records == [
        (
            "RX LINE telemetry",
            {
                "session": "s1",
                "stream": "telemetry",
                "text": "telemetry",
                "seq_first": 11,
                "seq_last": 11,
            },
        ),
        (
            "RX LINE chat",
            {
                "session": "s1",
                "stream": "chat",
                "text": "chat",
                "seq_first": 10,
                "seq_last": 12,
            },
        ),
        (
            "RX LINE chat",
            {
                "session": "s1",
                "stream": "chat",
                "text": "",
                "seq_first": 12,
                "seq_last": 12,
            },
        ),
    ]


def test_run_log_uses_incremental_text_span_and_flushes_partial_on_disconnect(
    tmp_path,
):
    log_path = tmp_path / "agent.log"
    with RunLog(log_path) as run_log:
        run_log.record(
            "RX chat",
            {
                "session": "s1",
                "stream": "chat",
                "seq": 20,
                "text": "",
                "data_b64": "4g==",
            },
        )
        run_log.record(
            "RX chat",
            {
                "session": "s1",
                "stream": "chat",
                "seq": 21,
                "text": "€\npartial",
                "data_b64": "grwKcGFydGlhbA==",
            },
        )
        run_log.record(
            "STATE",
            {
                "session": "s1",
                "seq": 22,
                "state": "disconnected",
            },
        )

    records = _records(log_path)
    assert (
        "RX LINE chat",
        {
            "session": "s1",
            "stream": "chat",
            "text": "€",
            "seq_first": 20,
            "seq_last": 21,
        },
    ) in records
    partial_index = records.index(
        (
            "RX PARTIAL chat",
            {
                "session": "s1",
                "stream": "chat",
                "text": "partial",
                "seq_first": 21,
                "seq_last": 21,
            },
        )
    )
    state_index = next(
        index
        for index, (tag, payload) in enumerate(records)
        if tag == "STATE" and payload.get("state") == "disconnected"
    )
    assert partial_index < state_index
