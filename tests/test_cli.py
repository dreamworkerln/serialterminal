from serialterminal.cli import DeviceCandidate, DeviceSelector


def _candidate(index: int) -> DeviceCandidate:
    return DeviceCandidate(
        kind="ble",
        key=f"device-{index}",
        label=f"Device {index}",
        detail=f"detail-{index}",
        identity=object(),
    )


def test_small_menu_uses_immediate_single_key_reader(monkeypatch):
    selector = DeviceSelector("auto")
    candidates = [_candidate(1), _candidate(2)]

    monkeypatch.setattr(
        selector,
        "_read_single_key_choice",
        lambda prompt_text, candidate_count, allow_cancel: "2",
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt_text: (_ for _ in ()).throw(
            AssertionError("line input should not be used for a small menu")
        ),
    )

    selected = selector.choose_from(
        candidates,
        auto_single=False,
        allow_cancel=True,
    )

    assert selected is candidates[1]


def test_small_menu_enter_can_cancel(monkeypatch):
    selector = DeviceSelector("auto")
    candidates = [_candidate(1), _candidate(2)]

    monkeypatch.setattr(
        selector,
        "_read_single_key_choice",
        lambda prompt_text, candidate_count, allow_cancel: "",
    )

    selected = selector.choose_from(
        candidates,
        auto_single=False,
        allow_cancel=True,
    )

    assert selected is None


def test_ten_item_menu_keeps_number_plus_enter_input(monkeypatch):
    selector = DeviceSelector("auto")
    candidates = [_candidate(index) for index in range(1, 11)]

    monkeypatch.setattr(
        selector,
        "_read_single_key_choice",
        lambda prompt_text, candidate_count, allow_cancel: (_ for _ in ()).throw(
            AssertionError("single-key reader must not be used for 10+ devices")
        ),
    )
    monkeypatch.setattr("builtins.input", lambda prompt_text: "10")

    selected = selector.choose_from(
        candidates,
        auto_single=False,
        allow_cancel=True,
    )

    assert selected is candidates[9]
