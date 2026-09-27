import threading
import time

import pytest

from serialterminal.sweep import (
    SweepError,
    SweepJob,
    SweepJobManager,
    normalize_sweep_plan,
)


class _Context:
    pass


class _RecordingAdapter:
    name = "test.recording"

    def __init__(self):
        self.samples = []
        self.applied = []
        self.verified = []
        self.cleaned = False

    def phase_timeout_s(self, phase, coordinate):
        return 1.0

    def prepare(self, phase):
        phase.raise_if_cancelled()

    def apply_coordinate(self, coordinate, phase):
        phase.raise_if_cancelled()
        self.applied.append(dict(coordinate))

    def verify_coordinate(self, coordinate, phase):
        phase.raise_if_cancelled()
        self.verified.append(dict(coordinate))

    def start_sample(self, coordinate, repetition, phase):
        phase.raise_if_cancelled()
        return (dict(coordinate), repetition)

    def wait_sample_settled(
        self,
        coordinate,
        repetition,
        token,
        phase,
    ):
        phase.raise_if_cancelled()
        self.samples.append((dict(coordinate), repetition))
        return {"sample_id": f"s{len(self.samples)}"}

    def cleanup(self, phase):
        self.cleaned = True


class _BlockingAdapter(_RecordingAdapter):
    name = "test.blocking"

    def __init__(self):
        super().__init__()
        self.prepare_started = threading.Event()
        self.release = threading.Event()

    def prepare(self, phase):
        self.prepare_started.set()
        while not self.release.wait(timeout=0.01):
            phase.raise_if_cancelled()


class _FailingAdapter(_RecordingAdapter):
    def prepare(self, phase):
        raise RuntimeError("boom")


class _CleanupTimeoutAdapter(_RecordingAdapter):
    def phase_timeout_s(self, phase, coordinate):
        if phase == "cleanup":
            return 0.01
        return 1.0

    def cleanup(self, phase):
        time.sleep(0.02)


class _PrimaryAndCleanupFailureAdapter(_CleanupTimeoutAdapter):
    def prepare(self, phase):
        raise RuntimeError("primary boom")


class _BlockingRunLog:
    def __init__(self):
        self.terminal_record_started = threading.Event()
        self.release_terminal_record = threading.Event()

    def record(self, tag, payload):
        if (
            tag == "SWEEP"
            and payload.get("kind") == "sweep_completed"
        ):
            self.terminal_record_started.set()
            assert self.release_terminal_record.wait(timeout=1.0)


def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def _manager(adapter_holder, *, max_retained_terminal=16):
    owned = set()

    def acquire(sweep_id, sessions):
        assert not owned
        owned.update(sessions)

    def release(sweep_id, sessions):
        owned.difference_update(sessions)

    return (
        SweepJobManager(
            acquire_sessions=acquire,
            release_sessions=release,
            run_log=None,
            max_retained_terminal=max_retained_terminal,
        ),
        owned,
    )


@pytest.mark.parametrize(
    "plan",
    [
        {
            "axes": [
                {"name": "sf", "values": [7]},
                {"name": "sf", "values": [8]},
            ],
            "repetitions": 1,
        },
        {
            "constants": {"sf": 7},
            "axes": [{"name": "sf", "values": [8]}],
            "repetitions": 1,
        },
        {
            "axes": [{"name": "sf", "values": []}],
            "repetitions": 1,
        },
        {"axes": [], "repetitions": 0},
        {"axes": [], "repetitions": -1},
        {"axes": [], "repetitions": True},
    ],
)
def test_plan_schema_hygiene_rejects_invalid_shape(plan):
    with pytest.raises(SweepError) as caught:
        normalize_sweep_plan(plan)
    assert caught.value.code == "invalid_sweep_plan"


def test_plan_rejects_absurd_cartesian_product_before_job_creation():
    with pytest.raises(SweepError) as caught:
        normalize_sweep_plan(
            {
                "axes": [
                    {"name": "a", "values": list(range(400))},
                    {"name": "b", "values": list(range(400))},
                ],
                "repetitions": 1,
            }
        )
    assert caught.value.code == "sweep_plan_too_large"


def test_plan_rejects_oversized_serialized_input():
    with pytest.raises(SweepError) as caught:
        normalize_sweep_plan(
            {
                "constants": {"blob": "x" * (70 * 1024)},
                "axes": [],
                "repetitions": 1,
            }
        )
    assert caught.value.code == "sweep_plan_too_large"


