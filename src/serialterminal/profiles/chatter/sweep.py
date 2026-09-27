from __future__ import annotations

from collections.abc import Mapping
import math
import re
import time
from typing import Any

from ...sweep import (
    SweepAdapterContext,
    SweepCancelled,
    SweepError,
    SweepPhaseContext,
    SweepPhaseTimeout,
    SweepPlan,
)


_IDENTITY_RE = re.compile(
    r"\[SYS\] CHATTER NODE (?P<identity>LoRa-Chatter-[0-9A-Fa-f]+)"
)
_ECHO_STATE_RE = re.compile(r"current=[A-Z]+ echo=(?P<state>ON|OFF)")
_FREQ_SAVED_RE = re.compile(
    r"^\[SYS\] FREQ (?P<freq>\d+(?:\.\d+)?) MHz SAVED$"
)
_BW_SAVED_RE = re.compile(
    r"^\[SYS\] BW (?P<bw>\d+(?:\.\d+)?) kHz SAVED$"
)
_CFG_RADIO_RE = re.compile(
    r"^\[SYS\] CFG RADIO power=(?P<power>-?\d+) dBm "
    r"freq=(?P<freq>\d+(?:\.\d+)?) MHz sf=(?P<sf>\d+) "
    r"bw=(?P<bw>\d+(?:\.\d+)?) kHz$"
)
_WAIT_ACK_RE = re.compile(
    r"DELIVERY WAIT_ACK user=(?P<user>[0-9A-Fa-f]+/\d+)"
)
_ACK_RE = re.compile(
    r"DELIVERY ACK user=(?P<user>[0-9A-Fa-f]+/\d+)"
)
_FAILED_RE = re.compile(
    r"DELIVERY FAILED user=(?P<user>[0-9A-Fa-f]+/\d+)"
)
_CANCEL_RE = re.compile(
    r"DELIVERY CANCEL user=(?P<user>[0-9A-Fa-f]+/\d+)"
)

_POWER_VALUES = frozenset([*range(2, 18), 20])
_BANDWIDTH_VALUES_HZ = frozenset(
    {
        7800,
        10400,
        15600,
        20800,
        31250,
        41700,
        62500,
        125000,
        250000,
        500000,
    }
)
_REQUIRED_FIELDS = frozenset(
    {
        "frequency_hz",
        "power_dbm",
        "bandwidth_hz",
        "sf",
        "payload_bytes",
        "direction",
    }
)
_MAX_ATTEMPTS = 5
_FRAME_HEADER_BYTES = 12
_ACK_FRAME_BYTES = 14
_CONTROL_FAILURE_MARKERS = (" REJECTED", " NOT SAVED", " BUSY")
_CANCEL_SETTLEMENT_TIMEOUT_S = 5.0


def _is_control_failure(line: str) -> bool:
    return line.startswith("[SYS]") and any(
        marker in line
        for marker in _CONTROL_FAILURE_MARKERS
    )


