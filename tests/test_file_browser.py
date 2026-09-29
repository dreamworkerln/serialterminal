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
