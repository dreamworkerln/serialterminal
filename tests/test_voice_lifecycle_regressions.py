import signal
import subprocess
import sys
import threading

import pytest

from serialterminal.file_transfer import FileTransferManager
from serialterminal.voice_audio import AlsaAudioBackend, CaptureResult, VoiceAudioError, _AlsaCapture
from serialterminal.voice_codec import VoiceCodecError
from test_file_transfer_core import _PairBinaryTransport
from test_voice_audio import _FakeCaptureProcess
from test_voice_service import FakeAudio, FakeCapture, FakeManager, make_service, record_and_stop, wait_for


def received_voice(manager, transfer_id="00000000000000bb"):
    path = manager.receive_dir / "incoming.stvoice.c2"
    path.write_bytes(bytes.fromhex("c0dec201020000") + b"\x09" * 8)
    progress = {"transfer_id": transfer_id, "direction": "RX", "filename": path.name,
                "state": "completed", "final_path": str(path)}
    manager.snapshot = progress
    return {"transfer_id": transfer_id, "direction": "RX", "filename": path.name,
            "kind": "transfer_completed", "progress": dict(progress)}


@pytest.mark.parametrize("second_stage", ["recording", "admitting"])
def test_old_real_ft1_terminal_preserves_new_capture_owner(tmp_path, monkeypatch, second_stage):
    left, right = _PairBinaryTransport(), _PairBinaryTransport()
    left.peer, right.peer = right, left
    first_send, terminal_entered = threading.Event(), threading.Event()
    release_terminal, terminal_applied = threading.Event(), threading.Event()
    second_admit, release_admit = threading.Event(), threading.Event()
    service = None

    def sink(event):
        if event.get("direction") == "TX" and event.get("kind") == "binary_send_start":
            assert first_send.wait(3)
        if service is not None:
            service.on_ft1_event(event, tx)

    tx = FileTransferManager(left, receive_dir=tmp_path / "left-rx", event_sink=sink)
    rx = FileTransferManager(right, receive_dir=tmp_path / "right-rx")
    service = make_service(tmp_path, tx)
    handle = service._handle_ft1_event
    send = tx.start_send
    calls = 0

    def gated_handle(envelope):
        if envelope.event.get("direction") == "TX" and envelope.event.get("kind") == "transfer_completed":
            terminal_entered.set()
            assert release_terminal.wait(3)
            handle(envelope)
            terminal_applied.set()
        else:
            handle(envelope)

    def gated_admission(path):
        nonlocal calls
        calls += 1
        if calls == 2 and second_stage == "admitting":
            second_admit.set()
            assert release_admit.wait(3)
        return send(path)

    monkeypatch.setattr(service, "_handle_ft1_event", gated_handle)
    monkeypatch.setattr(tx, "start_send", gated_admission)
    try:
        record_and_stop(service)
        wait_for(lambda: service.snapshot().state == "IDLE")
        first_source = next((tmp_path / "voice-temp").glob("*.stvoice.c2"))
        first_send.set()
        assert terminal_entered.wait(3)
        wait_for(lambda: not tx.busy)
        assert rx.display_snapshot()["state"] == "completed"
        assert service.toggle_recording()
        wait_for(lambda: service.snapshot().state == "RECORDING")
        if second_stage == "admitting":
            assert service.toggle_recording()
            assert second_admit.wait(3)
        expected = "ADMITTING" if second_stage == "admitting" else "RECORDING"
        assert service.snapshot().state == expected
        release_terminal.set()
        assert terminal_applied.wait(3)
        assert service.snapshot().state == expected
        assert service.local_operation_active()
        assert not first_source.exists()
        if second_stage == "recording":
            assert service.toggle_recording()
        else:
            release_admit.set()
        wait_for(lambda: len(list(rx.receive_dir.glob("*.stvoice.c2"))) == 2)
        wait_for(lambda: service.snapshot().state == "IDLE" and not tx.busy)
        wait_for(lambda: not list((tmp_path / "voice-temp").glob("*.stvoice.c2")))
    finally:
        first_send.set()
        release_terminal.set()
        release_admit.set()
        service.close()
        tx.close()
        rx.close()


