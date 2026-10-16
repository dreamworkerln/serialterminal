from serialterminal.file_browser import FileBrowser, scan_directory


def test_file_browser_lists_parent_directories_then_files(tmp_path):
    (tmp_path / "z-dir").mkdir()
    (tmp_path / "a-dir").mkdir()
    (tmp_path / "b.txt").write_text("bb", encoding="utf-8")
    (tmp_path / "a.bin").write_bytes(b"a")

    items = scan_directory(tmp_path)
    names = [item.name for item in items]

    assert names[:3] == ["..", "a-dir", "z-dir"]
    assert names[3:] == ["a.bin", "b.txt"]
    assert items[1].is_dir is True
    assert items[3].is_dir is False


def test_file_browser_enter_directory_and_select_any_file(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    payload = sub / "payload.weird"
    payload.write_bytes(b"data")

    browser = FileBrowser(None, tmp_path)
    browser.selected = next(
        index for index, item in enumerate(browser.items) if item.path == sub
    )
    assert browser.activate_current() is None
    assert browser.directory == sub.resolve()

    browser.selected = next(
        index for index, item in enumerate(browser.items) if item.path == payload
    )
    assert browser.activate_current() == payload.resolve()


def test_file_browser_parent_navigation_reselects_previous_directory(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    browser = FileBrowser(None, sub)

    browser.go_parent()

    assert browser.directory == tmp_path.resolve()
    assert browser.current_item is not None
    assert browser.current_item.path == sub.resolve()


def test_file_browser_search_filters_files_and_keeps_parent(tmp_path):
    (tmp_path / "alpha.txt").write_text("a", encoding="utf-8")
    (tmp_path / "beta.bin").write_bytes(b"b")
    browser = FileBrowser(None, tmp_path)

    browser.query = "beta"
    browser.apply_filter()

    assert [item.name for item in browser.items] == ["..", "beta.bin"]


def test_file_browser_escape_cancels_and_enter_selects_file(tmp_path):
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"x")
    browser = FileBrowser(None, tmp_path)
    browser.selected = next(
        index for index, item in enumerate(browser.items) if item.path == payload
    )

    assert browser.handle_key("\x1b", 10) is False
    assert browser.handle_key("\n", 10) == payload.resolve()


def test_arrow_navigation_redraw_has_linear_unicode_width_work(tmp_path, monkeypatch):
    import curses
    from serialterminal import file_browser, tui_text
    from serialterminal.file_browser import FileBrowserItem

    class Screen:
        rows, columns = 60, 240

        def erase(self):
            self.lines = {}
            self.calls = []
            self.refreshes = 0

        def getmaxyx(self):
            return self.rows, self.columns

        def addnstr(self, y, x, text, limit, attr):
            self.lines[y] = text[:limit]
            self.calls.append((y, x, text, limit, attr))

        def refresh(self):
            self.refreshes += 1

    items = [FileBrowserItem(tmp_path / f"файл_{index}.bin", f"файл_{index}.bin",
                             False, 1024, 0) for index in range(100)]
    scans = []
    def scan(directory):
        scans.append(directory)
        return items
    monkeypatch.setattr(file_browser, "scan_directory", scan)
    monkeypatch.setattr(FileBrowser, "_colors", staticmethod(lambda: dict.fromkeys(
        ("normal", "header", "directory", "columns", "status", "search", "selected", "dim"), 0)))
    screen = Screen()
    browser = FileBrowser(screen, tmp_path)
    calls = 0
    original = tui_text._wcwidth
    def counted(char):
        nonlocal calls
        calls += 1
        return original(char)
    monkeypatch.setattr(tui_text, "_wcwidth", counted)
    for key, expected in [(curses.KEY_DOWN, 1), (curses.KEY_UP, 0)]:
        assert browser.handle_key(key, 53) is None
        assert browser.selected == expected
        calls = 0
        assert browser.draw() == 53
        assert f">{expected + 1:>4}" in screen.lines[3 + expected]
        item_rows = [call for call in screen.calls if 3 <= call[0] < 56]
        assert len(item_rows) == 53
        assert all(len(call[2]) == screen.columns - 1 for call in item_rows)
        assert screen.refreshes == 1
        # Бюджет зависит от размера кадра, а не от тайминга конкретного CI host.
        # Повторный подсчёт каждого растущего prefix превышает его на порядок.
        assert calls <= screen.rows * screen.columns * 8
    assert scans == [tmp_path.resolve()]
