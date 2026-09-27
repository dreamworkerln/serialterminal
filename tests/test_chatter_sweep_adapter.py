import threading
import time

import pytest

from serialterminal.profiles.chatter.sweep import (
    ChatterReliableUserSweepAdapter,
)
from serialterminal.sweep import (
    SweepCancelled,
    SweepPhaseContext,
    normalize_sweep_plan,
)


class _ScriptContext:
    def __init__(self):
        self.commands = []
        self.lines = {"s1": [], "s2": []}
        self.next_seq = {"s1": 1, "s2": 1}
        self.radio = {
            "s1": {
                "power": 2,
                "freq": "470.000",
                "bw": "125.000",
                "sf": 12,
            },
            "s2": {
                "power": 2,
                "freq": "470.000",
                "bw": "125.000",
                "sf": 12,
            },
        }
        self.pending_ack = {}
        self.observe_calls = 0

    def profile_name(self, session):
        return "chatter"

    def status(self, session):
        return {
            "session": session,
            "state": "connected",
            "latest_seq": self.next_seq[session] - 1,
        }

    def _line(self, session, text):
        seq = self.next_seq[session]
        self.next_seq[session] += 1
        self.lines[session].append(
            {
                "session": session,
                "stream": "main",
                "seq_first": seq,
                "seq_last": seq,
                "text": text,
            }
        )

    def send_bytes(self, session, data):
        raise AssertionError("chatter reliable-user adapter does not use send_bytes")

    def send_line(self, session, text):
        self.commands.append((session, text))
        state = self.radio[session]
        if text == "/cancel all":
            self._line(
                session,
                "[SYS] DELIVERY CANCEL: nothing pending",
            )
        elif text == "/diag off":
            self._line(session, "[SYS] DIAG OFF")
        elif text == "/heartbeat off":
            self._line(session, "[SYS] HEARTBEAT OFF")
        elif text == "/echo-loop stop":
            self._line(
                session,
                "[SYS] ECHO LOOP already stopped",
            )
        elif text == "/help":
            self._line(
                session,
                "[SYS] OUTPUT current=CHAT echo=OFF",
            )
        elif text == "/id":
            identity = (
                "LoRa-Chatter-A001"
                if session == "s1"
                else "LoRa-Chatter-A002"
            )
            self._line(
                session,
                f"[SYS] CHATTER NODE {identity}",
            )
        elif text.startswith("/power "):
            state["power"] = int(text.split()[1])
            self._line(
                session,
                f"[SYS] POWER {state['power']} dBm SAVED",
            )
        elif text.startswith("/freq "):
            state["freq"] = text.split()[1].rstrip("0").rstrip(".")
            self._line(
                session,
                f"[SYS] FREQ {state['freq']} MHz SAVED",
            )
        elif text.startswith("/bw "):
            state["bw"] = text.split()[1].rstrip("0").rstrip(".")
            self._line(
                session,
                f"[SYS] BW {state['bw']} kHz SAVED",
            )
        elif text.startswith("/sf "):
            state["sf"] = int(text.split()[1])
            self._line(
                session,
                f"[SYS] SF {state['sf']} SAVED",
            )
        elif text == "/config":
            self._line(
                session,
                "[SYS] CFG RADIO "
                f"power={state['power']} dBm "
                f"freq={state['freq']} MHz "
                f"sf={state['sf']} "
                f"bw={state['bw']} kHz",
            )
        elif not text.startswith("/"):
            user = "A001/42"
            self._line(
                session,
                "DELIVERY WAIT_ACK "
                f"user={user} attempt=1/5 timeout=100ms queue=0",
            )
            self.pending_ack[session] = user
        return {
            "tx_id": len(self.commands),
            "state": "queued",
        }

    def observe(
        self,
        cursors,
        *,
        timeout_ms,
        include_events=False,
    ):
        self.observe_calls += 1
        result_lines = []
        result_cursors = dict(cursors)
        returned_wait = set()
        for session, cursor in cursors.items():
            available = [
                line
                for line in self.lines[session]
                if line["seq_last"] > cursor
            ]
            result_lines.extend(available)
            if available:
                result_cursors[session] = available[-1]["seq_last"]
                if any(
                    line["text"].startswith("DELIVERY WAIT_ACK")
                    for line in available
                ):
                    returned_wait.add(session)

        # ACK появляется только после того, как WAIT_ACK уже был отдан отдельным
        # observe response. Так тест доказывает, что WAIT_ACK не settlement.
        for session in returned_wait:
            user = self.pending_ack.pop(session, None)
            if user is not None:
                self._line(
                    session,
                    "DELIVERY ACK "
                    f"user={user} attempts=1/5 elapsed=10ms queue=0",
                )

        return {
            "lines": result_lines,
            "cursors": result_cursors,
            "timed_out": not bool(result_lines),
        }