@pytest.mark.parametrize("repetitions", [3, 10])
def test_exact_repetitions_and_ordered_axis_traversal(repetitions):
    plan = normalize_sweep_plan(
        {
            "constants": {"fixed": 1},
            "axes": [
                {"name": "sf", "values": [7, 8]},
                {"name": "direction", "values": ["a>b", "b>a"]},
            ],
            "repetitions": repetitions,
        }
    )
    adapter = _RecordingAdapter()
    manager, owned = _manager(adapter)
    started = manager.start(
        sessions=("s1", "s2"),
        plan=plan,
        adapter=adapter,
    )
    sweep_id = started["sweep_id"]

    assert _wait_until(
        lambda: manager.observe(
            sweep_id,
            cursor=0,
            window=100,
            timeout_ms=0,
        )["state"]
        == "completed"
    )
    assert len(adapter.samples) == 4 * repetitions
    assert adapter.samples == [
        ({"fixed": 1, "sf": sf, "direction": direction}, repetition)
        for sf in [7, 8]
        for direction in ["a>b", "b>a"]
        for repetition in range(1, repetitions + 1)
    ]
    assert not owned


def test_requested_window_is_capped_and_head_is_independent():
    plan = normalize_sweep_plan(
        {
            "axes": [{"name": "x", "values": [1, 2, 3]}],
            "repetitions": 2,
        }
    )
    adapter = _RecordingAdapter()
    manager, _ = _manager(adapter)
    sweep_id = manager.start(
        sessions=("s1",),
        plan=plan,
        adapter=adapter,
    )["sweep_id"]
    assert _wait_until(
        lambda: manager.observe(
            sweep_id,
            cursor=0,
            window=100,
            timeout_ms=0,
        )["state"]
        == "completed"
    )

    first = manager.observe(
        sweep_id,
        cursor=0,
        window=1_000_000,
        timeout_ms=0,
    )
    assert len(first["events"]) == first["cursor"]
    assert len(first["events"]) <= first["head_cursor"]
    assert len(first["events"]) <= 100
    if first["cursor"] < first["head_cursor"]:
        second = manager.observe(
            sweep_id,
            cursor=first["cursor"],
            window=100,
            timeout_ms=0,
        )
        assert second["events"][0]["seq"] == first["cursor"] + 1


def test_cursor_algebra_is_off_by_one_safe_and_duplicate_reads_are_stable():
    plan = normalize_sweep_plan({"axes": [], "repetitions": 1})
    job = SweepJob(
        sweep_id="sw1",
        sessions=("s1",),
        plan=plan,
        adapter=_RecordingAdapter(),
        release_sessions=lambda *_: None,
        run_log=None,
        event_retention=3,
        max_window=2,
    )
    for value in range(1, 6):
        job._record_event("test", value=value)

    with pytest.raises(SweepError) as expired:
        job.observe(1, 2, 0)
    assert expired.value.code == "sweep_cursor_expired"
    assert expired.value.details["oldest_retained_event_seq"] == 3
    assert expired.value.details["oldest_valid_cursor"] == 2

    valid = job.observe(2, 99, 0)
    assert [event["seq"] for event in valid["events"]] == [3, 4]
    assert valid["cursor"] == 4
    assert valid["head_cursor"] == 5

    duplicate = job.observe(2, 99, 0)
    assert duplicate["events"] == valid["events"]

    with pytest.raises(SweepError) as future:
        job.observe(6, 1, 0)
    assert future.value.code == "invalid_sweep_cursor"


@pytest.mark.parametrize("cursor", [-1, True, 1.5, "1"])
def test_sweep_cursor_is_strictly_typed(cursor):
    plan = normalize_sweep_plan({"axes": [], "repetitions": 1})
    job = SweepJob(
        sweep_id="sw1",
        sessions=("s1",),
        plan=plan,
        adapter=_RecordingAdapter(),
        release_sessions=lambda *_: None,
        run_log=None,
    )
    with pytest.raises(SweepError) as caught:
        job.observe(cursor, 1, 0)
    assert caught.value.code == "invalid_sweep_cursor"


def test_start_metadata_progress_and_long_poll_wakeup():
    plan = normalize_sweep_plan({"axes": [], "repetitions": 1})
    adapter = _BlockingAdapter()
    manager, _ = _manager(adapter)
    started = manager.start(
        sessions=("s1",),
        plan=plan,
        adapter=adapter,
    )
    sweep_id = started["sweep_id"]

    assert started["state"] == "running"
    assert started["total_samples"] == 1
    assert started["events"] == {
        "cursor": 0,
        "max_window": 100,
        "retention": 4096,
    }
    assert started["jobs"] == {
        "max_active": 1,
        "max_retained_terminal": 16,
    }
    assert adapter.prepare_started.wait(timeout=1.0)

    initial = manager.observe(
        sweep_id,
        cursor=0,
        window=100,
        timeout_ms=0,
    )
    assert initial["state"] == "running"
    assert initial["progress"]["total_samples"] == 1
    assert initial["progress"]["current"]["phase"] == "prepare"

    result_holder = {}
    done = threading.Event()

    def long_poll():
        result_holder["result"] = manager.observe(
            sweep_id,
            cursor=initial["cursor"],
            window=100,
            timeout_ms=1000,
        )
        done.set()

    thread = threading.Thread(target=long_poll)
    thread.start()
    assert not done.wait(timeout=0.05)

    adapter.release.set()
    assert done.wait(timeout=1.0)
    thread.join(timeout=1.0)
    assert not thread.is_alive()
    result = result_holder["result"]
    assert result["timed_out"] is False
    assert result["events"]
    assert result["cursor"] > initial["cursor"]


