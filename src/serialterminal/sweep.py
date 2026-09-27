from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import itertools
import json
import math
import threading
import time
from typing import Any, Protocol


SWEEP_EVENT_RETENTION = 4096
SWEEP_MAX_WINDOW = 100
SWEEP_MAX_RETAINED_TERMINAL = 16
SWEEP_MAX_PLAN_BYTES = 64 * 1024
SWEEP_MAX_AXES = 16
SWEEP_MAX_TOTAL_SAMPLES = 100_000
SWEEP_MAX_PHASE_TIMEOUT_S = 3600.0


class SweepError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class SweepCancelled(RuntimeError):
    pass


class SweepPhaseTimeout(RuntimeError):
    def __init__(self, phase: str):
        super().__init__(f"sweep adapter phase timed out: {phase}")
        self.phase = phase


@dataclass(frozen=True)
class SweepAxis:
    name: str
    values: tuple[Any, ...]


@dataclass(frozen=True)
class SweepPlan:
    constants: dict[str, Any]
    axes: tuple[SweepAxis, ...]
    repetitions: int
    options: dict[str, Any]
    total_points: int
    total_samples: int

    def coordinates(self):
        if not self.axes:
            yield dict(self.constants)
            return
        names = [axis.name for axis in self.axes]
        value_sets = [axis.values for axis in self.axes]
        for values in itertools.product(*value_sets):
            coordinate = dict(self.constants)
            coordinate.update(zip(names, values))
            yield coordinate