def _scaled_decimal(text: str, scale: int) -> int:
    whole, dot, fraction = text.partition(".")
    if not whole.isdigit() or (dot and not fraction.isdigit()):
        raise ValueError(text)
    digits = (fraction + "000")[:3]
    return int(whole) * scale + int(digits) * (scale // 1000)


def _format_milli(value: int, unit_scale: int) -> str:
    whole = value // unit_scale
    remainder = value % unit_scale
    milli = (remainder * 1000) // unit_scale
    return f"{whole}.{milli:03d}"


def _lora_toa_s(
    sf: int,
    bandwidth_hz: int,
    frame_bytes: int,
) -> float:
    symbol_s = (2**sf) / float(bandwidth_hz)
    low_data_rate_opt = 1 if symbol_s >= 0.016 else 0
    numerator = 8 * frame_bytes - 4 * sf + 28 + 16
    denominator = 4 * (sf - 2 * low_data_rate_opt)
    payload_symbols = 8 + max(
        math.ceil(numerator / denominator) * 5,
        0,
    )
    return (8 + 4.25 + payload_symbols) * symbol_s


def _possible_values(
    plan: SweepPlan,
    name: str,
) -> tuple[Any, ...]:
    if name in plan.constants:
        return (plan.constants[name],)
    for axis in plan.axes:
        if axis.name == name:
            return axis.values
    raise SweepError(
        "invalid_sweep_plan",
        f"chatter adapter requires coordinate field: {name}",
    )


def _require_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SweepError(
            "invalid_sweep_plan",
            f"{name} values must be integers",
        )
    return value


def _validate_chatter_plan(
    context: SweepAdapterContext,
    sessions: tuple[str, ...],
    plan: SweepPlan,
) -> None:
    if len(sessions) != 2 or sessions[0] == sessions[1]:
        raise SweepError(
            "invalid_sweep_sessions",
            "chatter.reliable_user requires exactly two distinct sessions",
        )

    for session in sessions:
        profile = context.profile_name(session)
        if profile != "chatter":
            raise SweepError(
                "incompatible_sweep_session",
                f"session {session} must use profile chatter",
                {"session": session, "profile": profile},
            )
        status = context.status(session)
        if status.get("state") != "connected":
            raise SweepError(
                "session_not_connected",
                f"session is not connected: {session}",
                {
                    "session": session,
                    "state": status.get("state"),
                },
            )

    names = set(plan.constants) | {
        axis.name
        for axis in plan.axes
    }
    missing = sorted(_REQUIRED_FIELDS - names)
    unknown = sorted(names - _REQUIRED_FIELDS)
    if missing:
        raise SweepError(
            "invalid_sweep_plan",
            "missing chatter coordinate field(s): "
            + ", ".join(missing),
        )
    if unknown:
        raise SweepError(
            "invalid_sweep_plan",
            "unknown chatter coordinate field(s): "
            + ", ".join(unknown),
        )
    if plan.options:
        raise SweepError(
            "invalid_sweep_plan",
            "chatter.reliable_user currently accepts no plan.options",
        )

    for value in _possible_values(plan, "frequency_hz"):
        frequency = _require_int("frequency_hz", value)
        if (
            frequency % 1000 != 0
            or not 470_000_000 <= frequency <= 510_000_000
        ):
            raise SweepError(
                "invalid_sweep_plan",
                "frequency_hz must be a 1 kHz step inside "
                "470000000..510000000",
            )
    for value in _possible_values(plan, "power_dbm"):
        if _require_int("power_dbm", value) not in _POWER_VALUES:
            raise SweepError(
                "invalid_sweep_plan",
                "power_dbm must be 2..17 or 20",
            )
    for value in _possible_values(plan, "bandwidth_hz"):
        if (
            _require_int("bandwidth_hz", value)
            not in _BANDWIDTH_VALUES_HZ
        ):
            raise SweepError(
                "invalid_sweep_plan",
                "bandwidth_hz is not supported by Chatter firmware",
            )
    for value in _possible_values(plan, "sf"):
        sf = _require_int("sf", value)
        if not 7 <= sf <= 12:
            raise SweepError(
                "invalid_sweep_plan",
                "sf must be 7..12",
            )
    for value in _possible_values(plan, "payload_bytes"):
        size = _require_int("payload_bytes", value)
        if not 1 <= size <= 200:
            raise SweepError(
                "invalid_sweep_plan",
                "payload_bytes must be 1..200",
            )

    allowed_directions = {
        f"{sessions[0]}>{sessions[1]}",
        f"{sessions[1]}>{sessions[0]}",
    }
    for value in _possible_values(plan, "direction"):
        if value not in allowed_directions:
            raise SweepError(
                "invalid_sweep_plan",
                "direction values must name one of the two "
                "participating session directions",
            )


class ChatterReliableUserSweepAdapter:
    name = "chatter.reliable_user"

    def __init__(
        self,
        context: SweepAdapterContext,
        sessions: tuple[str, ...],
        plan: SweepPlan,
    ):
        _validate_chatter_plan(context, sessions, plan)
        self.context = context
        self.sessions = sessions
        self.plan = plan
        self.cursors = {
            session: int(context.status(session)["latest_seq"])
            for session in sessions
        }
        self.identities: dict[str, str] = {}
        self._verified_radio: tuple[int, int, int, int] | None = None
        self._pending_radio: tuple[int, int, int, int] | None = None

    def phase_timeout_s(
        self,
        phase: str,
        coordinate: Mapping[str, Any] | None,
    ) -> float:
        if phase == "prepare":
            return 90.0
        if phase == "apply":
            return 45.0
        if phase == "verify":
            return 20.0
        if phase == "sample_start":
            return 10.0
        if phase == "cleanup":
            return 30.0
        if phase == "sample_settlement":
            if coordinate is None:
                return 60.0
            sf = int(coordinate["sf"])
            bw = int(coordinate["bandwidth_hz"])
            payload = int(coordinate["payload_bytes"])
            user_toa = _lora_toa_s(
                sf,
                bw,
                _FRAME_HEADER_BYTES + payload,
            )
            ack_toa = _lora_toa_s(
                sf,
                bw,
                _ACK_FRAME_BYTES,
            )
            # Firmware допускает до пяти attempts и airtime-derived retry
            # windows. Bound зависит от фактического PHY, чтобы быстрый BW500
            # не наследовал многоминутный timeout медленного legal PHY.
            return min(
                3600.0,
                max(
                    15.0,
                    10.0
                    + 25.0 * user_toa
                    + _MAX_ATTEMPTS * ack_toa,
                ),
            )
        raise RuntimeError(
            f"unknown chatter sweep phase: {phase}"
        )

    def _observe_lines(
        self,
        phase: SweepPhaseContext,
        *,
        respect_cancel: bool = True,
        deadline: float | None = None,
        timeout_phase: str | None = None,
    ) -> list[dict[str, Any]]:
        if respect_cancel:
            phase.raise_if_cancelled()
        effective_deadline = (
            phase.deadline
            if deadline is None
            else min(phase.deadline, deadline)
        )
        remaining = effective_deadline - time.monotonic()
        if remaining <= 0:
            raise SweepPhaseTimeout(timeout_phase or phase.name)
        timeout_ms = max(
            1,
            min(250, int(math.ceil(remaining * 1000.0))),
        )
        result = self.context.observe(
            dict(self.cursors),
            timeout_ms=timeout_ms,
            include_events=False,
        )
        for session, cursor in (
            result.get("cursors") or {}
        ).items():
            if (
                session in self.cursors
                and isinstance(cursor, int)
                and not isinstance(cursor, bool)
            ):
                self.cursors[session] = cursor
        return [
            line
            for line in result.get("lines", [])
            if isinstance(line, dict)
        ]

    def _wait_line(
        self,
        session: str,
        predicate,
        phase: SweepPhaseContext,
        *,
        respect_cancel: bool = True,
    ) -> str:
        while True:
            for line in self._observe_lines(
                phase,
                respect_cancel=respect_cancel,
            ):
                if line.get("session") != session:
                    continue
                text = line.get("text")
                if not isinstance(text, str):
                    continue
                if _is_control_failure(text):
                    raise RuntimeError(
                        f"{session}: Chatter control failed: {text}"
                    )
                if predicate(text):
                    return text

    def _send_wait(
        self,
        session: str,
        text: str,
        predicate,
        phase: SweepPhaseContext,
    ) -> str:
        phase.raise_if_cancelled()
        self.context.send_line(session, text)
        return self._wait_line(
            session,
            predicate,
            phase,
        )

    def prepare(self, phase: SweepPhaseContext) -> None:
        identities: dict[str, str] = {}
        for session in self.sessions:
            # Session-level TX fence уже завершил все pre-lease host writes.
            # Firmware sweep transition теперь атомарно гасит normal reliable
            # backlog и фоновые RF-механизмы до первого measured USER.
            self._send_wait(
                session,
                "/sweep on",
                lambda line:
                    line.startswith("[SYS] SWEEP ON source=")
                    or line.startswith("[SYS] SWEEP already ON source="),
                phase,
            )
            # Reliable settlement is reported as TELEMETRY. BLE 0004 is an
            # optional profile stream and Serial/SPP have only the main
            # stream, so force BOTH rather than assuming telemetry is visible.
            self._send_wait(
                session,
                "/both",
                lambda line: line == "[SYS] OUTPUT BOTH",
                phase,
            )
            help_line = self._send_wait(
                session,
                "/help",
                lambda line:
                    _ECHO_STATE_RE.search(line) is not None,
                phase,
            )
            echo_match = _ECHO_STATE_RE.search(help_line)
            assert echo_match is not None
            if echo_match.group("state") == "ON":
                self.context.send_line(session, "/echo")
                help_line = self._send_wait(
                    session,
                    "/help",
                    lambda line:
                        _ECHO_STATE_RE.search(line) is not None,
                    phase,
                )
                echo_match = _ECHO_STATE_RE.search(help_line)
                if (
                    echo_match is None
                    or echo_match.group("state") != "OFF"
                ):
                    raise RuntimeError(
                        f"session {session} echo request mode "
                        "did not become OFF"
                    )
            identity_line = self._send_wait(
                session,
                "/id",
                lambda line:
                    _IDENTITY_RE.search(line) is not None,
                phase,
            )
            match = _IDENTITY_RE.search(identity_line)
            assert match is not None
            identities[session] = match.group("identity")

        if len(set(identities.values())) != len(identities):
            raise RuntimeError(
                "participating sessions resolve to the same "
                "Chatter identity"
            )
        self.identities = identities

    @staticmethod
    def _radio_tuple(
        coordinate: Mapping[str, Any],
    ) -> tuple[int, int, int, int]:
        return (
            int(coordinate["power_dbm"]),
            int(coordinate["frequency_hz"]),
            int(coordinate["bandwidth_hz"]),
            int(coordinate["sf"]),
        )

    def apply_coordinate(
        self,
        coordinate: Mapping[str, Any],
        phase: SweepPhaseContext,
    ) -> None:
        target = self._radio_tuple(coordinate)
        if target == self._verified_radio:
            self._pending_radio = target
            return

        power, frequency_hz, bandwidth_hz, sf = target
        frequency_text = _format_milli(
            frequency_hz,
            1_000_000,
        )
        bandwidth_text = _format_milli(
            bandwidth_hz,
            1_000,
        )
        for session in self.sessions:
            self._send_wait(
                session,
                f"/power {power}",
                lambda line, power=power:
                    line
                    == f"[SYS] POWER {power} dBm SAVED",
                phase,
            )
            self._send_wait(
                session,
                f"/freq {frequency_text}",
                lambda line,
                frequency_hz=frequency_hz:
                    (
                        (match := _FREQ_SAVED_RE.match(line))
                        is not None
                        and _scaled_decimal(
                            match.group("freq"),
                            1_000_000,
                        )
                        == frequency_hz
                    ),
                phase,
            )
            self._send_wait(
                session,
                f"/bw {bandwidth_text}",
                lambda line,
                bandwidth_hz=bandwidth_hz:
                    (
                        (match := _BW_SAVED_RE.match(line))
                        is not None
                        and _scaled_decimal(
                            match.group("bw"),
                            1_000,
                        )
                        == bandwidth_hz
                    ),
                phase,
            )
            self._send_wait(
                session,
                f"/sf {sf}",
                lambda line, sf=sf:
                    line == f"[SYS] SF {sf} SAVED",
                phase,
            )
        self._pending_radio = target

    def verify_coordinate(
        self,
        coordinate: Mapping[str, Any],
        phase: SweepPhaseContext,
    ) -> None:
        target = self._radio_tuple(coordinate)
        if target == self._verified_radio:
            return
        if self._pending_radio != target:
            raise RuntimeError(
                "coordinate verification called without matching apply"
            )

        for session in self.sessions:
            line = self._send_wait(
                session,
                "/config",
                lambda value:
                    _CFG_RADIO_RE.match(value) is not None,
                phase,
            )
            match = _CFG_RADIO_RE.match(line)
            assert match is not None
            actual = (
                int(match.group("power")),
                _scaled_decimal(
                    match.group("freq"),
                    1_000_000,
                ),
                _scaled_decimal(
                    match.group("bw"),
                    1_000,
                ),
                int(match.group("sf")),
            )
            if actual != target:
                raise RuntimeError(
                    f"session {session} radio config mismatch: "
                    f"requested={target!r} actual={actual!r}"
                )
        self._verified_radio = target

    def _payload(
        self,
        coordinate: Mapping[str, Any],
        repetition: int,
    ) -> str:
        size = int(coordinate["payload_bytes"])
        direction = str(coordinate["direction"])
        source = direction.split(">", 1)[0]
        direction_mark = (
            "A"
            if source == self.sessions[0]
            else "B"
        )
        marker = (
            f"S{coordinate['sf']}{direction_mark}"
            f"P{size}R{repetition}-"
        )
        if size == 1:
            return direction_mark
        if len(marker) >= size:
            return marker[:size]
        return marker + ("X" * (size - len(marker)))

    def start_sample(
        self,
        coordinate: Mapping[str, Any],
        repetition: int,
        phase: SweepPhaseContext,
    ) -> Any:
        phase.raise_if_cancelled()
        source, target = str(
            coordinate["direction"]
        ).split(">", 1)
        payload = self._payload(
            coordinate,
            repetition,
        )
        response = self.context.send_line(
            source,
            payload,
        )
        tx_id = response.get("tx_id")
        if (
            isinstance(tx_id, bool)
            or not isinstance(tx_id, int)
        ):
            raise RuntimeError(
                "send_line returned no tx_id"
            )
        return {
            "source": source,
            "target": target,
            "tx_id": tx_id,
        }

    def wait_sample_settled(
        self,
        coordinate: Mapping[str, Any],
        repetition: int,
        token: Any,
        phase: SweepPhaseContext,
    ) -> Mapping[str, Any] | None:
        if not isinstance(token, dict):
            raise RuntimeError(
                "invalid chatter sample token"
            )

        source = str(token["source"])
        user_id: str | None = None
        cancel_sent = False
        cancel_deadline: float | None = None

        while True:
            if (
                phase.cancel_requested
                and not cancel_sent
            ):
                self.context.send_line(
                    source,
                    "/cancel all",
                )
                cancel_sent = True
                cancel_deadline = (
                    time.monotonic()
                    + _CANCEL_SETTLEMENT_TIMEOUT_S
                )

            for line in self._observe_lines(
                phase,
                respect_cancel=False,
                deadline=cancel_deadline,
                timeout_phase=(
                    "cancel_settlement"
                    if cancel_deadline is not None
                    else None
                ),
            ):
                if line.get("session") != source:
                    continue
                value = line.get("text")
                if not isinstance(value, str):
                    continue

                if (
                    value.startswith("[SYS] SEND QUEUE FULL")
                    or value.startswith("[SYS] INPUT TOO LONG")
                    or "TX FATAL " in value
                ):
                    raise RuntimeError(
                        f"{source}: Chatter sample rejected: {value}"
                    )

                for regex in (
                    _WAIT_ACK_RE,
                    _ACK_RE,
                    _FAILED_RE,
                ):
                    match = regex.search(value)
                    if match is None:
                        continue
                    candidate = match.group("user")
                    if user_id is None:
                        # Sweep owns this session and prepare cleared prior
                        # reliable work, so the first new WAIT_ACK identifies
                        # the sample. /id is a BLE/eFuse identity and must not
                        # be compared with the protocol's random session ID.
                        if regex is not _WAIT_ACK_RE:
                            continue
                        user_id = candidate
                    if candidate != user_id:
                        continue
                    if (
                        regex is _ACK_RE
                        or regex is _FAILED_RE
                    ):
                        return {
                            "tx_id": int(token["tx_id"]),
                            "user_id": user_id,
                        }

                if cancel_sent:
                    cancelled = _CANCEL_RE.search(value)
                    if (
                        cancelled is not None
                        and (
                            user_id is None
                            or cancelled.group("user") == user_id
                        )
                    ):
                        raise SweepCancelled(
                            "active Chatter reliable USER "
                            "was cancelled"
                        )
                    if value.startswith(
                        "[SYS] DELIVERY CANCEL"
                    ):
                        raise SweepCancelled(
                            "Chatter reliable USER "
                            "cancellation settled"
                        )

    def cleanup(
        self,
        phase: SweepPhaseContext,
    ) -> None:
        for session in self.sessions:
            self.context.send_line(
                session,
                "/sweep off",
            )
            self._wait_line(
                session,
                lambda line:
                    line in {
                        "[SYS] SWEEP OFF",
                        "[SYS] SWEEP already OFF",
                    },
                phase,
                respect_cancel=False,
            )


def create_reliable_user_sweep_adapter(
    context: SweepAdapterContext,
    sessions: tuple[str, ...],
    plan: SweepPlan,
) -> ChatterReliableUserSweepAdapter:
    return ChatterReliableUserSweepAdapter(
        context,
        sessions,
        plan,
    )
