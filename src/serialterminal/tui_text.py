"""Текст для TUI: управляющие символы и ширина в ячейках терминала."""
from __future__ import annotations

import unicodedata
from ctypes import CDLL, c_int, c_wchar


_wcwidth = CDLL(None).wcwidth
_wcwidth.argtypes = (c_wchar,)
_wcwidth.restype = c_int


def screen_safe_text(text: str) -> str:
    # curses отвергает NUL, а остальные C0/C1 могут двигать курсор или занимать
    # несколько ячеек. Видимые escapes нужны до wrap и на каждом пути отрисовки.
    return "".join(
        ascii(char)[1:-1] if ord(char) < 32 or 127 <= ord(char) < 160 else char
        for char in text
    )


def clusters(text: str) -> list[str]:
    result: list[str] = []
    for char in text:
        code = ord(char)
        extending = (unicodedata.category(char).startswith("M") or char == "\u200d"
                     or 0x1F3FB <= code <= 0x1F3FF)
        regional = 0x1F1E6 <= code <= 0x1F1FF
        if result and (extending or result[-1].endswith("\u200d") or
                       (regional and len(result[-1]) == 1 and 0x1F1E6 <= ord(result[-1]) <= 0x1F1FF)):
            result[-1] += char
        else:
            result.append(char)
    return result


def cell_width(text: str) -> int:
    if text.isascii() and text.isprintable():
        return len(text)
    # ncurses использует таблицы libc и размещает code points по отдельности.
    # Python Unicode tables/ZWJ folding могут дать другую ширину и сдвиг рамки.
    return sum(max(0, _wcwidth(char)) for char in text)


def fit_cells(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if text.isascii() and text.isprintable():
        return text[:width]
    parts: list[str] = []
    used = 0
    # Ширина libc аддитивна: каждый cluster измеряем один раз. Пересчёт
    # растущего prefix на каждом шаге превращает redraw в квадратичную работу.
    for cluster in clusters(text):
        size = cell_width(cluster)
        if used + size > width:
            break
        parts.append(cluster)
        used += size
    return "".join(parts)


def wrap_cells(text: str, width: int) -> list[str]:
    width = max(1, width)
    rows: list[str] = []
    parts: list[str] = []
    used = 0
    for cluster in clusters(text):
        size = cell_width(cluster)
        if size > width:
            cluster = "�"
            size = cell_width(cluster)
        if used + size > width:
            rows.append("".join(parts))
            parts = []
            used = 0
        parts.append(cluster)
        used += size
    if parts or not rows:
        rows.append("".join(parts))
    return rows


def middle_ellipsis(text: str, width: int) -> str:
    if cell_width(text) <= width:
        return text
    if width <= 1:
        return "…" if width == 1 else ""
    left = fit_cells(text, (width - 1) // 2)
    used = cell_width(left) + cell_width("…")
    right: list[str] = []
    for cluster in reversed(clusters(text)):
        size = cell_width(cluster)
        if used + size > width:
            break
        right.append(cluster)
        used += size
    return left + "…" + "".join(reversed(right))