def _phase(name, cancel_event=None, seconds=2.0):
    return SweepPhaseContext(
        name=name,
        deadline=time.monotonic() + seconds,
        cancel_event=cancel_event or threading.Event(),
    )


def _plan():
    return normalize_sweep_plan(
        {
            "constants": {
                "frequency_hz": 470_000_000,
                "power_dbm": 2,
                "bandwidth_hz": 500_000,
                "sf": 7,
                "payload_bytes": 32,
                "direction": "s1>s2",
            },
            "axes": [],
            "repetitions": 3,
        }
    )


def _coordinate():
    return {
        "frequency_hz": 470_000_000,
        "power_dbm": 2,
        "bandwidth_hz": 500_000,
        "sf": 7,
        "payload_bytes": 32,
        "direction": "s1>s2",
    }


def test_prepare_settles_reliable_flow_before_other_mutations():
    context = _ScriptContext()
    adapter = ChatterReliableUserSweepAdapter(
        context,
        ("s1", "s2"),
        _plan(),
    )
    adapter.prepare(_phase("prepare"))

    first_for_s1 = next(
        command
        for session, command in context.commands
        if session == "s1"
    )
    first_for_s2 = next(
        command
        for session, command in context.commands
        if session == "s2"
    )
    assert first_for_s1 == "/cancel all"
    assert first_for_s2 == "/cancel all"
    assert adapter.identities == {
        "s1": "LoRa-Chatter-A001",
        "s2": "LoRa-Chatter-A002",
    }


def test_apply_then_verify_issues_config_only_after_saved_transitions():
    context = _ScriptContext()
    adapter = ChatterReliableUserSweepAdapter(
        context,
        ("s1", "s2"),
        _plan(),
    )
    coordinate = _coordinate()

    adapter.apply_coordinate(
        coordinate,
        _phase("apply"),
    )
    adapter.verify_coordinate(
        coordinate,
        _phase("verify"),
    )

    for session in ("s1", "s2"):
        commands = [
            command
            for actual_session, command in context.commands
            if actual_session == session
        ]
        assert commands == [
            "/power 2",
            "/freq 470.000",
            "/bw 500.000",
            "/sf 7",
            "/config",
        ]


def test_wait_ack_is_not_sample_settlement_but_matching_ack_is():
    context = _ScriptContext()
    adapter = ChatterReliableUserSweepAdapter(
        context,
        ("s1", "s2"),
        _plan(),
    )
    coordinate = _coordinate()
    token = adapter.start_sample(
        coordinate,
        1,
        _phase("sample_start"),
    )
    before = context.observe_calls
    result = adapter.wait_sample_settled(
        coordinate,
        1,
        token,
        _phase("sample_settlement"),
    )

    assert context.observe_calls >= before + 2
    assert result["tx_id"] == token["tx_id"]
    assert result["user_id"] == "A001/42"
    payload = next(
        command
        for session, command in context.commands
        if session == "s1" and not command.startswith("/")
    )
    assert len(payload.encode("ascii")) == 32


def test_cancel_during_settlement_sends_bounded_cancel_and_terminates():
    context = _ScriptContext()
    adapter = ChatterReliableUserSweepAdapter(
        context,
        ("s1", "s2"),
        _plan(),
    )
    coordinate = _coordinate()
    token = adapter.start_sample(
        coordinate,
        1,
        _phase("sample_start"),
    )
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(SweepCancelled):
        adapter.wait_sample_settled(
            coordinate,
            1,
            token,
            _phase(
                "sample_settlement",
                cancel_event=cancel,
            ),
        )

    assert ("s1", "/cancel all") in context.commands
