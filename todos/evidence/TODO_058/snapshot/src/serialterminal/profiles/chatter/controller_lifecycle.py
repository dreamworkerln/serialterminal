"""Грамматика локальных lifecycle-строк контроллера Chatter."""
from __future__ import annotations

import re
from typing import Literal


_RESET_LINE_RE = re.compile(
    r"(?:ESP-ROM:[^\r\n]+|"
    r"rst:0x[0-9a-fA-F]+(?: \([A-Z0-9_]+\))?,"
    r"boot:0x[0-9a-fA-F]+(?: \([A-Z0-9_]+\))?|"
    r"\[SYS\] RADIO FATAL [^\r\n]+)"
)


def parse_controller_lifecycle_line(line: str) -> Literal["reset", "ready"] | None:
    # USER/echo имеют собственный префикс. Не снимаем его или leading whitespace:
    # цитата boot-маркера не доказывает смену владельца outstanding операций.
    value = line.rstrip("\r\n")
    if value == "[SYS] CHATTER READY":
        return "ready"
    if _RESET_LINE_RE.fullmatch(value) is not None:
        return "reset"
    return None
