import json

from serialterminal.runlog import RunLog


def _records(path):
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        _, tagged = line.split(" [", 1)
        tag, rendered = tagged.split("] ", 1)
        records.append((tag, json.loads(rendered)))
    return records


def test_run_log_keeps_raw_rx_only_without_line_or_partial_records(tmp_path):
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
                "text": "k=1 user=0 err=0\n",
                "data_b64": "Yg==",
            },
        )
        run_log.record(
            "STATE",
            {"session": "s2", "seq": 284, "state": "disconnected"},
        )

    records = _records(log_path)
    raw = [payload for tag, payload in records if tag == "RX chat"]
    assert [item["seq"] for item in raw] == [282, 283]
    assert [item["text"] for item in raw] == [
        "SESSION t=540s TX o",
        "k=1 user=0 err=0\n",
    ]
    assert not any(tag.startswith("RX LINE ") for tag, _ in records)
    assert not any(tag.startswith("RX PARTIAL ") for tag, _ in records)
