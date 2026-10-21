import json
from pathlib import Path
import threading
import time

from serialterminal.file_transfer import FileTransferError
from serialterminal.voice_service import VoiceMessageService


def wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timeout")


class FakeCodec:
    mode = 0
    samples_per_frame = 160
    bits_per_frame = 64
    bytes_per_frame = 8
    pcm_bytes_per_frame = 320

    def __init__(self, library):
        self.library = library

    def encode(self, pcm):
        assert len(pcm) == 320
        return bytes([pcm[0]]) * 8

    def decode(self, bits):
        assert len(bits) == 8
        return bytes([bits[0], 0]) * 160

    def close(self):
        pass


class FakeLibrary:
    version_major = 1
    version_minor = 2

    def __init__(self, path):
        self.path = path

    def load(self):
        return self

    def create(self, mode=0):
        assert mode == 0
        return FakeCodec(self)


class FakeCapture:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.stop = False
        self.closed = False

    def read(self, timeout=0.1):
        if self.chunks:
            return self.chunks.pop(0)
        if self.stop:
            raise EOFError
        time.sleep(min(timeout, 0.01))
        return None

    def request_stop(self):
        self.stop = True

    def finish(self):
        from serialterminal.voice_audio import CaptureResult
        return CaptureResult(0, self.stop, "")

    def close(self):
        self.closed = True
        self.stop = True


class FakeAudio:
    def __init__(self, chunks=None):
        self.chunks = chunks or [b"\x01\x00" * 160]
        self.played = []
        self.play_started = threading.Event()
        self.play_release = threading.Event()
        self.block_playback = False

    def availability(self):
        return True, ""

    def start_capture(self):
        return FakeCapture(self.chunks)

    def play_pcm(self, chunks, cancel_event):
        self.play_started.set()
        data = b"".join(chunks)
        if self.block_playback:
            while not self.play_release.wait(0.01):
                if cancel_event.is_set():
                    return
        self.played.append(data)

    def stop_playback(self):
        self.play_release.set()


class FakeManager:
    def __init__(self, receive_dir, mode="normal"):
        self.receive_dir = Path(receive_dir)
        self.receive_dir.mkdir(parents=True, exist_ok=True)
        self.busy = False
        self.mode = mode
        self.started = threading.Event()
        self.release_start = threading.Event()
        self.service = None
        self.snapshot = None

    def display_snapshot(self):
        return self.snapshot

    def start_send(self, path):
        self.started.set()
        if self.mode == "busy":
            raise FileTransferError("file_transfer_busy", "busy", phase="preparing")
        if self.mode == "blocked":
            self.release_start.wait(3.0)
        tx_id = "00000000000000aa"
        self.snapshot = {
            "transfer_id": tx_id,
            "direction": "TX",
            "filename": Path(path).name,
            "state": "sending",
        }
        if self.mode == "early-complete":
            event = {
                "transfer_id": tx_id,
                "direction": "TX",
                "filename": Path(path).name,
                "kind": "transfer_completed",
                "progress": {**self.snapshot, "state": "completed"},
            }
            self.snapshot = dict(event["progress"])
            self.service.on_ft1_event(event, self)
            return dict(self.snapshot)
        return dict(self.snapshot)


def make_service(tmp_path, manager, *, audio=None):
    sdk = tmp_path / "sdk"
    (sdk / "lib").mkdir(parents=True)
    (sdk / "manifest.json").write_text(json.dumps({"sdk_format": 1}))
    service = VoiceMessageService(
        codec2_sdk_dir=sdk,
        temp_dir=tmp_path / "voice-temp",
        audio_backend=audio or FakeAudio(),
        codec_library_factory=FakeLibrary,
        event_queue_size=8,
        playback_queue_size=2,
    )
    manager.service = service
    service.bind_manager(manager)
    return service


def record_and_stop(service):
    assert service.toggle_recording()
    wait_for(lambda: service.snapshot().state == "RECORDING")
    assert service.toggle_recording()


def test_voice_tx_early_terminal_before_start_send_return_cleans_matching_temp(tmp_path):
    manager = FakeManager(tmp_path / "rx", mode="early-complete")
    service = make_service(tmp_path, manager)
    try:
        record_and_stop(service)
        wait_for(lambda: manager.started.is_set())
        wait_for(lambda: service.snapshot().state == "IDLE")
        assert service.snapshot().retained_paths == ()
        assert list((tmp_path / "voice-temp").glob("*.stvoice.c2")) == []
    finally:
        service.close()


def test_voice_ft1_busy_preserves_finalized_file_as_ready(tmp_path):
    manager = FakeManager(tmp_path / "rx", mode="busy")
    service = make_service(tmp_path, manager)
    try:
        record_and_stop(service)
        wait_for(lambda: service.snapshot().state == "READY_FILE")
        snap = service.snapshot()
        assert len(snap.retained_paths) == 1
        retained = Path(snap.retained_paths[0])
        assert retained.exists()
        assert retained.read_bytes().startswith(bytes.fromhex("c0dec201020000"))
        assert any("F5 retry" in message for message in service.drain_notifications())
    finally:
        service.close()


