"""Окно ROOT-передачи и адресное подтверждение отмены без владения FT1."""
from __future__ import annotations

import curses
import math

from .tui_text import cell_width, fit_cells, middle_ellipsis, screen_safe_text, wrap_cells

TERMINAL_STATES = {"completed", "failed", "cancelled"}
ACTIVE_STATES = {"preparing", "compressing", "sending", "receiving", "resuming",
                 "waiting_result", "repair_requested", "repairing", "verifying",
                 "decompressing", "recovering_local_node"}


def live_transfer(snapshot: dict | None) -> bool:
    return bool(snapshot is not None and snapshot["state"] in ACTIVE_STATES
                and snapshot.get("presentation", {}).get("active", False))


def attempt_key(snapshot: dict | None):
    if snapshot is None:
        return None
    return snapshot["transfer_id"], snapshot.get("presentation", {}).get("attempt")


def transfer_phase(snapshot: dict) -> str:
    controller = snapshot.get("controller")
    if live_transfer(snapshot) and controller is not None and not controller.get("ready", False):
        return "recovering_local_node"
    return str(snapshot["state"])


def file_transfer_status_line(event: dict) -> str | None:
    outcomes = {"transfer_completed": "успешно", "transfer_failed": "ошибка",
                "transfer_cancelled": "отменена пользователем",
                "transfer_started": "начата", "cancel_requested": "запрошена отмена",
                "local_recovery_started": "восстановление связи с нодой",
                "local_recovery_resumed": "передача возобновлена",
                "resume_state_restored": "возобновлена из сохранённого состояния",
                "resume_state_reset": "сохранённые данные отсутствуют; приём с начала",
                "resume_started": "продолжение передачи",
                "transfer_suspended": "приостановлена; состояние сохранено"}
    outcome = outcomes.get(event.get("kind"))
    if event.get("kind") == "transfer_cancelled" and event.get("cancelled_by_peer"):
        outcome = "отменена отправителем" if event.get("direction") == "RX" else "отменена получателем"
    if event.get("kind") == "state":
        outcome = {"compressing": "подготовка файла", "sending": "передача данных",
                   "receiving": "приём данных", "resuming": "возобновление передачи",
                   "repair_requested": "запрошено восстановление пропусков",
                   "repairing": "восстановление пропусков", "verifying": "проверка файла",
                   "decompressing": "распаковка файла",
                   "waiting_result": "ожидание проверки получателем"}.get(event.get("state"))
    if outcome is None:
        return None
    filename = screen_safe_text(str(event.get("filename", "?")))
    text = f"[FT1] {event.get('direction', '?')} «{filename}»: {outcome}"
    if event["kind"] == "transfer_failed":
        failure = event.get("progress", {}).get("failure", {})
        reason = ": ".join(str(failure[k]) for k in ("code", "message") if failure.get(k))
        if reason:
            text += " — " + screen_safe_text(reason)
    return text


def init_file_transfer_colors() -> dict[str, int]:
    # Ближайшие ANSI-256 цвета Dracula без изменения palette самого terminal.
    # На 8/16-color terminal сохраняем контраст обычными curses colors.
    if curses.COLORS >= 256:
        foreground, background, purple = 255, 236, 141
    else:
        foreground, background, purple = curses.COLOR_WHITE, curses.COLOR_BLACK, curses.COLOR_MAGENTA
    curses.init_pair(8, foreground, background)
    curses.init_pair(9, purple, background)
    curses.init_pair(10, background, purple)
    return {"file": curses.color_pair(8), "file_border": curses.color_pair(9),
            "file_selected": curses.color_pair(10) | curses.A_BOLD}


def duration(seconds: float | None) -> str:
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        return "—"
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


