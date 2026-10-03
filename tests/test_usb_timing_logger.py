from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import usb_timing_logger as logger


def test_build_log_paths_use_one_st_style_basename() -> None:
    paths = logger.build_log_paths(
        moment=datetime(2026, 10, 3, 7, 15, 1, 234567, tzinfo=timezone.utc),
        pid=4321,
        log_dir=Path("logs"),
    )

    assert paths == {
        "/dev/ttyACM0": Path(
            "logs/serialterminal-20261003-071501-234567-p4321.ttyACM0.timing.log"
        ),
        "/dev/ttyACM1": Path(
            "logs/serialterminal-20261003-071501-234567-p4321.ttyACM1.timing.log"
        ),
    }


def test_extract_complete_lines_preserves_partial_tail() -> None:
    buffer = bytearray(b"one\r\ntwo\npartial")

    assert logger._extract_complete_lines(buffer) == [b"one\r", b"two"]
    assert buffer == b"partial"


def test_write_payload_line_preserves_firmware_timing_text(monkeypatch) -> None:
    monkeypatch.setattr(logger, "_timestamp", lambda: "2026-10-03T07:15:01.234+03:00")
    output = StringIO()

    logger._write_payload_line(
        output,
        b"[TIMING] us=123456 event=USER_TX attempt=1\r",
    )

    assert output.getvalue() == (
        "2026-10-03T07:15:01.234+03:00 "
        "[TIMING] us=123456 event=USER_TX attempt=1\n"
    )