def test_rx_voice_waits_for_capture_then_playback_blocks_new_f12(tmp_path):
    audio = FakeAudio()
    audio.block_playback = True
    manager = FakeManager(tmp_path / "rx", mode="busy")
    service = make_service(tmp_path, manager, audio=audio)
    try:
        assert service.toggle_recording()
        wait_for(lambda: service.snapshot().state == "RECORDING")
        received = manager.receive_dir / "voice-remote.stvoice.c2"
        received.write_bytes(bytes.fromhex("c0dec201020000") + b"\x05" * 8)
        event = {
            "transfer_id": "00000000000000bb",
            "direction": "RX",
            "filename": "voice-remote.stvoice.c2",
            "kind": "transfer_completed",
            "progress": {
                "transfer_id": "00000000000000bb",
                "direction": "RX",
                "filename": "voice-remote.stvoice.c2",
                "state": "completed",
                "final_path": str(received),
            },
        }
        manager.snapshot = dict(event["progress"])
        service.on_ft1_event(event, manager)
        time.sleep(0.1)
        assert not audio.play_started.is_set()
        assert service.toggle_recording()
        wait_for(lambda: audio.play_started.is_set())
        assert service.toggle_recording() is False
        assert any("playback is active" in item for item in service.drain_notifications())
        audio.play_release.set()
        wait_for(lambda: not service.snapshot().playback_active)
        assert audio.played and len(audio.played[0]) == 320
    finally:
        audio.play_release.set()
        service.close()


def test_duplicate_rx_completion_autoplays_once(tmp_path):
    audio = FakeAudio()
    manager = FakeManager(tmp_path / "rx")
    service = make_service(tmp_path, manager, audio=audio)
    try:
        received = manager.receive_dir / "v.stvoice.c2"
        received.write_bytes(bytes.fromhex("c0dec201020000") + b"\x09" * 8)
        event = {
            "transfer_id": "0000000000000001", "direction": "RX",
            "filename": "v.stvoice.c2", "kind": "transfer_completed",
            "progress": {"transfer_id": "0000000000000001", "direction": "RX",
                         "filename": "v.stvoice.c2", "state": "completed",
                         "final_path": str(received)},
        }
        manager.snapshot = dict(event["progress"])
        service.on_ft1_event(event, manager)
        service.on_ft1_event(event, manager)
        wait_for(lambda: len(audio.played) == 1)
        time.sleep(0.1)
        assert len(audio.played) == 1
        assert received.exists()
    finally:
        service.close()



def test_blocking_ft1_admission_runs_off_tui_and_shutdown_retains_file(tmp_path):
    manager = FakeManager(tmp_path / "rx", mode="blocked")
    service = make_service(tmp_path, manager)
    try:
        record_and_stop(service)
        wait_for(lambda: manager.started.is_set())
        wait_for(lambda: service.snapshot().state == "ADMITTING")
        started = time.monotonic()
        service.close()
        assert time.monotonic() - started < 2.0
        retained = service.snapshot().retained_paths
        assert len(retained) == 1 and Path(retained[0]).exists()
        manager.release_start.set()
        time.sleep(0.1)
        assert Path(retained[0]).exists()
    finally:
        manager.release_start.set()
        service.close()


def test_stale_terminal_from_detached_manager_cannot_delete_current_voice_file(tmp_path):
    manager = FakeManager(tmp_path / "rx")
    service = make_service(tmp_path, manager)
    try:
        manager.mode = "busy"
        record_and_stop(service)
        wait_for(lambda: service.snapshot().state == "READY_FILE")
        retained = Path(service.snapshot().retained_paths[0])
        service.detach_manager(manager)
        event = {
            "transfer_id": "00000000000000aa",
            "direction": "TX",
            "filename": retained.name,
            "kind": "transfer_completed",
            "progress": {"state": "completed"},
        }
        service.on_ft1_event(event, manager)
        time.sleep(0.1)
        assert retained.exists()
    finally:
        service.close()


def test_invalid_and_recursive_voice_rx_do_not_autoplay(tmp_path):
    audio = FakeAudio()
    manager = FakeManager(tmp_path / "rx")
    service = make_service(tmp_path, manager, audio=audio)
    try:
        bad = manager.receive_dir / "bad.stvoice.c2"
        bad.write_bytes(b"not codec2")
        event = {
            "transfer_id": "bad", "direction": "RX", "filename": bad.name,
            "kind": "transfer_completed",
            "progress": {"transfer_id": "bad", "direction": "RX", "filename": bad.name,
                         "state": "completed", "final_path": str(bad)},
        }
        manager.snapshot = dict(event["progress"])
        service.on_ft1_event(event, manager)
        time.sleep(0.1)
        assert not audio.played

        child = manager.receive_dir / "child.stvoice.c2"
        child.write_bytes(bytes.fromhex("c0dec201020000") + b"\x01" * 8)
        child_event = {
            "transfer_id": "child", "direction": "RX", "filename": child.name,
            "kind": "transfer_completed",
            "progress": {"transfer_id": "child", "direction": "RX", "filename": child.name,
                         "state": "completed", "final_path": str(child)},
        }
        manager.snapshot = {"transfer_id": "root", "direction": "RX", "state": "receiving"}
        service.on_ft1_event(child_event, manager)
        time.sleep(0.1)
        assert not audio.played
    finally:
        service.close()