@pytest.mark.parametrize("overflow", [False, True])
def test_two_admitted_attempts_keep_independent_cleanup(tmp_path, overflow):
    class SequentialManager(FakeManager):
        def start_send(self, path):
            result = super().start_send(path)
            result["transfer_id"] = f"{len(sources) + 1:016x}"
            self.snapshot = result
            sources.append((path, dict(result)))
            return result

    sources = []
    manager = SequentialManager(tmp_path / "rx")
    service = make_service(tmp_path, manager)
    try:
        for count in (1, 2):
            record_and_stop(service)
            wait_for(lambda: len(sources) == count and service.snapshot().state == "IDLE")
        if overflow:
            manager.snapshot = {**sources[-1][1], "state": "completed"}
            manager.snapshots = lambda: [{**result, "state": "completed"} for _, result in sources]
            service._overflow_manager = manager
            service._reconcile_overflow()
        else:
            for path, result in sources:
                service.on_ft1_event({**result, "kind": "transfer_completed",
                                      "progress": {**result, "state": "completed"}}, manager)
        wait_for(lambda: all(not path.exists() for path, _ in sources))
    finally:
        service.close()


@pytest.mark.parametrize("startup_fails", [False, True])
def test_rx_playback_waits_through_startup_timeout(tmp_path, startup_fails):
    class DelayedAudio(FakeAudio):
        def __init__(self):
            super().__init__()
            self.entered, self.release = threading.Event(), threading.Event()
            self.block_playback = True

        def start_capture(self):
            self.entered.set()
            assert self.release.wait(3)
            if startup_fails:
                raise VoiceAudioError("capture startup failed")
            return super().start_capture()

    audio = DelayedAudio()
    manager = FakeManager(tmp_path / "rx", mode="busy")
    service = make_service(tmp_path, manager, audio=audio)
    try:
        assert service.toggle_recording() and audio.entered.wait(3)
        service.on_ft1_event(received_voice(manager), manager)
        assert not audio.play_started.wait(0.35)
        assert service.snapshot().state == "STARTING"
        audio.release.set()
        if not startup_fails:
            wait_for(lambda: service.snapshot().state == "RECORDING")
            assert not audio.play_started.is_set()
            assert service.toggle_recording()
        assert audio.play_started.wait(3)
        assert service.toggle_recording() is False
        audio.play_release.set()
        wait_for(lambda: len(audio.played) == 1)
    finally:
        audio.release.set()
        audio.play_release.set()
        service.close()


@pytest.mark.parametrize("code,forced,requested,stderr,send", [
    (0, False, True, "", True),
    (-signal.SIGINT, False, True, "", True),
    (1, False, True, "", True),
    (1, False, True, "audio read error", False),
    (1, False, False, "", False),
    (1, True, True, "", False),
    (-signal.SIGKILL, False, True, "", False),
    (2, False, True, "", False),
    (0, True, True, "", False),
    (0, False, False, "", False),
])
def test_capture_stop_outcome_controls_auto_send(tmp_path, code, forced, requested, stderr, send):
    class ResultCapture(FakeCapture):
        def finish(self):
            return CaptureResult(returncode=code, requested_stop=self.stop and requested,
                                 stderr=stderr, forced_stop=forced)

    class ResultAudio(FakeAudio):
        def start_capture(self):
            return ResultCapture(self.chunks)

    manager = FakeManager(tmp_path / "rx")
    service = make_service(tmp_path, manager, audio=ResultAudio())
    try:
        record_and_stop(service)
        wait_for(lambda: service.snapshot().state in {"IDLE", "READY_FILE"})
        assert manager.started.is_set() is send
        if not send:
            assert not list((tmp_path / "voice-temp").glob("*.stvoice.c2"))
            assert not list((tmp_path / "voice-temp").glob("*.partial"))
            assert any("failed" in line for line in service.drain_notifications())
    finally:
        service.close()