def test_positive_long_poll_timeout_is_explicit():
    plan = normalize_sweep_plan({"axes": [], "repetitions": 1})
    adapter = _BlockingAdapter()
    manager, _ = _manager(adapter)
    sweep_id = manager.start(
        sessions=("s1",),
        plan=plan,
        adapter=adapter,
    )["sweep_id"]
    assert adapter.prepare_started.wait(timeout=1.0)

    initial = manager.observe(
        sweep_id,
        cursor=0,
        window=100,
        timeout_ms=0,
    )
    result = manager.observe(
        sweep_id,
        cursor=initial["head_cursor"],
        window=100,
        timeout_ms=20,
    )
    assert result["events"] == []
    assert result["cursor"] == initial["head_cursor"]
    assert result["head_cursor"] == initial["head_cursor"]
    assert result["state"] == "running"
    assert result["timed_out"] is True

    manager.cancel(sweep_id)
    assert _wait_until(
        lambda: manager.observe(
            sweep_id,
            cursor=initial["head_cursor"],
            window=100,
            timeout_ms=0,
        )["state"]
        == "cancelled"
    )


def test_close_rejects_non_terminal_job():
    plan = normalize_sweep_plan({"axes": [], "repetitions": 1})
    adapter = _BlockingAdapter()
    manager, _ = _manager(adapter)
    sweep_id = manager.start(
        sessions=("s1",),
        plan=plan,
        adapter=adapter,
    )["sweep_id"]
    assert adapter.prepare_started.wait(timeout=1.0)

    with pytest.raises(SweepError) as caught:
        manager.close(sweep_id)
    assert caught.value.code == "sweep_not_terminal"

    adapter.release.set()
    assert _wait_until(
        lambda: manager.observe(
            sweep_id,
            cursor=0,
            window=100,
            timeout_ms=0,
        )["state"]
        == "completed"
    )
    assert manager.close(sweep_id)["state"] == "closed"


def test_cancel_converges_to_terminal_state_and_releases_ownership():
    plan = normalize_sweep_plan({"axes": [], "repetitions": 1})
    adapter = _BlockingAdapter()
    manager, owned = _manager(adapter)
    sweep_id = manager.start(
        sessions=("s1",),
        plan=plan,
        adapter=adapter,
    )["sweep_id"]
    assert adapter.prepare_started.wait(timeout=1.0)
    assert owned == {"s1"}

    cancelling = manager.cancel(sweep_id)
    assert cancelling["state"] == "cancelling"
    assert _wait_until(
        lambda: manager.observe(
            sweep_id,
            cursor=0,
            window=100,
            timeout_ms=0,
        )["state"]
        in {"cancelled", "failed"}
    )
    assert not owned


def test_terminal_state_event_and_forensic_record_publish_together():
    plan = normalize_sweep_plan({"axes": [], "repetitions": 1})
    run_log = _BlockingRunLog()
    job = SweepJob(
        sweep_id="sw1",
        sessions=("s1",),
        plan=plan,
        adapter=_RecordingAdapter(),
        release_sessions=lambda *_: None,
        run_log=run_log,
    )

    terminal_thread = threading.Thread(
        target=job._terminal,
        args=("completed",),
    )
    terminal_thread.start()
    assert run_log.terminal_record_started.wait(timeout=1.0)

    result_holder = {}
    observe_done = threading.Event()

    def observe():
        result_holder["result"] = job.observe(
            0,
            100,
            1000,
        )
        observe_done.set()

    observe_thread = threading.Thread(target=observe)
    observe_thread.start()
    assert not observe_done.wait(timeout=0.05)

    run_log.release_terminal_record.set()
    terminal_thread.join(timeout=1.0)
    observe_thread.join(timeout=1.0)
    assert not terminal_thread.is_alive()
    assert not observe_thread.is_alive()

    result = result_holder["result"]
    assert result["state"] == "completed"
    assert result["events"][-1]["kind"] == "sweep_completed"
    assert result["cursor"] == result["head_cursor"]


