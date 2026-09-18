from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run-chatter-scenario"


def load_runner():
    return runpy.run_path(str(RUNNER), run_name="chatter_scenario_test")


def test_cancel_all_payload_is_bounded_and_exact_length():
    module = load_runner()
    payload = module["current_payload"]("20260918T101118Z")
    assert payload.startswith("CANCEL11_CURRENT_20260918T101118Z_")
    assert len(payload.encode("utf-8")) == 188
    assert len(payload.encode("utf-8")) <= 200


def test_cancel_all_trigger_and_cancel_regexes_match_firmware_lines():
    module = load_runner()
    queued = module["QUEUED_RE"].search(
        "DELIVERY QUEUED source=2 bytes=28 waiting=2/8 in_flight=1"
    )
    assert queued is not None
    assert queued.group("waiting") == "2"
    assert queued.group("in_flight") == "1"

    cancel = module["CANCEL_RE"].search(
        "DELIVERY CANCEL user=909C/7 attempts=1 status=unknown queue_removed=2"
    )
    assert cancel is not None
    assert cancel.group("identity") == "909C/7"
    assert cancel.group("attempts") == "1"
    assert cancel.group("removed") == "2"


def test_companion_path_matches_agent_log_contract(tmp_path):
    module = load_runner()
    path = module["companion_path"](tmp_path / "scenario.log")
    assert path == tmp_path / "scenario.console.log"


def test_parser_requires_explicit_four_device_keys_and_log():
    module = load_runner()
    args = module["parser"]().parse_args(
        [
            "cancel-all-current-plus-queue",
            "--sender-usb-key",
            "serial:a",
            "--sender-ble-key",
            "ble:a",
            "--peer-usb-key",
            "serial:b",
            "--peer-ble-key",
            "ble:b",
            "--log",
            "/tmp/test.log",
        ]
    )
    assert args.scenario == "cancel-all-current-plus-queue"
    assert args.sender_usb_key == "serial:a"
    assert args.sender_ble_key == "ble:a"
    assert args.peer_usb_key == "serial:b"
    assert args.peer_ble_key == "ble:b"


def test_discover_expected_devices_populates_cache_before_open():
    module = load_runner()

    class FakeAgent:
        def __init__(self):
            self.calls = []

        def request(self, op, **kwargs):
            self.calls.append((op, kwargs))
            assert op == "discover"
            if kwargs["scope"] == "serial":
                return {"devices": [{"key": "serial:a"}, {"key": "serial:b"}]}
            if kwargs["scope"] == "ble":
                return {"devices": [{"key": "ble:a"}, {"key": "ble:b"}]}
            raise AssertionError(kwargs["scope"])

    agent = FakeAgent()
    devices = module["discover_expected_devices"](
        agent,
        {"serial:a", "ble:a", "serial:b", "ble:b"},
        5.0,
    )
    assert {item["key"] for item in devices} == {
        "serial:a",
        "ble:a",
        "serial:b",
        "ble:b",
    }
    assert [call[1]["scope"] for call in agent.calls] == ["serial", "ble"]


def test_discover_expected_devices_reports_missing_key():
    module = load_runner()

    class FakeAgent:
        def request(self, op, **kwargs):
            if kwargs["scope"] == "serial":
                return {"devices": [{"key": "serial:a"}]}
            return {"devices": []}

    try:
        module["discover_expected_devices"](
            FakeAgent(),
            {"serial:a", "ble:a"},
            5.0,
        )
    except module["ScenarioError"] as exc:
        assert exc.code == "expected_device_missing"
        assert "ble:a" in str(exc)
    else:
        raise AssertionError("expected ScenarioError")


def test_discover_scope_labels_permission_boundary():
    module = load_runner()

    class FakeAgent:
        def request(self, op, **kwargs):
            raise module["ScenarioError"](
                "internal_error",
                "[Errno 1] Operation not permitted",
            )

    try:
        module["_discover_scope"](FakeAgent(), "ble", 5.0)
    except module["ScenarioError"] as exc:
        assert exc.code == "ble_discovery_permission"
        assert "Operation not permitted" in str(exc)
    else:
        raise AssertionError("expected ScenarioError")


def test_verify_echo_off_reads_help_without_toggling():
    module = load_runner()

    class FakeAgent:
        def __init__(self):
            self.calls = []

        def request(self, op, **kwargs):
            self.calls.append((op, kwargs))
            if op == "send_line":
                assert kwargs["text"] == "/help"
                return {"tx_id": 1, "state": "queued"}
            assert op == "observe"
            return {
                "events": [],
                "lines": [
                    {
                        "session": "s1",
                        "stream": "main",
                        "seq_first": 2,
                        "seq_last": 2,
                        "text": "[SYS]   current=CHAT echo=OFF",
                    }
                ],
                "cursors": {"s1": 2},
                "timed_out": False,
            }

    evidence = module["Evidence"](cursors={"s1": 0})
    agent = FakeAgent()
    module["verify_echo_off"](agent, evidence, "s1", "sender")
    assert [call[0] for call in agent.calls] == ["send_line", "observe"]


def test_verify_echo_off_blocks_echo_on():
    module = load_runner()

    class FakeAgent:
        def request(self, op, **kwargs):
            if op == "send_line":
                return {"tx_id": 1, "state": "queued"}
            return {
                "events": [],
                "lines": [
                    {
                        "session": "s1",
                        "stream": "main",
                        "seq_first": 2,
                        "seq_last": 2,
                        "text": "[SYS]   current=CHAT echo=ON",
                    }
                ],
                "cursors": {"s1": 2},
                "timed_out": False,
            }

    evidence = module["Evidence"](cursors={"s1": 0})
    try:
        module["verify_echo_off"](FakeAgent(), evidence, "s1", "sender")
    except module["ScenarioError"] as exc:
        assert exc.code == "echo_not_off"
    else:
        raise AssertionError("expected ScenarioError")
