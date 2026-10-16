import pytest

from serialterminal.tui import TerminalTui, TuiOutputBuffer


@pytest.mark.parametrize("control", [chr(n) for n in (*range(32), *range(127, 160))])
def test_tui_draw_never_passes_control_characters_to_curses(control):
    class Screen:
        calls = []

        def getmaxyx(self):
            return (24, 80)

        def addnstr(self, y, x, text, limit, attr):
            if "\x00" in text:
                raise ValueError("embedded null character")
            assert all(not (ord(c) < 32 or 127 <= ord(c) < 160) for c in text)
            self.calls.append((y, x, text, limit, attr))

    screen = Screen()
    TerminalTui._safe_addstr(screen, 3, 0, "before" + control + "after")
    assert len(screen.calls) == 1
    assert screen.calls[0][2].startswith("before")
    assert screen.calls[0][2].endswith("after")


def test_tui_wrap_accounts_for_visible_control_escapes():
    output = TuiOutputBuffer()
    output.write("A\x00\t\x1b[2J\x7f\x85Z\n")
    assert output.snapshot() == [r"A\x00\t\x1b[2J\x7f\x85Z"]
    rows = output.visual_rows(8)
    assert all(len(row.text) <= 8 for row in rows)
    assert "".join(row.text for row in rows) == output.snapshot()[0]


def test_tui_control_escape_preserves_partial_lines_and_unicode():
    output = TuiOutputBuffer()
    output.write("Привет \x00")
    line_id = output.latest_line_id()
    output.write(" мир\r\nnext\rthird\n")
    assert output.snapshot() == [r"Привет \x00 мир", "next", "third"]
    assert output.entries()[0].line_id == line_id