def test_capture_backend_records_forced_fallback_even_if_exit_zero():
    process = _FakeCaptureProcess(wait_results=["timeout", 0, 0])
    capture = _AlsaCapture(process, stop_timeout=0.01, kill_timeout=0.01)
    try:
        capture.request_stop()
        result = capture.finish()
        assert result.returncode == 0
        assert getattr(result, "forced_stop", False)
        assert not getattr(result, "graceful_stop", True)
    finally:
        capture.close()


@pytest.mark.parametrize("replace_during_validation", [False, True])
def test_obsolete_rx_is_not_admitted_after_manager_replacement(tmp_path, monkeypatch, replace_during_validation):
    old, new = FakeManager(tmp_path / "old"), FakeManager(tmp_path / "new")
    audio = FakeAudio()
    service = make_service(tmp_path, old, audio=audio)
    event = received_voice(old)
    entered, release = threading.Event(), threading.Event()
    import serialterminal.voice_service as voice_module
    validate = voice_module.validate_c2_file

    def delayed_validate(path, **kwargs):
        entered.set()
        assert release.wait(3)
        return validate(path, **kwargs)

    try:
        if replace_during_validation:
            monkeypatch.setattr(voice_module, "validate_c2_file", delayed_validate)
            service.on_ft1_event(event, old)
            assert entered.wait(3)
        service.detach_manager(old)
        service.bind_manager(new)
        if not replace_during_validation:
            service.on_ft1_event(event, old)
        release.set()
        assert not audio.play_started.wait(0.35)
        assert (old.receive_dir / "incoming.stvoice.c2").exists()
        monkeypatch.setattr(voice_module, "validate_c2_file", validate)
        service.on_ft1_event(received_voice(new, "00000000000000cc"), new)
        wait_for(lambda: len(audio.played) == 1)
    finally:
        release.set()
        service.close()


@pytest.mark.parametrize("failure", ["decode", "write"])
def test_playback_error_reaps_real_child(tmp_path, monkeypatch, failure):
    processes = []

    def spawn(_argv, **kwargs):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
        processes.append(process)
        if failure == "write":
            class BrokenInput:
                closed = False

                def write(self, _data):
                    raise BrokenPipeError("injected pipe failure")

                def close(self):
                    self.closed = True
            original = process.stdin
            process.stdin = BrokenInput()
            process.original_stdin = original
        return process

    def chunks():
        if failure == "decode":
            raise VoiceCodecError("decode failed")
        yield b"\x00\x00" * 160

    backend = AlsaAudioBackend(popen_factory=spawn)
    monkeypatch.setattr(backend, "availability", lambda: (True, ""))
    expected = VoiceCodecError if failure == "decode" else VoiceAudioError
    try:
        with pytest.raises(expected):
            backend.play_pcm(chunks(), threading.Event())
        assert processes[0].poll() is not None
        backend.stop_playback()
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=3)
            if hasattr(process, "original_stdin"):
                process.original_stdin.close()


def test_graceful_capture_result_accepts_requested_sigint():
    result = CaptureResult(-signal.SIGINT, True, "")
    assert getattr(result, "graceful_stop", False)


def test_capture_that_exited_before_stop_is_not_a_requested_completion():
    process = _FakeCaptureProcess(wait_results=[0, 0])
    process.poll = lambda: 0
    capture = _AlsaCapture(process, stop_timeout=0.01, kill_timeout=0.01)
    try:
        capture.request_stop()
        result = capture.finish()
        assert result.requested_stop is False
        assert not result.graceful_stop
        assert process.signals == []
    finally:
        capture.close()


def test_pre_cancelled_playback_does_not_spawn_child(monkeypatch):
    processes = []

    def spawn(_argv, **kwargs):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
        processes.append(process)
        return process

    backend = AlsaAudioBackend(popen_factory=spawn)
    monkeypatch.setattr(backend, "availability", lambda: (True, ""))
    cancel = threading.Event()
    cancel.set()
    try:
        backend.play_pcm([b"\0\0" * 160], cancel)
        assert processes == []
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=3)