class SweepAdapterContext(Protocol):
    def status(self, session_id: str) -> dict[str, Any]:
        ...

    def profile_name(self, session_id: str) -> str:
        ...

    def send_line(self, session_id: str, text: str) -> dict[str, Any]:
        ...

    def send_bytes(self, session_id: str, data: bytes) -> dict[str, Any]:
        ...

    def observe(
        self,
        cursors: dict[str, int],
        *,
        timeout_ms: int,
        include_events: bool = False,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class SweepPhaseContext:
    name: str
    deadline: float
    cancel_event: threading.Event

    @property
    def cancel_requested(self) -> bool:
        return self.cancel_event.is_set()

    def remaining_s(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def remaining_ms(self, maximum_ms: int = 250) -> int:
        remaining = self.remaining_s()
        if remaining <= 0:
            raise SweepPhaseTimeout(self.name)
        return max(1, min(maximum_ms, int(math.ceil(remaining * 1000.0))))

    def raise_if_cancelled(self) -> None:
        if self.cancel_requested:
            raise SweepCancelled("sweep cancellation requested")
        if self.remaining_s() <= 0:
            raise SweepPhaseTimeout(self.name)


class SweepAdapter(Protocol):
    name: str

    def phase_timeout_s(
        self,
        phase: str,
        coordinate: Mapping[str, Any] | None,
    ) -> float:
        ...

    def prepare(self, phase: SweepPhaseContext) -> None:
        ...

    def apply_coordinate(
        self,
        coordinate: Mapping[str, Any],
        phase: SweepPhaseContext,
    ) -> None:
        ...

    def verify_coordinate(
        self,
        coordinate: Mapping[str, Any],
        phase: SweepPhaseContext,
    ) -> None:
        ...

    def start_sample(
        self,
        coordinate: Mapping[str, Any],
        repetition: int,
        phase: SweepPhaseContext,
    ) -> Any:
        ...

    def wait_sample_settled(
        self,
        coordinate: Mapping[str, Any],
        repetition: int,
        token: Any,
        phase: SweepPhaseContext,
    ) -> Mapping[str, Any] | None:
        ...

    def cleanup(self, phase: SweepPhaseContext) -> None:
        ...


SweepAdapterFactory = Callable[
    [SweepAdapterContext, tuple[str, ...], SweepPlan],
    SweepAdapter,
]


def _json_size(value: Any) -> int:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SweepError(
            "invalid_sweep_plan",
            f"sweep plan is not valid JSON data: {exc}",
        ) from exc
    return len(rendered.encode("utf-8"))


def normalize_sweep_plan(raw: Any) -> SweepPlan:
    if not isinstance(raw, dict):
        raise SweepError(
            "invalid_sweep_plan",
            "sweep_start requires object field 'plan'",
        )
    if _json_size(raw) > SWEEP_MAX_PLAN_BYTES:
        raise SweepError(
            "sweep_plan_too_large",
            f"sweep plan exceeds {SWEEP_MAX_PLAN_BYTES} UTF-8 JSON bytes",
        )

    allowed = {"constants", "axes", "repetitions", "options"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise SweepError(
            "invalid_sweep_plan",
            "unknown sweep plan field(s): " + ", ".join(unknown),
        )

    constants = raw.get("constants", {})
    if not isinstance(constants, dict):
        raise SweepError(
            "invalid_sweep_plan",
            "plan.constants must be an object",
        )
    if any(not isinstance(key, str) or not key for key in constants):
        raise SweepError(
            "invalid_sweep_plan",
            "plan.constants keys must be non-empty strings",
        )

    raw_axes = raw.get("axes", [])
    if not isinstance(raw_axes, list):
        raise SweepError("invalid_sweep_plan", "plan.axes must be an array")
    if len(raw_axes) > SWEEP_MAX_AXES:
        raise SweepError(
            "sweep_plan_too_large",
            f"plan.axes exceeds maximum of {SWEEP_MAX_AXES}",
        )

    axes: list[SweepAxis] = []
    axis_names: set[str] = set()
    total_points = 1
    for index, raw_axis in enumerate(raw_axes):
        if not isinstance(raw_axis, dict):
            raise SweepError(
                "invalid_sweep_plan",
                f"plan.axes[{index}] must be an object",
            )
        unknown_axis = sorted(set(raw_axis) - {"name", "values"})
        if unknown_axis:
            raise SweepError(
                "invalid_sweep_plan",
                f"plan.axes[{index}] has unknown field(s): "
                + ", ".join(unknown_axis),
            )
        name = raw_axis.get("name")
        values = raw_axis.get("values")
        if not isinstance(name, str) or not name:
            raise SweepError(
                "invalid_sweep_plan",
                f"plan.axes[{index}].name must be a non-empty string",
            )
        if name in axis_names:
            raise SweepError(
                "invalid_sweep_plan",
                f"duplicate sweep axis name: {name}",
            )
        if name in constants:
            raise SweepError(
                "invalid_sweep_plan",
                f"sweep axis collides with constant: {name}",
            )
        if not isinstance(values, list) or not values:
            raise SweepError(
                "invalid_sweep_plan",
                f"plan.axes[{index}].values must be a non-empty array",
            )
        _json_size(values)
        if total_points > SWEEP_MAX_TOTAL_SAMPLES // len(values):
            raise SweepError(
                "sweep_plan_too_large",
                "Cartesian sweep point count is too large",
            )
        total_points *= len(values)
        axis_names.add(name)
        axes.append(SweepAxis(name=name, values=tuple(values)))

    repetitions = raw.get("repetitions")
    if (
        isinstance(repetitions, bool)
        or not isinstance(repetitions, int)
        or repetitions <= 0
    ):
        raise SweepError(
            "invalid_sweep_plan",
            "plan.repetitions must be a positive integer",
        )
    if total_points > SWEEP_MAX_TOTAL_SAMPLES // repetitions:
        raise SweepError(
            "sweep_plan_too_large",
            f"total requested samples exceed maximum of "
            f"{SWEEP_MAX_TOTAL_SAMPLES}",
        )
    total_samples = total_points * repetitions

    options = raw.get("options", {})
    if not isinstance(options, dict):
        raise SweepError(
            "invalid_sweep_plan",
            "plan.options must be an object",
        )
    _json_size(options)

    return SweepPlan(
        constants=dict(constants),
        axes=tuple(axes),
        repetitions=repetitions,
        options=dict(options),
        total_points=total_points,
        total_samples=total_samples,
    )


class SweepJob:
    _TERMINAL = frozenset({"completed", "failed", "cancelled"})

    def __init__(
        self,
        *,
        sweep_id: str,
        sessions: tuple[str, ...],
        plan: SweepPlan,
        adapter: SweepAdapter,
        release_sessions: Callable[[str, tuple[str, ...]], None],
        run_log: Any | None,
        event_retention: int = SWEEP_EVENT_RETENTION,
        max_window: int = SWEEP_MAX_WINDOW,
    ):
        self.sweep_id = sweep_id
        self.sessions = sessions
        self.plan = plan
        self.adapter = adapter
        self.release_sessions = release_sessions
        self.run_log = run_log
        self.event_retention = event_retention
        self.max_window = max_window
        self.cancel_event = threading.Event()
        self._condition = threading.Condition()
        self._events: deque[dict[str, Any]] = deque(maxlen=event_retention)
        self._next_event_seq = 1
        self._state = "running"
        self._completed_samples = 0
        self._current: dict[str, Any] | None = None
        self._failure: dict[str, Any] | None = None
        self._thread: threading.Thread | None = None

    @property
    def state(self) -> str:
        with self._condition:
            return self._state

    def start(self) -> None:
        thread = threading.Thread(
            target=self._run,
            name=f"serialterminal-sweep-{self.sweep_id}",
            daemon=True,
        )
        self._thread = thread
        thread.start()

    def join(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)

    def _phase_context(
        self,
        phase: str,
        coordinate: Mapping[str, Any] | None = None,
    ) -> SweepPhaseContext:
        timeout = self.adapter.phase_timeout_s(phase, coordinate)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(float(timeout))
            or timeout <= 0
            or timeout > SWEEP_MAX_PHASE_TIMEOUT_S
        ):
            raise RuntimeError(
                f"adapter returned invalid timeout for {phase}: {timeout!r}"
            )
        return SweepPhaseContext(
            name=phase,
            deadline=time.monotonic() + float(timeout),
            cancel_event=self.cancel_event,
        )

    def _run_phase(
        self,
        phase: str,
        callback: Callable[[SweepPhaseContext], Any],
        coordinate: Mapping[str, Any] | None = None,
        *,
        check_cancel_before: bool = True,
    ) -> Any:
        context = self._phase_context(phase, coordinate)
        if check_cancel_before:
            context.raise_if_cancelled()
        result = callback(context)
        if context.remaining_s() <= 0:
            raise SweepPhaseTimeout(phase)
        return result

    def _snapshot_locked(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "progress": {
                "completed_samples": self._completed_samples,
                "total_samples": self.plan.total_samples,
                "current": (
                    dict(self._current)
                    if self._current is not None
                    else None
                ),
            },
            "failure": (
                dict(self._failure)
                if self._failure is not None
                else None
            ),
        }

    def _record_event(
        self,
        kind: str,
        **fields: Any,
    ) -> dict[str, Any]:
        with self._condition:
            event = {
                "seq": self._next_event_seq,
                "kind": kind,
                "timestamp": time.time(),
                **fields,
            }
            self._next_event_seq += 1
            self._events.append(event)
            self._condition.notify_all()
        if self.run_log is not None:
            self.run_log.record(
                "SWEEP",
                {
                    "sweep_id": self.sweep_id,
                    "event_seq": event["seq"],
                    "kind": kind,
                    **fields,
                },
            )
        return event

    def _set_current(
        self,
        coordinate: Mapping[str, Any] | None,
        repetition: int | None,
        phase: str | None,
    ) -> None:
        with self._condition:
            if coordinate is None:
                self._current = None
                return
            current: dict[str, Any] = {"coordinate": dict(coordinate)}
            if repetition is not None:
                current["repetition"] = repetition
            if phase is not None:
                current["phase"] = phase
            self._current = current

    def _terminal(
        self,
        state: str,
        *,
        failure: dict[str, Any] | None = None,
    ) -> None:
        assert state in self._TERMINAL
        kind = {
            "completed": "sweep_completed",
            "failed": "sweep_failed",
            "cancelled": "sweep_cancelled",
        }[state]
        with self._condition:
            self._state = state
            self._failure = failure
            self._current = None
            # Terminal state становится видимым только вместе с event wakeup.
            # Ownership освобождается раньше, чтобы видимый terminal snapshot
            # уже соответствовал доступности внешних session mutations.
            self.release_sessions(self.sweep_id, self.sessions)
        self._record_event(
            kind,
            **({"failure": failure} if failure is not None else {}),
        )

    def _run(self) -> None:
        terminal = "completed"
        failure: dict[str, Any] | None = None
        prepared = False
        try:
            self._record_event("sweep_started")
            self._set_current({}, None, "prepare")
            self._run_phase("prepare", self.adapter.prepare)
            prepared = True

            for coordinate in self.plan.coordinates():
                if self.cancel_event.is_set():
                    raise SweepCancelled("sweep cancellation requested")
                self._set_current(coordinate, None, "apply")
                self._record_event(
                    "coordinate_started",
                    coordinate=dict(coordinate),
                )
                self._run_phase(
                    "apply",
                    lambda phase, coordinate=coordinate:
                        self.adapter.apply_coordinate(coordinate, phase),
                    coordinate,
                )
                self._set_current(coordinate, None, "verify")
                self._run_phase(
                    "verify",
                    lambda phase, coordinate=coordinate:
                        self.adapter.verify_coordinate(coordinate, phase),
                    coordinate,
                )

                for repetition in range(1, self.plan.repetitions + 1):
                    if self.cancel_event.is_set():
                        raise SweepCancelled(
                            "sweep cancellation requested"
                        )
                    self._set_current(
                        coordinate,
                        repetition,
                        "sample_start",
                    )
                    token = self._run_phase(
                        "sample_start",
                        lambda phase,
                        coordinate=coordinate,
                        repetition=repetition:
                            self.adapter.start_sample(
                                coordinate,
                                repetition,
                                phase,
                            ),
                        coordinate,
                    )
                    self._set_current(
                        coordinate,
                        repetition,
                        "sample_settlement",
                    )
                    sample = self._run_phase(
                        "sample_settlement",
                        lambda phase,
                        coordinate=coordinate,
                        repetition=repetition,
                        token=token:
                            self.adapter.wait_sample_settled(
                                coordinate,
                                repetition,
                                token,
                                phase,
                            ),
                        coordinate,
                        check_cancel_before=False,
                    )
                    with self._condition:
                        self._completed_samples += 1
                    event_fields: dict[str, Any] = {
                        "coordinate": dict(coordinate),
                        "repetition": repetition,
                    }
                    if sample is not None:
                        event_fields["sample"] = dict(sample)
                    self._record_event(
                        "sample_completed",
                        **event_fields,
                    )
                    if self.cancel_event.is_set():
                        raise SweepCancelled(
                            "sweep cancellation requested"
                        )

                self._record_event(
                    "coordinate_completed",
                    coordinate=dict(coordinate),
                )

        except SweepCancelled:
            terminal = "cancelled"
        except SweepPhaseTimeout as exc:
            terminal = "failed"
            failure = {
                "code": "adapter_timeout",
                "phase": exc.phase,
                "message": str(exc),
            }
        except Exception as exc:
            terminal = "failed"
            failure = {
                "code": "adapter_failed",
                "message": str(exc),
            }
        finally:
            if prepared or terminal != "completed":
                try:
                    self._set_current({}, None, "cleanup")
                    self._run_phase(
                        "cleanup",
                        self.adapter.cleanup,
                        check_cancel_before=False,
                    )
                except SweepPhaseTimeout as exc:
                    terminal = "failed"
                    failure = {
                        "code": "cleanup_timeout",
                        "phase": exc.phase,
                        "message": str(exc),
                    }
                except Exception as exc:
                    terminal = "failed"
                    failure = {
                        "code": "cleanup_failed",
                        "message": str(exc),
                    }
            self._terminal(terminal, failure=failure)

    def cancel(self) -> dict[str, Any]:
        with self._condition:
            if self._state in self._TERMINAL:
                return {
                    "sweep_id": self.sweep_id,
                    "state": self._state,
                }
            self._state = "cancelling"
            self.cancel_event.set()
            self._condition.notify_all()
            return {
                "sweep_id": self.sweep_id,
                "state": self._state,
            }

    def observe(
        self,
        cursor: int,
        window: int,
        timeout_ms: int,
    ) -> dict[str, Any]:
        if (
            isinstance(cursor, bool)
            or not isinstance(cursor, int)
            or cursor < 0
        ):
            raise SweepError(
                "invalid_sweep_cursor",
                "cursor must be a non-negative integer",
            )
        if (
            isinstance(window, bool)
            or not isinstance(window, int)
            or window <= 0
        ):
            raise SweepError(
                "invalid_sweep_window",
                "window must be a positive integer",
            )
        if (
            isinstance(timeout_ms, bool)
            or not isinstance(timeout_ms, int)
            or timeout_ms < 0
        ):
            raise SweepError(
                "invalid_timeout",
                "timeout_ms must be a non-negative integer",
            )

        deadline = time.monotonic() + timeout_ms / 1000.0
        with self._condition:
            while True:
                head = self._next_event_seq - 1
                if cursor > head:
                    raise SweepError(
                        "invalid_sweep_cursor",
                        "cursor is newer than the current sweep event head",
                        {
                            "requested_cursor": cursor,
                            "head_cursor": head,
                        },
                    )
                if self._events:
                    oldest_retained = self._events[0]["seq"]
                    oldest_valid = oldest_retained - 1
                else:
                    oldest_retained = self._next_event_seq
                    oldest_valid = head
                if cursor < oldest_valid:
                    raise SweepError(
                        "sweep_cursor_expired",
                        "requested sweep cursor is older than "
                        "retained event history",
                        {
                            "requested_cursor": cursor,
                            "oldest_valid_cursor": oldest_valid,
                            "oldest_retained_event_seq":
                                oldest_retained,
                            "head_cursor": head,
                        },
                    )

                available = [
                    event
                    for event in self._events
                    if event["seq"] > cursor
                ]
                if (
                    available
                    or self._state in self._TERMINAL
                    or timeout_ms == 0
                ):
                    selected = available[
                        : min(window, self.max_window)
                    ]
                    response_cursor = (
                        selected[-1]["seq"]
                        if selected
                        else cursor
                    )
                    snapshot = self._snapshot_locked()
                    result = {
                        "events": [
                            dict(event)
                            for event in selected
                        ],
                        "cursor": response_cursor,
                        "head_cursor": head,
                        "state": snapshot["state"],
                        "progress": snapshot["progress"],
                        "timed_out": False,
                    }
                    if snapshot["failure"] is not None:
                        result["failure"] = snapshot["failure"]
                    return result

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    snapshot = self._snapshot_locked()
                    result = {
                        "events": [],
                        "cursor": cursor,
                        "head_cursor": head,
                        "state": snapshot["state"],
                        "progress": snapshot["progress"],
                        "timed_out": True,
                    }
                    if snapshot["failure"] is not None:
                        result["failure"] = snapshot["failure"]
                    return result
                self._condition.wait(timeout=remaining)


class SweepJobManager:
    def __init__(
        self,
        *,
        acquire_sessions:
            Callable[[str, tuple[str, ...]], None],
        release_sessions:
            Callable[[str, tuple[str, ...]], None],
        run_log: Any | None,
        max_retained_terminal: int =
            SWEEP_MAX_RETAINED_TERMINAL,
    ):
        self.acquire_sessions = acquire_sessions
        self.release_sessions = release_sessions
        self.run_log = run_log
        self.max_retained_terminal = max_retained_terminal
        self._lock = threading.Lock()
        self._jobs: dict[str, SweepJob] = {}
        self._terminal_order: deque[str] = deque()
        self._next_id = 1
        self._active_id: str | None = None

    def start(
        self,
        *,
        sessions: tuple[str, ...],
        plan: SweepPlan,
        adapter: SweepAdapter,
    ) -> dict[str, Any]:
        with self._lock:
            if self._active_id is not None:
                raise SweepError(
                    "sweep_busy",
                    f"another sweep is active: {self._active_id}",
                    {"sweep_id": self._active_id},
                )
            sweep_id = f"sw{self._next_id}"
            self._next_id += 1
            self.acquire_sessions(sweep_id, sessions)
            job = SweepJob(
                sweep_id=sweep_id,
                sessions=sessions,
                plan=plan,
                adapter=adapter,
                release_sessions=self._release_from_job,
                run_log=self.run_log,
            )
            self._jobs[sweep_id] = job
            self._active_id = sweep_id
            try:
                job.start()
            except Exception:
                self._jobs.pop(sweep_id, None)
                self._active_id = None
                self.release_sessions(sweep_id, sessions)
                raise
        return {
            "sweep_id": sweep_id,
            "state": "running",
            "total_samples": plan.total_samples,
            "events": {
                "cursor": 0,
                "max_window": job.max_window,
                "retention": job.event_retention,
            },
            "jobs": {
                "max_active": 1,
                "max_retained_terminal":
                    self.max_retained_terminal,
            },
        }

    def _release_from_job(
        self,
        sweep_id: str,
        sessions: tuple[str, ...],
    ) -> None:
        self.release_sessions(sweep_id, sessions)
        with self._lock:
            if self._active_id == sweep_id:
                self._active_id = None
            self._terminal_order.append(sweep_id)
            self._evict_terminal_locked()

    def _evict_terminal_locked(self) -> None:
        while (
            len(self._terminal_order)
            > self.max_retained_terminal
        ):
            sweep_id = self._terminal_order.popleft()
            self._jobs.pop(sweep_id, None)

    def _get(self, sweep_id: str) -> SweepJob:
        with self._lock:
            job = self._jobs.get(sweep_id)
        if job is None:
            raise SweepError(
                "unknown_sweep",
                f"unknown sweep: {sweep_id}",
            )
        return job

    def observe(
        self,
        sweep_id: str,
        *,
        cursor: int,
        window: int,
        timeout_ms: int,
    ) -> dict[str, Any]:
        return self._get(sweep_id).observe(
            cursor,
            window,
            timeout_ms,
        )

    def cancel(self, sweep_id: str) -> dict[str, Any]:
        return self._get(sweep_id).cancel()

    def close(self, sweep_id: str) -> dict[str, Any]:
        job = self._get(sweep_id)
        state = job.state
        if state not in SweepJob._TERMINAL:
            raise SweepError(
                "sweep_not_terminal",
                f"sweep is not terminal: {sweep_id}",
                {"state": state},
            )
        with self._lock:
            if self._jobs.get(sweep_id) is not job:
                raise SweepError(
                    "unknown_sweep",
                    f"unknown sweep: {sweep_id}",
                )
            self._jobs.pop(sweep_id, None)
            try:
                self._terminal_order.remove(sweep_id)
            except ValueError:
                pass
        return {
            "sweep_id": sweep_id,
            "state": "closed",
        }

    def cancel_active(self) -> None:
        with self._lock:
            active_id = self._active_id
            active = (
                self._jobs.get(active_id)
                if active_id is not None
                else None
            )
        if active is not None:
            active.cancel()

    def join_all(self, timeout: float) -> None:
        deadline = time.monotonic() + max(0.0, timeout)
        with self._lock:
            jobs = list(self._jobs.values())
        for job in jobs:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            job.join(timeout=remaining)
