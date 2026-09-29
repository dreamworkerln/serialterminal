from __future__ import annotations

import curses
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class FileBrowserItem:
    path: Path
    name: str
    is_dir: bool
    size: int | None
    mtime: float | None
    is_parent: bool = False


def format_size(size: int | None) -> str:
    if size is None:
        return ""
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{size} B"


def format_date(timestamp: float | None) -> str:
    if timestamp is None:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def shorten(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return "…"
    return text[: width - 1] + "…"


def scan_directory(directory: Path) -> list[FileBrowserItem]:
    result: list[FileBrowserItem] = []
    parent = directory.parent
    if parent != directory:
        result.append(
            FileBrowserItem(
                path=parent,
                name="..",
                is_dir=True,
                size=None,
                mtime=None,
                is_parent=True,
            )
        )

    try:
        entries = list(directory.iterdir())
    except OSError:
        return result

    scanned: list[FileBrowserItem] = []
    for path in entries:
        try:
            stat = path.stat()
            is_dir = path.is_dir()
        except OSError:
            continue
        scanned.append(
            FileBrowserItem(
                path=path,
                name=path.name,
                is_dir=is_dir,
                size=None if is_dir else stat.st_size,
                mtime=stat.st_mtime,
            )
        )

    scanned.sort(key=lambda item: (not item.is_dir, item.name.casefold()))
    result.extend(scanned)
    return result


class FileBrowser:
    """Single-pane curses filesystem picker used by the TUI file sender."""

    def __init__(self, stdscr, start_dir: Path) -> None:
        self.stdscr = stdscr
        self.directory = start_dir.expanduser().resolve()
        self.all_items: list[FileBrowserItem] = []
        self.items: list[FileBrowserItem] = []
        self.selected = 0
        self.top = 0
        self.query = ""
        self.search_mode = False
        self.status = ""
        self.reload()

    @property
    def current_item(self) -> FileBrowserItem | None:
        if not self.items:
            return None
        if not 0 <= self.selected < len(self.items):
            return None
        return self.items[self.selected]

    def reload(self) -> None:
        current_path = self.current_item.path if self.current_item else None
        self.all_items = scan_directory(self.directory)
        self.apply_filter()

        if current_path is not None:
            for index, item in enumerate(self.items):
                if item.path == current_path:
                    self.selected = index
                    break
        self.clamp_selection()
        self.status = f"{len(self.all_items)} item(s)"

    def apply_filter(self) -> None:
        query = self.query.casefold()
        if not query:
            self.items = list(self.all_items)
        else:
            self.items = [
                item
                for item in self.all_items
                if item.is_parent or query in item.name.casefold()
            ]
        self.clamp_selection()

    def clamp_selection(self) -> None:
        if not self.items:
            self.selected = 0
            self.top = 0
            return
        self.selected = max(0, min(self.selected, len(self.items) - 1))
        self.top = max(0, min(self.top, len(self.items) - 1))

    def move(self, delta: int) -> None:
        if not self.items:
            return
        self.selected = max(0, min(self.selected + delta, len(self.items) - 1))

    def ensure_visible(self, page_rows: int) -> None:
        if page_rows <= 0:
            return
        if self.selected < self.top:
            self.top = self.selected
        elif self.selected >= self.top + page_rows:
            self.top = self.selected - page_rows + 1
        max_top = max(0, len(self.items) - page_rows)
        self.top = max(0, min(self.top, max_top))

    def enter_directory(self, directory: Path) -> None:
        try:
            resolved = directory.expanduser().resolve()
            if not resolved.is_dir():
                self.status = f"Not a directory: {directory}"
                return
        except OSError as exc:
            self.status = f"Cannot open directory: {exc}"
            return
        self.directory = resolved
        self.selected = 0
        self.top = 0
        self.query = ""
        self.search_mode = False
        self.reload()

    def go_parent(self) -> None:
        parent = self.directory.parent
        if parent != self.directory:
            previous = self.directory
            self.enter_directory(parent)
            for index, item in enumerate(self.items):
                if item.path == previous:
                    self.selected = index
                    break

    def activate_current(self) -> Path | None:
        item = self.current_item
        if item is None:
            return None
        if item.is_dir:
            self.enter_directory(item.path)
            return None
        return item.path

    def clear_search(self) -> None:
        self.query = ""
        self.search_mode = False
        self.selected = 0
        self.top = 0
        self.apply_filter()
        self.status = "Search cleared"

    def handle_search_key(self, key) -> None:
        if key == "\x1b":
            self.clear_search()
            return
        if key in ("\n", "\r") or key == curses.KEY_ENTER:
            self.search_mode = False
            self.status = f"Filter: {self.query}" if self.query else "Search finished"
            return
        if key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            if self.query:
                self.query = self.query[:-1]
                self.selected = 0
                self.top = 0
                self.apply_filter()
            return
        if isinstance(key, str) and key.isprintable():
            self.query += key
            self.selected = 0
            self.top = 0
            self.apply_filter()

    @staticmethod
    def _wheel_direction(button_state: int) -> int:
        up_mask = (
            getattr(curses, "BUTTON4_PRESSED", 0)
            | getattr(curses, "BUTTON4_CLICKED", 0)
        )
        down_mask = (
            getattr(curses, "BUTTON5_PRESSED", 0)
            | getattr(curses, "BUTTON5_CLICKED", 0)
        )
        if up_mask and button_state & up_mask:
            return -1
        if down_mask and button_state & down_mask:
            return 1
        return 0

    def handle_key(self, key, page_rows: int) -> Path | None | bool:
        if self.search_mode:
            self.handle_search_key(key)
            return None

        if key == "\x1b":
            return False
        if key == curses.KEY_UP:
            self.move(-1)
        elif key == curses.KEY_DOWN:
            self.move(1)
        elif key == curses.KEY_PPAGE:
            self.move(-max(1, page_rows))
        elif key == curses.KEY_NPAGE:
            self.move(max(1, page_rows))
        elif key == curses.KEY_HOME:
            self.selected = 0
        elif key == curses.KEY_END:
            if self.items:
                self.selected = len(self.items) - 1
        elif key in (curses.KEY_LEFT, curses.KEY_BACKSPACE, "\x7f", "\b"):
            self.go_parent()
        elif key == curses.KEY_RIGHT:
            item = self.current_item
            if item is not None and item.is_dir:
                self.enter_directory(item.path)
        elif key == "/":
            self.search_mode = True
            self.status = ""
        elif key in ("r", "R"):
            self.reload()
        elif key in ("\n", "\r") or key == curses.KEY_ENTER:
            selected = self.activate_current()
            if selected is not None:
                return selected
        elif key == curses.KEY_MOUSE:
            try:
                _mouse_id, _x, _y, _z, button_state = curses.getmouse()
            except curses.error:
                return None
            direction = self._wheel_direction(button_state)
            if direction:
                self.move(direction * 3)
        return None

    @staticmethod
    def _safe_addstr(stdscr, y: int, x: int, text: str, attr: int = 0) -> None:
        height, width = stdscr.getmaxyx()
        if not (0 <= y < height and 0 <= x < width):
            return
        available = width - x
        if available <= 0:
            return
        try:
            stdscr.addnstr(
                y,
                x,
                text,
                max(1, available - 1),
                attr,
            )
        except curses.error:
            pass

    def draw(self) -> int:
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()

        if height < 10 or width < 50:
            self._safe_addstr(self.stdscr, 0, 0, "Terminal is too small.")
            self._safe_addstr(self.stdscr, 1, 0, "Resize to at least 50x10.")
            self.stdscr.refresh()
            return 1

        title = f" FILE BROWSER  {self.directory}"
        self._safe_addstr(
            self.stdscr,
            0,
            0,
            shorten(title, width - 1),
            curses.A_BOLD,
        )
        separator = "─" * max(1, width - 1)
        self._safe_addstr(self.stdscr, 1, 0, separator, curses.A_DIM)

        list_top = 3
        footer_rows = 4
        page_rows = max(1, height - list_top - footer_rows)

        show_date = width >= 92
        show_size = width >= 68
        show_type = width >= 55

        right_reserved = 4
        if show_type:
            right_reserved += 9
        if show_size:
            right_reserved += 12
        if show_date:
            right_reserved += 18
        name_width = max(12, width - right_reserved - 2)

        columns = f"  {'Name':<{name_width}}"
        if show_type:
            columns += "  Type "
        if show_size:
            columns += f" {'Size':>10}"
        if show_date:
            columns += "  Modified"
        self._safe_addstr(
            self.stdscr,
            2,
            0,
            shorten(columns, width - 1),
            curses.A_BOLD | curses.A_UNDERLINE,
        )

        self.ensure_visible(page_rows)
        if not self.items:
            message = "Directory is empty."
            if self.query:
                message = f'No matches for "{self.query}".'
            self._safe_addstr(self.stdscr, list_top, 2, message, curses.A_DIM)
        else:
            for row in range(page_rows):
                index = self.top + row
                if index >= len(self.items):
                    break
                item = self.items[index]
                marker = ">" if index == self.selected else " "
                display_name = item.name + ("/" if item.is_dir and not item.is_parent else "")
                line = f"{marker} {shorten(display_name, name_width):<{name_width}}"
                if show_type:
                    line += f"  {'<DIR>' if item.is_dir else item.path.suffix[1:].upper() or 'FILE':<5}"
                if show_size:
                    line += f" {format_size(item.size):>10}"
                if show_date:
                    line += f"  {format_date(item.mtime)}"
                attr = (
                    curses.A_REVERSE | curses.A_BOLD
                    if index == self.selected
                    else curses.A_NORMAL
                )
                self._safe_addstr(
                    self.stdscr,
                    list_top + row,
                    0,
                    shorten(line, width - 1),
                    attr,
                )

        sep_y = height - 4
        self._safe_addstr(self.stdscr, sep_y, 0, separator, curses.A_DIM)
        item = self.current_item
        info = str(item.path if item is not None else self.directory)
        self._safe_addstr(
            self.stdscr,
            sep_y + 1,
            0,
            shorten(info, width - 1),
            curses.A_DIM,
        )
        if self.search_mode:
            status = f"/ {self.query}█"
        else:
            status = self.status or (
                "↑↓ move  PgUp/PgDn page  Enter select/open  "
                "←/Backspace parent  / search  R reload  Esc cancel"
            )
        self._safe_addstr(
            self.stdscr,
            sep_y + 2,
            0,
            shorten(status, width - 1),
            curses.A_BOLD if self.search_mode else 0,
        )
        self._safe_addstr(
            self.stdscr,
            sep_y + 3,
            0,
            shorten("Home/End first/last   → enter directory", width - 1),
            curses.A_DIM,
        )
        self.stdscr.refresh()
        return page_rows

    def run(self) -> Path | None:
        previous_cursor: int | None = None
        try:
            try:
                previous_cursor = curses.curs_set(0)
            except curses.error:
                previous_cursor = None
            self.stdscr.keypad(True)
            while True:
                page_rows = self.draw()
                try:
                    key = self.stdscr.get_wch()
                except curses.error:
                    continue
                result = self.handle_key(key, page_rows)
                if result is False:
                    return None
                if isinstance(result, Path):
                    return result
        finally:
            if previous_cursor is not None:
                try:
                    curses.curs_set(previous_cursor)
                except curses.error:
                    pass


def browse_file(stdscr, start_dir: Path | None = None) -> Path | None:
    browser = FileBrowser(stdscr, start_dir or Path.cwd())
    return browser.run()