class FileTransferWindow:
    def __init__(self) -> None:
        self.transfer_id: str | None = None
        self.mode = "closed"
        self._state: str | None = None
        self._attempt = None
        self._resume = 0
        self._activity = 0
        self._controller_key = None
        self._recovery_activity: int | None = None
        self.cancel_requested_id: str | None = None
        self.confirmation_id: str | None = None
        self.confirmation_attempt = None
        self.confirm_yes = True
        self._dismissed_confirmation = False

    @property
    def visible(self) -> bool:
        return self.mode == "foreground"

    @visible.setter
    def visible(self, value: bool) -> None:
        self.mode = "foreground" if value else "closed"

    def cancelling(self, snapshot: dict | None) -> bool:
        return bool(snapshot is not None and live_transfer(snapshot) and (
            snapshot.get("presentation", {}).get("cancel_requested", False)
            or self.cancel_requested_id == snapshot["transfer_id"]))

    def _confirmation_active(self, snapshot: dict | None) -> bool:
        return (self.confirmation_id is not None and live_transfer(snapshot)
                and attempt_key(snapshot) == self.confirmation_attempt
                and not self.cancelling(snapshot))

    def sync(self, snapshot: dict | None) -> None:
        if snapshot is None:
            self.transfer_id = None
            self.visible = False
            self._state = None
            self.cancel_requested_id = None
            self._attempt = None
            self._controller_key = None
            self._recovery_activity = None
            return
        state = snapshot["state"]
        if (self.confirmation_id is not None
                and (state == "cancelled" or self.cancelling(snapshot))):
            # Удалённая отмена снимает вопрос, но оставляет остановленный
            # progress. Уже нажатый Enter не должен попасть в command input.
            self.confirmation_id = None
            self.confirmation_attempt = None
            self._dismissed_confirmation = True
        presentation = snapshot.get("presentation", {})
        new_attempt = attempt_key(snapshot) != self._attempt
        resume = presentation.get("resume", 0)
        activity = presentation.get("activity", 0)
        if new_attempt:
            self._attempt = attempt_key(snapshot)
            self.transfer_id = snapshot["transfer_id"]
            self.cancel_requested_id = None
            self.mode = "foreground" if live_transfer(snapshot) else "closed"
            self._controller_key = None
            self._recovery_activity = None
            # Уже открытый dialog остаётся привязан к прежней операции.
            # Его запоздалый Enter не должен попасть в input или новый ROOT.
        elif live_transfer(snapshot) and resume != self._resume and not self.cancelling(snapshot):
            self.mode = "foreground"
        controller = snapshot.get("controller")
        if controller is not None and live_transfer(snapshot):
            key = controller.get("epoch"), controller.get("connection_generation")
            if ((self._controller_key is not None and key != self._controller_key)
                    or not controller.get("ready", False)) and self._recovery_activity is None:
                self._recovery_activity = self._activity
            # READY без принятого FT1 обмена не является возобновлением файла.
            if (controller.get("ready", False) and self._recovery_activity is not None
                    and activity > self._recovery_activity and not self.cancelling(snapshot)):
                self.mode = "foreground"
                self._recovery_activity = None
            self._controller_key = key
        if state == "completed" or (not live_transfer(snapshot) and state not in {"failed", "cancelled"}):
            self.mode = "closed"
        self._resume = resume
        self._activity = activity
        self._state = state

    def mark_cancel_requested(self, transfer_id: str) -> None:
        if transfer_id == self.transfer_id:
            # Принятый cancel ещё не завершает worker и не освобождает ownership.
            self.cancel_requested_id = transfer_id
            # Оператор уже подтвердил отмену: cleanup продолжается в manager,
            # но progress не требует второго Esc и не возвращается после drain.
            self.mode = "closed"

    def request_cancel(self, snapshot: dict | None) -> None:
        self.sync(snapshot)
        if live_transfer(snapshot) and not self.cancelling(snapshot):
            self.confirmation_id = snapshot["transfer_id"]
            self.confirmation_attempt = attempt_key(snapshot)
            self.confirm_yes = True
            self.visible = True

    def handle_key(self, key, snapshot: dict | None) -> tuple[bool, str | None]:
        self.sync(snapshot)
        if self._dismissed_confirmation:
            self._dismissed_confirmation = False
            if key in ("\n", "\r", curses.KEY_ENTER):
                return True, None
        if self.confirmation_id is not None:
            if key in ("\x1b", "\n", "\r", curses.KEY_ENTER):
                target = self.confirmation_id
                active = self._confirmation_active(snapshot)
                self.confirmation_id = None
                return True, target if key != "\x1b" and self.confirm_yes and active else None
            if key == curses.KEY_LEFT:
                self.confirm_yes = False
            elif key == curses.KEY_RIGHT:
                self.confirm_yes = True
            return True, None
        if key == curses.KEY_F7:
            if live_transfer(snapshot) and not self.cancelling(snapshot):
                self.mode = "background" if self.visible else "foreground"
            return True, None
        if key in ("\x1b", curses.KEY_F6) and snapshot is not None:
            if key == "\x1b" and self.cancelling(snapshot):
                self.visible = False
            elif snapshot["state"] in TERMINAL_STATES:
                if key == "\x1b":
                    self.visible = False
            elif live_transfer(snapshot):
                self.request_cancel(snapshot)
            return True, None
        return False, None

    @staticmethod
    def draw_box(stdscr, draw, height: int, width: int, content: list[str], title: str, attr: int, border: int):
        rows, columns = stdscr.getmaxyx()
        width = min(width, columns - 2)
        height = min(height, rows - 5)
        top = max(0, (rows - 4 - height) // 2)
        left = max(0, (columns - width) // 2)
        inner = max(1, width - 4)
        draw(stdscr, top, left, "┌" + fit_cells(" " + title + " ", width - 2).ljust(width - 2, "─") + "┐", border | curses.A_BOLD)
        for index in range(height - 2):
            text = fit_cells(content[index] if index < len(content) else "", inner)
            padding = " " * max(0, width - 3 - cell_width(text))
            draw(stdscr, top + index + 1, left, "│ " + text + padding + "│", attr)
            if border != attr:
                draw(stdscr, top + index + 1, left, "│", border)
                draw(stdscr, top + index + 1, left + width - 1, "│", border)
        draw(stdscr, top + height - 1, left, "└" + "─" * (width - 2) + "┘", border)
        return top, left, height, width

    def draw(self, stdscr, draw, snapshot: dict | None, *, bar, state_label, rate: float, attr: int, selected: int, border: int | None = None) -> None:
        self.sync(snapshot)
        rows, columns = stdscr.getmaxyx()
        if (not self.visible and self.confirmation_id is None) or rows < 12 or columns < 60:
            return
        border = attr if border is None else border
        width = columns - 4
        if snapshot is None:
            # Исчезнувшая session не оставляет невидимый modal-перехват клавиш.
            self.draw_box(stdscr, draw, 5, width,
                      ["Операция завершилась или изменилась.", "", "Enter/Esc: закрыть диалог"],
                      "Подтверждение", attr, border)
            return
        inner = width - 4
        available = max(1, rows - 7)
        name = screen_safe_text(str(snapshot.get("filename", "?")))
        name_rows = wrap_cells(name, inner)
        state = transfer_phase(snapshot)
        if state == "recovering_local_node" or self.cancelling(snapshot):
            rate = 0.0
        percentage = max(0.0, min(100.0, float(snapshot.get("percentage", 0))))
        processed = max(0, int(snapshot.get("bytes_completed", 0)))
        total = max(0, int(snapshot.get("wire_bytes", 0)))
        elapsed = snapshot.get("elapsed")
        # ETA относится только к текущему DATA stream. Repair/RESULT могут
        # продолжаться после его конца, поэтому общего обещания времени нет.
        eta = ((total - processed) * 8 / (rate * 1000)
               if rate > 0 and total > processed and state in {"sending", "receiving", "resuming"} else None)
        progress = f"[{bar(percentage, max(4, inner - 10))}] {percentage:.1f}%"
        detail = (f"Подготовка {processed}/{snapshot.get('original_bytes', 0)} source bytes"
                  if state == "compressing" else f"{processed}/{total} wire bytes | {rate:.1f} kbit/s")
        timing = f"Прошло {duration(elapsed)} | ETA DATA {duration(eta)}"
        repair = snapshot.get("repair")
        stage = f"{snapshot.get('direction', '?')} | {state_label(state)} | ROOT {snapshot['transfer_id']}"
        if state == "cancelled" and snapshot.get("presentation", {}).get("cancelled_by_peer"):
            origin = "отменено отправителем" if snapshot.get("direction") == "RX" else "отменено получателем"
            stage = f"{snapshot.get('direction', '?')} | {origin} | ROOT {snapshot['transfer_id']}"
        if self.cancelling(snapshot):
            stage = f"{snapshot.get('direction', '?')} | отмена: ожидание завершения | ROOT {snapshot['transfer_id']}"
        if repair and state not in TERMINAL_STATES:
            stage += f" | repair depth={repair.get('depth', '?')} missing={repair.get('missing_total', '?')}"
        footer = "F7: в фон | Esc: запрос отмены"
        if state in TERMINAL_STATES:
            footer = "Esc: закрыть окно"
        elif self.cancelling(snapshot):
            footer = "Отмена запрошена; ожидаем результат"
        extra = []
        if snapshot.get("failure"):
            failure = snapshot["failure"]
            extra = [screen_safe_text(f"{failure.get('code', '')}: {failure.get('message', '')}")]
        elif snapshot.get("final_path"):
            extra = [screen_safe_text(str(snapshot["final_path"]))]
        name_budget = max(1, min(3, available - 5 - len(extra)))
        shown_name = name_rows[:name_budget]
        if len(name_rows) > name_budget:
            shown_name[-1] = middle_ellipsis("".join(name_rows[name_budget - 1:]), inner)
        content = [*shown_name, stage, progress, detail, timing, *extra, footer]
        if len(content) > available:
            # Маленький terminal сохраняет имя, реальное состояние и controls;
            # остальные показатели возвращаются при увеличении окна.
            content = [middle_ellipsis(name, inner), state_label(state), progress, footer][:available]
        if self.visible:
            self.draw_box(stdscr, draw, len(content) + 2, width, content, "Передача файла", attr, border)
        if self.confirmation_id is not None:
            active = self._confirmation_active(snapshot)
            content = ["Отменить передачу файла?", "", "←/→: выбор | Enter: подтвердить | Esc: продолжить"]
            if not active:
                content = ["Операция завершилась или изменилась.", "", "Enter/Esc: закрыть диалог"]
            top, left, _, _ = self.draw_box(stdscr, draw, 5, width, content, "Подтверждение", attr, border)
            if active:
                no, yes = "[ Нет ]", "[ Да ]"
                x = left + max(2, (width - 20) // 2)
                draw(stdscr, top + 2, x, no, attr if self.confirm_yes else selected)
                draw(stdscr, top + 2, x + 12, yes, selected if self.confirm_yes else attr)
