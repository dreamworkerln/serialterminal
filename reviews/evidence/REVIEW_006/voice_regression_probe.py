from __future__ import annotations
import importlib.util
import json
import pathlib
import os
import subprocess
import sys
import tempfile
import threading
import time

ROOT = pathlib.Path(os.environ.get("ST_REVIEW_REPO", json.loads((pathlib.Path(__file__).parent / "checkpoint.json").read_text())["repository"]))
sys.path.insert(0, str(ROOT / "tests"))
spec = importlib.util.spec_from_file_location("voice_review_fakes", ROOT / "tests/test_voice_service.py")
fakes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fakes)
from serialterminal.voice_audio import CaptureResult, AlsaAudioBackend
from serialterminal.voice_codec import VoiceCodecError


def rx_event(manager, ident="00000000000000bb"):
    path = manager.receive_dir / "incoming.stvoice.c2"
    path.write_bytes(bytes.fromhex("c0dec201020000") + b"\x09" * 8)
    progress = {"transfer_id": ident, "direction": "RX", "filename": path.name,
                "state": "completed", "final_path": str(path)}
    manager.snapshot = progress
    return {"transfer_id": ident, "direction": "RX", "filename": path.name,
            "kind": "transfer_completed", "progress": dict(progress)}


def stale_tx_clobbers_recording(root):
    from serialterminal.file_transfer import FileTransferManager
    from test_file_transfer_core import _PairBinaryTransport
    left, right = _PairBinaryTransport(), _PairBinaryTransport()
    left.peer, right.peer = right, left
    first_send, gate_entered, release = threading.Event(), threading.Event(), threading.Event()
    service = None
    def sink(event):
        if event.get("direction") == "TX" and event.get("kind") == "binary_send_start":
            assert first_send.wait(2)
        if service is not None:
            service.on_ft1_event(event, manager)
    manager = FileTransferManager(left, receive_dir=root / "left-rx", event_sink=sink)
    peer = FileTransferManager(right, receive_dir=root / "right-rx")
    service = fakes.make_service(root, manager)
    original = service._handle_ft1_event
    def gated(envelope):
        if (envelope.event.get("direction") == "TX"
                and envelope.event.get("kind") == "transfer_completed"):
            gate_entered.set()
            assert release.wait(2)
        return original(envelope)
    try:
        service._handle_ft1_event = gated
        fakes.record_and_stop(service)
        fakes.wait_for(lambda: service.snapshot().state == "IDLE" and service._tx_attempt is not None)
        first_send.set()
        assert gate_entered.wait(2)
        fakes.wait_for(lambda: not manager.busy)
        assert manager.display_snapshot()["state"] == "completed"
        assert service.toggle_recording()
        fakes.wait_for(lambda: service.snapshot().state == "RECORDING")
        before = service.snapshot().state
        capture = service._capture_stream
        release.set()
        fakes.wait_for(lambda: service.snapshot().state == "IDLE")
        stopped = service.toggle_recording()
        return {"real_FT1_sender_completed": manager.display_snapshot()["state"] == "completed",
                "real_FT1_receiver_completed": peer.display_snapshot()["state"] == "completed",
                "state_before_old_terminal": before, "state_after_old_terminal": service.snapshot().state,
                "capture_still_open": not capture.closed, "record_stop_requested": service._record_stop.is_set(),
                "F12_can_stop_capture": stopped,
                "defect_reproduced": not stopped and not capture.closed and not service._record_stop.is_set()}
    finally:
        first_send.set()
        release.set()
        service.close()
        manager.close()
        peer.close()


def playback_during_starting(root):
    class DelayedAudio(fakes.FakeAudio):
        def __init__(self):
            super().__init__()
            self.entered, self.release = threading.Event(), threading.Event()
            self.block_playback = True
        def start_capture(self):
            self.entered.set()
            assert self.release.wait(2)
            return super().start_capture()
    audio = DelayedAudio()
    manager = fakes.FakeManager(root / "rx")
    service = fakes.make_service(root, manager, audio=audio)
    try:
        assert service.toggle_recording() and audio.entered.wait(1)
        assert service.snapshot().state == "STARTING"
        service.on_ft1_event(rx_event(manager), manager)
        assert audio.play_started.wait(1)
        started_state = service.snapshot().state
        audio.release.set()
        fakes.wait_for(lambda: service.snapshot().state == "RECORDING")
        return {"playback_started_in_state": started_state, "state_after_capture_start": service.snapshot().state,
                "playback_still_running": not audio.play_release.is_set(),
                "capture_open": not service._capture_stream.closed,
                "defect_reproduced": started_state == "STARTING" and not audio.play_release.is_set()}
    finally:
        audio.release.set()
        audio.play_release.set()
        service.close()


def forced_kill_is_auto_sent(root):
    class KilledCapture(fakes.FakeCapture):
        def finish(self):
            return CaptureResult(-9, True, "forced kill")
    class KilledAudio(fakes.FakeAudio):
        def start_capture(self):
            return KilledCapture(self.chunks)
    manager = fakes.FakeManager(root / "rx")
    service = fakes.make_service(root, manager, audio=KilledAudio())
    try:
        fakes.record_and_stop(service)
        fakes.wait_for(lambda: manager.started.is_set())
        fakes.wait_for(lambda: service.snapshot().state == "IDLE")
        return {"capture_returncode": -9, "FT1_send_started": manager.started.is_set(),
                "terminal_state": service.snapshot().state, "defect_reproduced": manager.started.is_set()}
    finally:
        service.close()


def stale_rx_after_manager_replacement(root):
    audio = fakes.FakeAudio()
    old = fakes.FakeManager(root / "old-rx")
    new = fakes.FakeManager(root / "new-rx")
    service = fakes.make_service(root, old, audio=audio)
    try:
        event = rx_event(old)
        service.detach_manager(old)
        service.bind_manager(new)
        service.on_ft1_event(event, old)
        fakes.wait_for(lambda: len(audio.played) == 1)
        return {"current_manager_replaced": service._manager is new, "old_RX_playbacks": len(audio.played),
                "defect_reproduced": len(audio.played) == 1}
    finally:
        service.close()


def playback_child_survives_decoder_failure(root):
    processes = []
    def spawn(_argv, **kwargs):
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(15)"], **kwargs)
        processes.append(p)
        return p
    backend = AlsaAudioBackend(popen_factory=spawn)
    backend.availability = lambda: (True, "")
    def broken_decode():
        raise VoiceCodecError("injected decode failure")
        yield b""
    try:
        try:
            backend.play_pcm(broken_decode(), threading.Event())
        except VoiceCodecError:
            pass
        p = processes[0]
        alive_after_error = p.poll() is None
        backend.stop_playback()
        alive_after_stop = p.poll() is None
        return {"child_alive_after_decode_error": alive_after_error,
                "child_alive_after_stop_playback": alive_after_stop,
                "backend_lost_process_handle": backend._playback_process is None,
                "defect_reproduced": alive_after_error and alive_after_stop}
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
            p.wait(timeout=2)


PROBES = [stale_tx_clobbers_recording, playback_during_starting, forced_kill_is_auto_sent,
          stale_rx_after_manager_replacement, playback_child_survives_decoder_failure]
if __name__ == "__main__":
    results = {}
    for probe in PROBES:
        with tempfile.TemporaryDirectory(prefix="voice-review-probe-") as temporary:
            results[probe.__name__] = probe(pathlib.Path(temporary))
    target = pathlib.Path(__file__).with_name("probe-results.json")
    target.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(results, ensure_ascii=False))
    assert all(row["defect_reproduced"] for row in results.values())
