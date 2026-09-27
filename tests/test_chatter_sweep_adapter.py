import threading
import time

import pytest

import serialterminal.profiles.chatter.sweep as chatter_sweep
from serialterminal.profiles.chatter.sweep import (
    ChatterReliableUserSweepAdapter,
)
from serialterminal.sweep import (
    SweepCancelled,
    SweepPhaseContext,
    SweepPhaseTimeout,
    normalize_sweep_plan,
)


def _canonical_milli(text):
    whole, dot, fraction = text.partition(".")
    if not dot:
        return whole
    fraction = fraction.rstrip("0")
    if not fraction:
        return whole
    return f"{whole}.{fraction}"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("470.000", "470"),
        ("470.125", "470.125"),
        ("500.000", "500"),
        ("62.500", "62.5"),
        ("7.800", "7.8"),
    ],
)
def test_canonical_milli_matches_firmware_format(text, expected):
    assert _canonical_milli(text) == expected


class _RejectingConfigContext:
    def __init__(self, base):
        self.base = base

    def __getattr__(self, name):
        return getattr(self.base, name)

    def send_line(self, session, text):
        if text.startswith("/sf "):
            self.base.commands.append((session, text))
            self.base._line(
                session,
                "[SYS] CFG BUSY: radio/protocol transaction active; "
                "setting not changed",
            )
            return {
                "tx_id": len(self.base.commands),
                "state": "queued",
            }
        return self.base.send_line(session, text)


class _SilentSfContext:
    def __init__(self, base):
        self.base = base

    def __getattr__(self, name):
        return getattr(self.base, name)

    def send_line(self, session, text):
        if text.startswith("/sf "):
            self.base.commands.append((session, text))
            return {
                "tx_id": len(self.base.commands),
                "state": "queued",
            }
        return self.base.send_line(session, text)


class _SilentCommandContext:
    def __init__(self, base, command):
        self.base = base
        self.command = command

    def __getattr__(self, name):
        return getattr(self.base, name)

    def send_line(self, session, text):
        if text == self.command:
            self.base.commands.append((session, text))
            return {
                "tx_id": len(self.base.commands),
                "state": "queued",
            }
        return self.base.send_line(session, text)


class _SilentSessionCommandContext:
    def __init__(self, base, session, command):
        self.base = base
        self.session = session
        self.command = command

    def __getattr__(self, name):
        return getattr(self.base, name)

    def send_line(self, session, text):
        if session == self.session and text == self.command:
            self.base.commands.append((session, text))
            return {
                "tx_id": len(self.base.commands),
                "state": "queued",
            }
        return self.base.send_line(session, text)


class _SilentCancelContext:
    def __init__(self, base):
        self.base = base

    def __getattr__(self, name):
        return getattr(self.base, name)

    def send_line(self, session, text):
        if text == "/cancel all":
            self.base.commands.append((session, text))
            return {
                "tx_id": len(self.base.commands),
                "state": "queued",
            }
        return self.base.send_line(session, text)


class _QueueFullContext:
    def __init__(self, base):
        self.base = base

    def __getattr__(self, name):
        return getattr(self.base, name)

    def send_line(self, session, text):
        if not text.startswith("/"):
            self.base.commands.append((session, text))
            self.base._line(
                session,
                "DELIVERY QUEUE FULL source=1 bytes=32 "
                "waiting=0/4 in_flight=1",
            )
            self.base._line(
                session,
                "[SYS] SEND QUEUE FULL: message not accepted",
            )
            return {
                "tx_id": len(self.base.commands),
                "state": "queued",
            }
        return self.base.send_line(session, text)


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
        elif text == "/both":
            self._line(session, "[SYS] OUTPUT BOTH")
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
            state["freq"] = _canonical_milli(text.split()[1])
            self._line(
                session,
                f"[SYS] FREQ {state['freq']} MHz SAVED",
            )
        elif text.startswith("/bw "):
            state["bw"] = _canonical_milli(text.split()[1])
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
    for session in ("s1", "s2"):
        commands = [
            command
            for actual_session, command in context.commands
            if actual_session == session
        ]
        assert commands.index("/both") < commands.index("/help")


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


def test_control_rejection_fails_apply_without_waiting_for_deadline():
    base = _ScriptContext()
    context = _RejectingConfigContext(base)
    adapter = ChatterReliableUserSweepAdapter(
        context,
        ("s1", "s2"),
        _plan(),
    )

    with pytest.raises(RuntimeError, match="CFG BUSY"):
        adapter.apply_coordinate(
            _coordinate(),
            _phase("apply", seconds=0.2),
        )

    assert (("s1", "/config") not in base.commands)
    assert (("s2", "/power 2") not in base.commands)


def test_missing_control_response_hits_explicit_phase_deadline():
    base = _ScriptContext()
    context = _SilentSfContext(base)
    adapter = ChatterReliableUserSweepAdapter(
        context,
        ("s1", "s2"),
        _plan(),
    )

    with pytest.raises(SweepPhaseTimeout):
        adapter.apply_coordinate(
            _coordinate(),
            _phase("apply", seconds=0.05),
        )


