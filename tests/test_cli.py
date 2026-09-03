from pathlib import Path

import serialterminal.cli as cli_module
from serialterminal.cli import DeviceCandidate, DeviceSelector
from serialterminal.transports.base import Transport


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


def test_initial_discovery_scanner_hotkey_retries_after_scanner(monkeypatch):
    selector = DeviceSelector("auto")
    candidate = _candidate(1)
    discovery_results = iter([[], [candidate]])
    controls = iter([None, "scanner", None])
    scanner_runs = []

    monkeypatch.setattr(selector, "discover", lambda: next(discovery_results))
    monkeypatch.setattr(cli_module, "read_initial_control", lambda timeout: next(controls))
    monkeypatch.setattr(selector, "_run_initial_scanner", lambda: scanner_runs.append(True))

    selected = selector.choose_initial()

    assert selected is candidate
    assert scanner_runs == [True]


def test_agent_subcommand_dispatches_to_jsonl_frontend(monkeypatch, tmp_path):
    import serialterminal.agent as agent_module

    observed = {}

    def fake_run_agent(*, log_path=None, stdin=None, stdout=None):
        observed["log_path"] = log_path
        return 23

    monkeypatch.setattr(agent_module, "run_agent", fake_run_agent)
    log_path = tmp_path / "agent.log"

    assert cli_module.main(["agent", "--log", str(log_path)]) == 23
    assert observed == {"log_path": str(log_path)}


class _DummyTransport(Transport):
    @property
    def is_connected(self):
        return False

    @property
    def description(self):
        return "dummy"

    def connect(self):
        return False

    def disconnect(self):
        pass

    def read(self, size=512):
        return b""

    def write(self, data):
        pass


class _DummySelector:
    def choose_transport_menu(self):
        return None


def test_human_session_uses_unique_default_log_path(monkeypatch, tmp_path):
    captured = {}
    generated = tmp_path / "logs" / "serialterminal-run.log"

    class FakeTerminalSession:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self):
            captured["ran"] = True

    monkeypatch.setattr(cli_module, "TerminalSession", FakeTerminalSession)
    monkeypatch.setattr(cli_module, "default_log_path", lambda: Path(generated))

    result = cli_module._run_session(
        _DummyTransport(),
        log_path=None,
        eol="lf",
        selector=_DummySelector(),
    )

    assert result == 0
    assert captured["log_path"] == str(generated)
    assert captured["ran"] is True
