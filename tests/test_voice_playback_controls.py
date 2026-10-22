"""Отмена и прогресс playback без физических аудио/радиоустройств."""
import io
import subprocess
import sys
import threading
import time

import pytest

from serialterminal.voice_audio import AlsaAudioBackend
from test_voice_service import FakeAudio, FakeManager, make_service, wait_for


def receive(service, manager, ident, frames=50):
    path = manager.receive_dir / (ident + ".stvoice.c2")
    path.write_bytes(bytes.fromhex("c0dec201020000") + b"\x05" * (8 * frames))
    progress = dict(transfer_id=ident, direction="RX", filename=path.name,
                    state="completed", final_path=str(path))
    manager.snapshot = progress
    service.on_ft1_event(dict(kind="transfer_completed", progress=progress, **progress), manager)
    return path


def test_progress_follows_time_not_fast_decode_and_cancel_retains_files(tmp_path):
    audio, manager = FakeAudio(), FakeManager(tmp_path / "rx")
    audio.block_playback = True
    service = make_service(tmp_path, manager, audio=audio)
    try:
        path = receive(service, manager, "first")
        assert audio.play_started.wait(2)
        wait_for(lambda: service._playback_decoded_seconds >= 0.99)
        snap = service.snapshot()
        assert snap.playback_total_seconds == 1.0
        assert snap.playback_seconds < 0.5
        with service._lock:
            service._playback_started = time.monotonic() - 0.5
        assert 0.5 <= service.snapshot().playback_seconds < 0.8
        queued = receive(service, manager, "queued")
        wait_for(lambda: len(service._playback_queue) == 1)
        assert service.cancel_playback()
        assert service.snapshot().playback_cancelled
        assert not service._playback_queue
        wait_for(lambda: not service.snapshot().playback_active)
        assert path.exists() and queued.exists() and not audio.played
        messages = service.drain_notifications()
        assert not any("playback completed" in line or "playback failed" in line for line in messages)
        assert not service.cancel_playback()
        audio.block_playback = False
        future = receive(service, manager, "future")
        wait_for(lambda: len(audio.played) == 1)
        assert future.exists()
    finally:
        service.close()


def test_cancel_fences_rx_already_in_validation(tmp_path, monkeypatch):
    import serialterminal.voice_service as module
    audio, manager = FakeAudio(), FakeManager(tmp_path / "rx")
    audio.block_playback = True
    service = make_service(tmp_path, manager, audio=audio)
    entered, release = threading.Event(), threading.Event()
    original = module.validate_c2_file

    def validate(path, **kwargs):
        if path.name == "pending.stvoice.c2":
            entered.set()
            assert release.wait(3)
        return original(path, **kwargs)

    try:
        receive(service, manager, "playing")
        assert audio.play_started.wait(2)
        monkeypatch.setattr(module, "validate_c2_file", validate)
        pending = receive(service, manager, "pending")
        assert entered.wait(2)
        assert service.cancel_playback()
        release.set()
        wait_for(lambda: (service._manager_generation, "pending", "RX") in service._autoplay_seen)
        wait_for(lambda: not service.snapshot().playback_active)
        assert pending.exists() and not service._playback_queue and not audio.played
        audio.block_playback = False
        receive(service, manager, "future")
        wait_for(lambda: len(audio.played) == 1)
    finally:
        release.set()
        service.close()


@pytest.mark.parametrize("phase", ["blocked_write", "drain"])
def test_cancel_interrupts_real_child_pipe_or_drain_without_ui_wait(tmp_path, monkeypatch, phase):
    marker = tmp_path / "ready"
    processes, errors = [], []

    def spawn(_argv, **kwargs):
        read = "sys.stdin.buffer.read(); " if phase == "drain" else ""
        code = "import pathlib,sys,time; " + read + "pathlib.Path(sys.argv[1]).touch(); time.sleep(30)"
        process = subprocess.Popen([sys.executable, "-c", code, str(marker)], **kwargs)
        processes.append(process)
        return process

    backend = AlsaAudioBackend(popen_factory=spawn)
    monkeypatch.setattr(backend, "availability", lambda: (True, ""))
    cancel = threading.Event()

    def play():
        try:
            backend.play_pcm([b"a" * (4 * 1024 * 1024 if phase == "blocked_write" else 320)], cancel)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=play)
    thread.start()
    try:
        wait_for(marker.exists)
        cancel.set()
        thread.join(3)
        assert not thread.is_alive()
        assert processes[0].poll() is not None
        assert not errors
    finally:
        cancel.set()
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)
        thread.join(3)


def test_playback_preserves_partial_pipe_writes(monkeypatch):
    class Input:
        closed = False
        data = bytearray()

        def write(self, data):
            size = min(2, len(data))
            self.data.extend(data[:size])
            return size

        def close(self):
            self.closed = True

    class Process:
        stdin, stderr = Input(), io.BytesIO()

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    process = Process()
    backend = AlsaAudioBackend(popen_factory=lambda *args, **kwargs: process)
    monkeypatch.setattr(backend, "availability", lambda: (True, ""))
    backend.play_pcm([b"123456", b"789"], threading.Event())
    assert process.stdin.data == b"123456789"


def test_cancel_during_codec_startup_does_not_launch_audio(tmp_path):
    audio, manager = FakeAudio(), FakeManager(tmp_path / "rx")
    service = make_service(tmp_path, manager, audio=audio)
    entered, release = threading.Event(), threading.Event()
    original = service._library

    def delayed_library():
        entered.set()
        assert release.wait(3)
        return original()

    service._library = delayed_library
    try:
        path = receive(service, manager, "startup")
        assert entered.wait(2)
        assert service.cancel_playback()
        assert service.snapshot().playback_cancelled
        release.set()
        wait_for(lambda: not service.snapshot().playback_active)
        assert path.exists() and not audio.play_started.is_set()
    finally:
        release.set()
        service.close()