def test_sample_queue_rejection_is_execution_failure_not_settlement_timeout():
    base = _ScriptContext()
    context = _QueueFullContext(base)
    adapter = ChatterReliableUserSweepAdapter(
        context,
        ("s1", "s2"),
        _plan(),
    )
    token = adapter.start_sample(
        _coordinate(),
        1,
        _phase("sample_start"),
    )

    with pytest.raises(RuntimeError, match="SEND QUEUE FULL"):
        adapter.wait_sample_settled(
            _coordinate(),
            1,
            token,
            _phase("sample_settlement", seconds=0.2),
        )


def test_settlement_binds_wait_ack_then_ignores_mismatched_ack():
    context = _ScriptContext()
    adapter = ChatterReliableUserSweepAdapter(
        context,
        ("s1", "s2"),
        _plan(),
    )
    token = adapter.start_sample(
        _coordinate(),
        1,
        _phase("sample_start"),
    )
    # Stop the fake from synthesizing its normal ACK after WAIT_ACK and
    # provide one unrelated ACK before the matching terminal ACK.
    context.pending_ack.clear()
    context._line(
        "s1",
        "DELIVERY ACK user=BEEF/9 attempts=1/5 "
        "elapsed=5ms queue=0",
    )
    context._line(
        "s1",
        "DELIVERY ACK user=A001/42 attempts=1/5 "
        "elapsed=10ms queue=0",
    )

    result = adapter.wait_sample_settled(
        _coordinate(),
        1,
        token,
        _phase("sample_settlement"),
    )

    assert result["user_id"] == "A001/42"


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



def test_cleanup_settles_reliable_work_on_both_sessions():
    context = _ScriptContext()
    adapter = ChatterReliableUserSweepAdapter(
        context,
        ("s1", "s2"),
        _plan(),
    )
    adapter.cleanup(_phase("cleanup"))

    assert ("s1", "/cancel all") in context.commands
    assert ("s2", "/cancel all") in context.commands


def test_cancel_uses_separate_short_settlement_budget(monkeypatch):
    base = _ScriptContext()
    context = _SilentCancelContext(base)
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
    # Не даём fake синтезировать нормальный ACK: проверяем именно потерянный
    # cancel/terminal response и отдельный cancel budget.
    base.pending_ack.clear()
    cancel = threading.Event()
    cancel.set()
    monkeypatch.setattr(
        chatter_sweep,
        "_CANCEL_SETTLEMENT_TIMEOUT_S",
        0.05,
    )

    started = time.monotonic()
    with pytest.raises(SweepPhaseTimeout) as caught:
        adapter.wait_sample_settled(
            coordinate,
            1,
            token,
            _phase(
                "sample_settlement",
                cancel_event=cancel,
                seconds=5.0,
            ),
        )
    elapsed = time.monotonic() - started

    assert caught.value.phase == "cancel_settlement"
    assert elapsed < 0.5
    assert ("s1", "/cancel all") in base.commands



@pytest.mark.parametrize(
    ("phase_name", "silent_command"),
    [
        ("prepare", "/cancel all"),
        ("cleanup", "/cancel all"),
    ],
)
def test_control_wait_phases_are_cooperatively_deadline_bounded(
    phase_name,
    silent_command,
):
    base = _ScriptContext()
    context = _SilentCommandContext(base, silent_command)
    adapter = ChatterReliableUserSweepAdapter(
        context,
        ("s1", "s2"),
        _plan(),
    )

    with pytest.raises(SweepPhaseTimeout) as caught:
        if phase_name == "prepare":
            adapter.prepare(_phase("prepare", seconds=0.05))
        else:
            adapter.cleanup(_phase("cleanup", seconds=0.05))
    assert caught.value.phase == phase_name


def test_verify_wait_is_cooperatively_deadline_bounded():
    base = _ScriptContext()
    context = _SilentCommandContext(base, "/config")
    adapter = ChatterReliableUserSweepAdapter(
        context,
        ("s1", "s2"),
        _plan(),
    )
    coordinate = _coordinate()
    adapter.apply_coordinate(coordinate, _phase("apply"))

    with pytest.raises(SweepPhaseTimeout) as caught:
        adapter.verify_coordinate(
            coordinate,
            _phase("verify", seconds=0.05),
        )
    assert caught.value.phase == "verify"


def test_sample_settlement_wait_is_cooperatively_deadline_bounded():
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
    context.pending_ack.clear()

    with pytest.raises(SweepPhaseTimeout) as caught:
        adapter.wait_sample_settled(
            coordinate,
            1,
            token,
            _phase("sample_settlement", seconds=0.05),
        )
    assert caught.value.phase == "sample_settlement"



def test_cleanup_attempts_exit_on_both_sessions_before_waiting():
    base = _ScriptContext()
    context = _SilentSessionCommandContext(
        base,
        "s1",
        "/cancel all",
    )
    adapter = ChatterReliableUserSweepAdapter(
        context,
        ("s1", "s2"),
        _plan(),
    )

    with pytest.raises(SweepPhaseTimeout):
        adapter.cleanup(_phase("cleanup", seconds=0.05))

    assert ("s1", "/cancel all") in base.commands
    assert ("s2", "/cancel all") in base.commands
