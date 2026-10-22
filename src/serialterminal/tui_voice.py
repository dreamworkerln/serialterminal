"""Панели записи и воспроизведения в той же области экрана, что и прогресс FT1."""
from __future__ import annotations

import curses

from .tui_file_transfer import FileTransferWindow, duration
from .voice_service import VoiceSnapshot


def draw_voice_panel(stdscr, draw, snapshot: VoiceSnapshot | None, *,
                     recording_attr: int, attr: int, border: int) -> bool:
    if snapshot is None or snapshot.state not in {"STARTING", "RECORDING", "FINALIZING", "ADMITTING"}:
        return False
    recording = snapshot.state == "RECORDING"
    elapsed = duration(snapshot.recording_seconds)
    if elapsed.startswith("00:"):
        elapsed = elapsed[3:]
    messages = {
        "STARTING": "Подготовка микрофона…",
        "RECORDING": f"● ЗАПИСЬ С МИКРОФОНА    {elapsed}",
        "FINALIZING": "Завершение записи: подготовка голосового файла…",
        "ADMITTING": "Подготовка голосового файла к передаче…",
    }
    hint = "F12 — остановить и отправить" if recording else "Ожидайте…"
    rows, columns = stdscr.getmaxyx()
    panel_attr = recording_attr if recording else attr
    if rows < 12 or columns < 60:
        # Даже при resize красный индикатор не заменяется общим предупреждением.
        draw(stdscr, 0, 0, messages[snapshot.state].ljust(max(1, columns - 1)), panel_attr)
        if rows > 1:
            draw(stdscr, 1, 0, hint.ljust(max(1, columns - 1)), panel_attr)
        return True
    FileTransferWindow.draw_box(
        stdscr, draw, 7, columns - 4,
        ["", messages[snapshot.state], "", hint, ""], "Голосовое сообщение",
        panel_attr, recording_attr if recording else border,
    )
    return True


def init_voice_colors() -> dict[str, int]:
    # Приглушённый сине-фиолетовый фон и общий Dracula accent окна FT1.
    foreground, background = (255, 60) if curses.COLORS >= 256 else (curses.COLOR_WHITE, curses.COLOR_BLUE)
    accent_text, accent = (236, 141) if curses.COLORS >= 256 else (curses.COLOR_BLACK, curses.COLOR_MAGENTA)
    curses.init_pair(11, foreground, background)
    curses.init_pair(12, accent_text, accent)
    return {"voice_playback": curses.color_pair(11),
            "voice_button": curses.color_pair(12) | curses.A_BOLD}


def playback_panel_visible(snapshot: VoiceSnapshot | None) -> bool:
    return bool(snapshot is not None and snapshot.playback_active and not snapshot.playback_cancelled)


def playback_button_rect(rows: int, columns: int) -> tuple[int, int, int] | None:
    if rows < 12 or columns < 60:
        return None
    height = min(10, rows - 5)
    top = max(0, (rows - 4 - height) // 2)
    return top + height - 3, (columns - len("[ Cancel ]")) // 2, len("[ Cancel ]")


def draw_playback_panel(stdscr, draw, snapshot: VoiceSnapshot | None, colors: dict[str, int]) -> bool:
    if not playback_panel_visible(snapshot):
        return False
    rows, columns = stdscr.getmaxyx()
    attr = colors.get("voice_playback", colors["panel"])
    selected = colors.get("voice_button", colors["header"])
    elapsed, total = snapshot.playback_seconds, snapshot.playback_total_seconds
    # До завершения backend не обещаем 100%: ALSA ещё может доигрывать буфер.
    percentage = min(99.0, max(0.0, elapsed / total * 100)) if total > 0 else 0.0
    elapsed_text = duration(elapsed).removeprefix("00:")
    total_text = duration(total).removeprefix("00:")
    timing = f"{elapsed_text} / {total_text}    {percentage:.0f}%"
    if rows < 12 or columns < 60:
        draw(stdscr, 0, 0, ("▶ АУДИО " + timing).ljust(max(1, columns - 1)), attr)
        if rows > 1:
            draw(stdscr, 1, 0, "Enter / Esc — остановить".ljust(max(1, columns - 1)), attr)
        return True
    height, width = min(10, rows - 5), columns - 4
    bar_width = max(4, width - 12)
    filled = int(bar_width * percentage / 100)
    content = [""] * (height - 2)
    content[0] = "▶ ВОСПРОИЗВЕДЕНИЕ"
    bar_row = 2 if height >= 9 else 1
    content[bar_row] = "█" * filled + "░" * (bar_width - filled)
    content[bar_row + 1] = timing
    content[-1] = "Enter или Esc — остановить"
    top, left, _, _ = FileTransferWindow.draw_box(
        stdscr, draw, height, width, content, "Голосовое сообщение", attr, attr)
    if filled:
        draw(stdscr, top + bar_row + 1, left + 2, "█" * filled, attr)
    y, x, _ = playback_button_rect(rows, columns)
    draw(stdscr, y, x, "[ Cancel ]", selected)
    return True