def test_cleanup_timeout_becomes_terminal_job_failure():
    plan = normalize_sweep_plan({"axes": [], "repetitions": 1})
    manager, _ = _manager(_CleanupTimeoutAdapter())
    sweep_id = manager.start(
        sessions=("s1",),
        plan=plan,
        adapter=_CleanupTimeoutAdapter(),
    )["sweep_id"]

    assert _wait_until(
        lambda: manager.observe(
            sweep_id,
            cursor=0,
            window=100,
            timeout_ms=0,
        )["state"]
        == "failed"
    )
    result = manager.observe(
        sweep_id,
        cursor=0,
        window=100,
        timeout_ms=0,
    )
    assert result["failure"]["code"] == "cleanup_timeout"


def test_job_failure_is_state_not_observe_api_failure():
    plan = normalize_sweep_plan({"axes": [], "repetitions": 1})
    manager, _ = _manager(_FailingAdapter())
    sweep_id = manager.start(
        sessions=("s1",),
        plan=plan,
        adapter=_FailingAdapter(),
    )["sweep_id"]
    assert _wait_until(
        lambda: manager.observe(
            sweep_id,
            cursor=0,
            window=100,
            timeout_ms=0,
        )["state"]
        == "failed"
    )
    result = manager.observe(
        sweep_id,
        cursor=0,
        window=100,
        timeout_ms=0,
    )
    assert result["state"] == "failed"
    assert result["failure"]["code"] in {
        "adapter_failed",
        "cleanup_failed",
    }


def test_terminal_retention_has_hard_count_bound():
    manager, _ = _manager(
        _RecordingAdapter(),
        max_retained_terminal=2,
    )
    plan = normalize_sweep_plan({"axes": [], "repetitions": 1})
    sweep_ids = []
    for _ in range(3):
        sweep_id = manager.start(
            sessions=("s1",),
            plan=plan,
            adapter=_RecordingAdapter(),
        )["sweep_id"]
        sweep_ids.append(sweep_id)
        assert _wait_until(
            lambda sweep_id=sweep_id:
                manager.observe(
                    sweep_id,
                    cursor=0,
                    window=100,
                    timeout_ms=0,
                )["state"]
                == "completed"
        )

    with pytest.raises(SweepError) as caught:
        manager.observe(
            sweep_ids[0],
            cursor=0,
            window=1,
            timeout_ms=0,
        )
    assert caught.value.code == "unknown_sweep"
    assert manager.observe(
        sweep_ids[-1],
        cursor=0,
        window=1,
        timeout_ms=0,
    )["state"] == "completed"



def test_preflight_finishes_before_adapter_prepare_starts():
    plan = normalize_sweep_plan({"axes": [], "repetitions": 1})
    owned = set()
    preflight_started = threading.Event()
    preflight_release = threading.Event()
    adapter = _BlockingAdapter()

    def acquire(sweep_id, sessions):
        owned.update(sessions)

        def preflight(phase):
            preflight_started.set()
            while not preflight_release.wait(timeout=0.01):
                phase.raise_if_cancelled()

        return preflight

    def release(sweep_id, sessions):
        owned.difference_update(sessions)

    manager = SweepJobManager(
        acquire_sessions=acquire,
        release_sessions=release,
        run_log=None,
    )
    sweep_id = manager.start(
        sessions=("s1",),
        plan=plan,
        adapter=adapter,
    )["sweep_id"]

    assert preflight_started.wait(timeout=1.0)
    assert not adapter.prepare_started.is_set()
    assert owned == {"s1"}

    preflight_release.set()
    assert adapter.prepare_started.wait(timeout=1.0)
    adapter.release.set()
    assert _wait_until(
        lambda: manager.observe(
            sweep_id,
            cursor=0,
            window=100,
            timeout_ms=0,
        )["state"]
        == "completed"
    )


def test_cleanup_failure_preserves_primary_failure():
    plan = normalize_sweep_plan({"axes": [], "repetitions": 1})
    manager, _ = _manager(_PrimaryAndCleanupFailureAdapter())
    sweep_id = manager.start(
        sessions=("s1",),
        plan=plan,
        adapter=_PrimaryAndCleanupFailureAdapter(),
    )["sweep_id"]

    assert _wait_until(
        lambda: manager.observe(
            sweep_id,
            cursor=0,
            window=100,
            timeout_ms=0,
        )["state"]
        == "failed"
    )
    result = manager.observe(
        sweep_id,
        cursor=0,
        window=100,
        timeout_ms=0,
    )
    assert result["failure"]["code"] == "adapter_failed"
    assert result["failure"]["message"] == "primary boom"
    assert result["cleanup_failure"]["code"] == "cleanup_timeout"
