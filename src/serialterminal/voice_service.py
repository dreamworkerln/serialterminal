from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import copy
import os
from pathlib import Path
import queue
import secrets
import tempfile
import threading
import time
from typing import Any, Callable

from .application_log import report_event, report_exception
from .file_transfer import FileTransferError, FileTransferManager
from .settings import DEFAULTS
from .voice_audio import AlsaAudioBackend, AudioBackend, VoiceAudioError
from .voice_codec import (
    C2FileEncoder,
    CODEC2_MODE_3200,
    Codec2Library,
    UnsupportedVoiceMode,
    VoiceCodecError,
    VoiceFormatError,
    iter_decoded_pcm,
    validate_c2_file,
)


_VOICE_LOCAL_STATES = {"STARTING", "RECORDING", "FINALIZING", "ADMITTING"}
_TERMINAL_FT_KINDS = {"transfer_completed", "transfer_failed", "transfer_cancelled"}


@dataclass(frozen=True)
class VoiceSnapshot:
    state: str
    recording_seconds: float
    ready_path: str | None
    playback_active: bool
    retained_paths: tuple[str, ...]


@dataclass
class _TxAttempt:
    job_id: str
    path: Path
    manager: FileTransferManager
    manager_generation: int
    tx_id: str | None = None
    early_terminal: list[dict[str, Any]] = field(default_factory=list)
    terminal_applied: bool = False


@dataclass(frozen=True)
class _FtEnvelope:
    manager: FileTransferManager
    manager_generation: int
    is_root: bool
    event: dict[str, Any]


@dataclass(frozen=True)
class _PlaybackRequest:
    identity: tuple[int, str, str]
    path: Path
    wire_filename: str


class VoiceMessageService:
    """Store-and-forward Codec2 voice workflow layered on public FT1 APIs."""

    def __init__(
        self,
        *,
        codec2_sdk_dir: str | Path | None,
        temp_dir: str | Path | None = None,
        audio_backend: AudioBackend | None = None,
        codec_library_factory: Callable[[str | Path], Codec2Library] = Codec2Library,
        event_queue_size: int | None = None,
        playback_queue_size: int | None = None,
    ) -> None:
        self.codec2_sdk_dir = None if codec2_sdk_dir is None else Path(codec2_sdk_dir).expanduser()
        self.temp_dir = None if temp_dir is None else Path(temp_dir).expanduser()
        self.audio_backend = AlsaAudioBackend() if audio_backend is None else audio_backend
        self._codec_library_factory = codec_library_factory
        self._codec_library: Codec2Library | None = None
        self._event_queue: queue.Queue[_FtEnvelope] = queue.Queue(
            maxsize=event_queue_size or DEFAULTS.voice.event_queue_size
        )
        self._playback_limit = playback_queue_size or DEFAULTS.voice.playback_queue_size
        self._playback_queue: deque[_PlaybackRequest] = deque()
        self._notifications: deque[str] = deque(maxlen=32)
        self._retained_paths: set[Path] = set()
        self._autoplay_seen: set[tuple[int, str, str]] = set()
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._state = "IDLE"
        self._record_started: float | None = None
        self._record_stop = threading.Event()
        self._capture_thread: threading.Thread | None = None
        self._capture_job_id: str | None = None
        self._capture_stream = None
        self._audio_mode: str | None = None
        self._playback_cancel = threading.Event()
        self._tx_attempts: dict[str, _TxAttempt] = {}
        self._manager: FileTransferManager | None = None
        self._manager_generation = 0
        self._overflow_manager: FileTransferManager | None = None
        self._closing = False
        self._worker_stop = threading.Event()
        self._event_worker = threading.Thread(
            target=self._event_loop,
            name="serialterminal-voice-events",
            daemon=True,
        )
        self._playback_worker = threading.Thread(
            target=self._playback_loop,
            name="serialterminal-voice-playback",
            daemon=True,
        )
        self._event_worker.start()
        self._playback_worker.start()

    def bind_manager(self, manager: FileTransferManager | None) -> None:
        with self._condition:
            if manager is self._manager:
                return
            self._manager = manager
            self._manager_generation += 1
            self._condition.notify_all()

    def detach_manager(self, manager: FileTransferManager | None) -> None:
        with self._condition:
            if manager is not None and manager is self._manager:
                self._manager = None
                self._manager_generation += 1
                self._condition.notify_all()

    def availability(self) -> tuple[bool, str]:
        with self._lock:
            manager = self._manager
            closing = self._closing
        if closing:
            return False, "voice service is shutting down"
        if manager is None:
            return False, "selected profile does not provide FT1/BINARY capability"
        if self.codec2_sdk_dir is None:
            return False, "configure --codec2-sdk-dir PATH"
        if not (self.codec2_sdk_dir / "manifest.json").is_file():
            return False, "configured Codec2 SDK tree has no manifest.json"
        available, reason = self.audio_backend.availability()
        if not available:
            return False, reason
        return True, ""

    def snapshot(self) -> VoiceSnapshot:
        with self._lock:
            seconds = 0.0
            if self._record_started is not None and self._state in {"RECORDING", "FINALIZING"}:
                seconds = max(0.0, time.monotonic() - self._record_started)
            ready = self._latest_retained_locked()
            return VoiceSnapshot(
                state=self._state,
                recording_seconds=seconds,
                ready_path=None if ready is None else str(ready),
                playback_active=self._audio_mode == "playback",
                retained_paths=tuple(sorted(str(path) for path in self._retained_paths)),
            )

    def local_operation_active(self) -> bool:
        with self._lock:
            return self._state in _VOICE_LOCAL_STATES

    def status_line(self) -> str | None:
        snap = self.snapshot()
        if snap.state == "STARTING":
            return "VOICE STARTING"
        if snap.state == "RECORDING":
            return f"VOICE REC {snap.recording_seconds:.1f}s · F12 send"
        if snap.state == "FINALIZING":
            return "VOICE FINALIZING"
        if snap.state == "ADMITTING":
            return "VOICE ADMITTING TO FT1"
        if snap.playback_active:
            return "VOICE PLAYBACK · F12 waits"
        if snap.state == "READY_FILE" and snap.ready_path:
            return f"VOICE READY {Path(snap.ready_path).name} · F5 retry"
        return None

    def drain_notifications(self) -> list[str]:
        with self._lock:
            result = list(self._notifications)
            self._notifications.clear()
            return result

    def _notify(self, text: str) -> None:
        with self._lock:
            self._notifications.append(text)
        report_event("VOICE " + text)

    def _latest_retained_locked(self) -> Path | None:
        def modified(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0

        return max(self._retained_paths, key=modified, default=None)

    def _library(self) -> Codec2Library:
        with self._lock:
            library = self._codec_library
            sdk_dir = self.codec2_sdk_dir
        if sdk_dir is None:
            raise VoiceCodecError("Codec2 SDK directory is not configured")
        if library is None:
            library = self._codec_library_factory(sdk_dir)
            library.load()
            with self._lock:
                if self._codec_library is None:
                    self._codec_library = library
                else:
                    library = self._codec_library
        return library

    def toggle_recording(self) -> bool:
        with self._condition:
            if self._closing:
                self._notifications.append("Voice unavailable: service is shutting down")
                return False
            if self._state == "RECORDING":
                self._state = "FINALIZING"
                self._record_stop.set()
                self._condition.notify_all()
                return True
            if self._state in {"STARTING", "FINALIZING", "ADMITTING"}:
                self._notifications.append("Voice operation is still finishing; wait for it to settle")
                return False
            if self._audio_mode == "playback":
                self._notifications.append("Voice playback is active; press F12 again after playback finishes")
                return False
            manager = self._manager
            if manager is None:
                self._notifications.append("Voice unavailable: selected profile has no FT1 capability")
                return False
            if manager.busy:
                self._notifications.append("Voice recording not started: FT1 is already busy")
                return False
        available, reason = self.availability()
        if not available:
            self._notify("Voice unavailable: " + reason)
            return False
        with self._condition:
            if self._state not in {"IDLE", "READY_FILE"} or self._audio_mode is not None:
                return False
            self._state = "STARTING"
            # Audio owner резервируется до загрузки SDK и открытия микрофона.
            self._audio_mode = "capture"
            self._record_stop = threading.Event()
            job_id = secrets.token_hex(8)
            self._capture_job_id = job_id
            self._capture_thread = threading.Thread(
                target=self._capture_worker,
                args=(job_id,),
                name=f"serialterminal-voice-capture-{job_id}",
                daemon=True,
            )
            self._capture_thread.start()
            self._condition.notify_all()
        return True

    def _voice_temp_root(self) -> Path:
        if self.temp_dir is not None:
            root = self.temp_dir
        else:
            root = Path(tempfile.gettempdir()) / "serialterminal-voice"
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _new_voice_name() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"voice-{stamp}-{secrets.token_hex(3)}.stvoice.c2"

    def _capture_worker(self, job_id: str) -> None:
        final_path: Path | None = None
        partial_path: Path | None = None
        capture = None
        codec = None
        stop_requested = False
        process_result = None
        try:
            library = self._library()
            codec = library.create(CODEC2_MODE_3200)
            final_path = self._voice_temp_root() / self._new_voice_name()
            partial_path = final_path.with_name(final_path.name + ".partial")
            capture = self.audio_backend.start_capture()
            with self._condition:
                if self._closing or self._capture_job_id != job_id:
                    raise VoiceAudioError("voice capture was cancelled before start")
                self._capture_stream = capture
                self._audio_mode = "capture"
                self._record_started = time.monotonic()
                self._state = "RECORDING"
                self._condition.notify_all()
            self._notify("Voice recording started; F12 stops and sends")
            with partial_path.open("xb") as output:
                writer = C2FileEncoder(output, codec)
                stop_deadline = None
                while True:
                    if self._record_stop.is_set() and not stop_requested:
                        stop_requested = True
                        capture.request_stop()
                        stop_deadline = time.monotonic() + (
                            DEFAULTS.voice.process_stop_timeout_s
                            + DEFAULTS.voice.process_kill_timeout_s
                            + 0.5
                        )
                    try:
                        chunk = capture.read(timeout=0.1)
                    except EOFError:
                        if not stop_requested:
                            raise VoiceAudioError("arecord exited before F12 stop")
                        break
                    if chunk:
                        writer.feed_pcm(chunk)
                    if stop_requested and stop_deadline is not None and time.monotonic() >= stop_deadline:
                        process_result = capture.finish()
                        # Process is now boundedly stopped; drain whatever the reader already captured.
                        drain_deadline = time.monotonic() + DEFAULTS.voice.process_kill_timeout_s + 0.5
                        while True:
                            try:
                                chunk = capture.read(timeout=0.1)
                            except EOFError:
                                break
                            if chunk:
                                writer.feed_pcm(chunk)
                                continue
                            if time.monotonic() >= drain_deadline:
                                raise VoiceAudioError("arecord stdout did not drain after bounded stop")
                        break
                if process_result is None:
                    process_result = capture.finish()
                if not process_result.graceful_stop:
                    raise VoiceAudioError(
                        f"audio capture did not stop gracefully (status {process_result.returncode})"
                        + (f": {process_result.stderr}" if process_result.stderr else "")
                    )
                with self._lock:
                    shutting_down = self._closing
                if shutting_down:
                    raise VoiceAudioError("voice capture stopped by SerialTerminal shutdown")
                frames = writer.finalize()
                if frames <= 0:
                    raise VoiceAudioError("empty voice recording was not sent")
                output.flush()
                os.fsync(output.fileno())
            os.replace(partial_path, final_path)
            partial_path = None
            validate_c2_file(
                final_path,
                expected_major=library.version_major,
                expected_minor=library.version_minor,
                expected_mode=codec.mode,
                frame_bytes=codec.bytes_per_frame,
            )
            with self._condition:
                self._audio_mode = None
                self._capture_stream = None
                self._record_started = None
                if self._closing:
                    self._retained_paths.add(final_path)
                    self._state = "CLOSED"
                    self._condition.notify_all()
                    return
                self._state = "ADMITTING"
                self._condition.notify_all()
            self._admit_finalized(job_id, final_path)
        except Exception as exc:
            report_exception(exc, "voice capture/finalize")
            if partial_path is not None:
                try:
                    partial_path.unlink(missing_ok=True)
                except OSError as cleanup:
                    report_exception(cleanup, "voice partial cleanup")
            with self._condition:
                self._audio_mode = None
                self._capture_stream = None
                self._record_started = None
                if self._capture_job_id == job_id:
                    self._capture_job_id = None
                if final_path is not None and final_path.exists():
                    self._retained_paths.add(final_path)
                    if not self._closing:
                        self._state = "READY_FILE"
                elif not self._closing:
                    self._state = "IDLE"
                else:
                    self._state = "CLOSED"
                self._condition.notify_all()
            self._notify(f"Voice recording failed: {type(exc).__name__}: {exc}")
        finally:
            if codec is not None:
                codec.close()
            if capture is not None:
                try:
                    capture.close()
                except Exception as exc:
                    report_exception(exc, "voice capture cleanup")
            with self._condition:
                if self._capture_thread is threading.current_thread():
                    self._capture_thread = None
                self._condition.notify_all()

    def _admit_finalized(self, job_id: str, path: Path) -> None:
        with self._condition:
            if self._closing:
                self._retained_paths.add(path)
                self._state = "CLOSED"
                self._capture_job_id = None
                self._condition.notify_all()
                return
            manager = self._manager
            generation = self._manager_generation
            if manager is None:
                self._retained_paths.add(path)
                self._state = "READY_FILE"
                self._capture_job_id = None
                self._notifications.append(f"Voice retained (no FT1 manager): {path}")
                return
            attempt = _TxAttempt(job_id, path, manager, generation)
            self._tx_attempts[job_id] = attempt
        try:
            result = manager.start_send(path)
        except FileTransferError as exc:
            with self._condition:
                if self._tx_attempts.get(job_id) is attempt:
                    self._tx_attempts.pop(job_id)
                self._retained_paths.add(path)
                self._capture_job_id = None
                if not self._closing:
                    self._state = "READY_FILE"
                self._condition.notify_all()
            self._notify(f"Voice retained for F5 retry: {exc.code}: {exc.message} | {path}")
            return
        except Exception as exc:
            report_exception(exc, "voice FT1 admission")
            with self._condition:
                if self._tx_attempts.get(job_id) is attempt:
                    self._tx_attempts.pop(job_id)
                self._retained_paths.add(path)
                self._capture_job_id = None
                if not self._closing:
                    self._state = "READY_FILE"
                self._condition.notify_all()
            self._notify(f"Voice retained after send-start failure: {exc} | {path}")
            return

        tx_id = str(result.get("transfer_id", ""))
        with self._condition:
            if self._closing:
                if self._tx_attempts.get(job_id) is attempt:
                    self._tx_attempts.pop(job_id)
                self._retained_paths.add(path)
                self._capture_job_id = None
                self._state = "CLOSED"
                self._condition.notify_all()
                return
            if self._tx_attempts.get(job_id) is not attempt:
                self._retained_paths.add(path)
                return
            attempt.tx_id = tx_id
            buffered = list(attempt.early_terminal)
            attempt.early_terminal.clear()
            for event in buffered:
                if event.get("transfer_id") == tx_id:
                    self._apply_tx_terminal_locked(attempt, event)
            if not attempt.terminal_applied and result.get("state") in {"completed", "failed", "cancelled"}:
                synthetic = {
                    "transfer_id": tx_id,
                    "direction": "TX",
                    "filename": result.get("filename", path.name),
                    "kind": "transfer_" + str(result["state"]),
                    "progress": dict(result),
                }
                self._apply_tx_terminal_locked(attempt, synthetic)
            if not attempt.terminal_applied:
                if not self._closing:
                    self._state = "IDLE"
                self._capture_job_id = None
            self._condition.notify_all()
        self._notify(f"Voice admitted to FT1 {tx_id}: {path.name}")

    def on_ft1_event(self, event: dict[str, Any], manager: FileTransferManager) -> None:
        try:
            root = manager.display_snapshot()
            is_root = root is None or root.get("transfer_id") == event.get("transfer_id")
        except Exception:
            is_root = False
        with self._lock:
            generation = self._manager_generation if manager is self._manager else -1
        envelope = _FtEnvelope(manager, generation, is_root, copy.deepcopy(event))
        try:
            self._event_queue.put_nowait(envelope)
        except queue.Full:
            with self._lock:
                self._overflow_manager = manager
                self._notifications.append("Voice FT1 event queue overflow; reconciling from manager snapshot")
            report_event("VOICE FT1 event queue overflow")

    def _event_loop(self) -> None:
        while not self._worker_stop.is_set():
            envelope = None
            try:
                envelope = self._event_queue.get(timeout=0.1)
            except queue.Empty:
                pass
            if envelope is not None:
                try:
                    self._handle_ft1_event(envelope)
                except Exception as exc:
                    report_exception(exc, "voice FT1 event dispatch")
            self._reconcile_overflow()

    def _handle_ft1_event(self, envelope: _FtEnvelope) -> None:
        event = envelope.event
        kind = event.get("kind")
        if kind not in _TERMINAL_FT_KINDS:
            return
        if event.get("direction") == "TX":
            with self._condition:
                # FT1 уже может освободиться для следующей записи, пока observer
                # ещё обрабатывает terminal предыдущей attempt.
                for attempt in list(self._tx_attempts.values()):
                    if attempt.manager is not envelope.manager:
                        continue
                    if attempt.manager_generation != envelope.manager_generation:
                        continue
                    if attempt.tx_id is None:
                        attempt.early_terminal.append(event)
                    elif event.get("transfer_id") == attempt.tx_id:
                        self._apply_tx_terminal_locked(attempt, event)
                self._condition.notify_all()
            return
        if event.get("direction") == "RX" and kind == "transfer_completed" and envelope.is_root:
            with self._lock:
                if (self._closing or envelope.manager is not self._manager
                        or envelope.manager_generation != self._manager_generation):
                    return
            self._handle_rx_completed(envelope)

    def _apply_tx_terminal_locked(self, attempt: _TxAttempt, event: dict[str, Any]) -> None:
        if attempt.terminal_applied or self._tx_attempts.get(attempt.job_id) is not attempt:
            return
        attempt.terminal_applied = True
        kind = str(event.get("kind", ""))
        path = attempt.path
        if self._closing:
            self._retained_paths.add(path)
            self._notifications.append(f"Voice terminal arrived during shutdown; retained: {path}")
            self._tx_attempts.pop(attempt.job_id)
            self._capture_job_id = None
            self._state = "CLOSED"
            return
        if kind == "transfer_completed":
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                self._retained_paths.add(path)
                self._notifications.append(f"Voice sent but local cleanup failed: {path}: {exc}")
            else:
                self._retained_paths.discard(path)
                self._notifications.append(f"Voice transfer completed: {path.name}")
        else:
            self._retained_paths.add(path)
            self._notifications.append(f"Voice transfer {kind.removeprefix('transfer_')}; retained: {path}")
        self._tx_attempts.pop(attempt.job_id)
        # Результат старого TX освобождает свой файл, но не owner новой записи.
        if self._capture_job_id in (None, attempt.job_id):
            self._capture_job_id = None
            if not self._closing:
                self._state = "READY_FILE" if path in self._retained_paths else "IDLE"

    def _reconcile_overflow(self) -> None:
        with self._lock:
            manager = self._overflow_manager
            self._overflow_manager = None
            generation = self._manager_generation if manager is self._manager else -1
        if manager is None or generation < 0:
            return
        try:
            snapshot = manager.display_snapshot()
        except Exception as exc:
            report_exception(exc, "voice FT1 overflow reconciliation")
            return
        snapshots = [] if snapshot is None else [snapshot]
        # display_snapshot уже может показывать более новый ROOT. Старые TX
        # восстанавливаем по public retained snapshots, а RX children не допускаем.
        retained = getattr(manager, "snapshots", None)
        if callable(retained):
            with self._lock:
                tx_ids = {attempt.tx_id for attempt in self._tx_attempts.values()
                          if attempt.manager is manager and attempt.manager_generation == generation}
            try:
                snapshots.extend(value for value in retained()
                                 if value.get("direction") == "TX" and value.get("transfer_id") in tx_ids)
            except Exception as exc:
                report_exception(exc, "voice TX overflow reconciliation")
        for value in snapshots:
            if value.get("state") not in {"completed", "failed", "cancelled"}:
                continue
            event = {
                "transfer_id": value.get("transfer_id"),
                "direction": value.get("direction"),
                "filename": value.get("filename"),
                "kind": "transfer_" + str(value["state"]),
                "progress": dict(value),
            }
            self._handle_ft1_event(_FtEnvelope(manager, generation, value is snapshot, event))

    def _handle_rx_completed(self, envelope: _FtEnvelope) -> None:
        event = envelope.event
        filename = str(event.get("filename", ""))
        if not filename.lower().endswith(".stvoice.c2"):
            return
        progress = event.get("progress")
        if not isinstance(progress, dict):
            return
        path_text = progress.get("final_path")
        if not isinstance(path_text, str):
            self._notify("Voice RX completion has no durable final_path; autoplay skipped")
            return
        path = Path(path_text)
        try:
            receive_root = envelope.manager.receive_dir.resolve()
            if path.is_symlink():
                raise VoiceFormatError("voice final_path must not be a symlink")
            resolved = path.resolve(strict=True)
            if resolved.parent != receive_root:
                raise VoiceFormatError("voice final_path is outside direct FT1 publication directory")
            validate_c2_file(resolved)
        except UnsupportedVoiceMode as exc:
            self._notify(f"Voice file retained but mode is unsupported: {exc} | {path}")
            return
        except (OSError, VoiceFormatError) as exc:
            self._notify(f"Received .stvoice.c2 is not playable: {exc} | {path}")
            return
        identity = (envelope.manager_generation, str(event.get("transfer_id")), "RX")
        with self._condition:
            # Файловая проверка шла без lock: за это время session могла смениться.
            if (self._closing or envelope.manager is not self._manager
                    or envelope.manager_generation != self._manager_generation):
                return
            if identity in self._autoplay_seen:
                return
            self._autoplay_seen.add(identity)
            if len(self._playback_queue) >= self._playback_limit:
                self._notifications.append(f"Voice autoplay queue full; retained for manual replay: {resolved}")
                return
            self._playback_queue.append(_PlaybackRequest(identity, resolved, filename))
            self._condition.notify_all()
        self._notify(f"Voice received and queued for playback: {resolved}")

    def _playback_loop(self) -> None:
        while not self._worker_stop.is_set():
            with self._condition:
                ready = self._condition.wait_for(
                    lambda: self._worker_stop.is_set()
                    or (
                        not self._closing
                        and self._playback_queue
                        and self._audio_mode is None
                        and self._state not in {"STARTING", "RECORDING", "FINALIZING"}
                    ),
                    timeout=0.2,
                )
                if self._worker_stop.is_set():
                    return
                if not ready:
                    continue
                request = self._playback_queue.popleft()
                self._audio_mode = "playback"
                self._playback_cancel = threading.Event()
            try:
                library = self._library()
                codec = library.create(CODEC2_MODE_3200)
                try:
                    chunks = iter_decoded_pcm(request.path, codec)
                    self.audio_backend.play_pcm(chunks, self._playback_cancel)
                finally:
                    codec.close()
                self._notify(f"Voice playback completed: {request.path}")
            except Exception as exc:
                report_exception(exc, "voice playback")
                self._notify(f"Voice playback failed; file retained: {exc} | {request.path}")
            finally:
                with self._condition:
                    self._audio_mode = None
                    self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            if self._closing:
                return
            closing_state = self._state
            self._closing = True
            self._record_stop.set()
            self._playback_cancel.set()
            capture = self._capture_stream
            self._condition.notify_all()
        if capture is not None:
            try:
                capture.request_stop()
            except Exception as exc:
                report_exception(exc, "voice capture shutdown request")
        try:
            self.audio_backend.stop_playback()
        except Exception as exc:
            report_exception(exc, "voice playback shutdown")
        thread = self._capture_thread
        if thread is not None and thread is not threading.current_thread():
            if closing_state == "ADMITTING":
                # start_send() may be inside its bounded admission fence. Do not hold
                # terminal shutdown on that call; late return is retention-only.
                thread.join(timeout=0.25)
            else:
                thread.join(
                    timeout=(
                        DEFAULTS.voice.process_stop_timeout_s
                        + DEFAULTS.voice.process_kill_timeout_s
                        + 1.0
                    )
                )
        with self._condition:
            for attempt in self._tx_attempts.values():
                if attempt.path.exists():
                    self._retained_paths.add(attempt.path)
            self._state = "CLOSED"
            self._condition.notify_all()
        self._worker_stop.set()
        with self._condition:
            self._condition.notify_all()
        self._event_worker.join(timeout=0.5)
        self._playback_worker.join(timeout=0.5)
        retained = self.snapshot().retained_paths
        if retained:
            self._notify("Voice files retained on shutdown: " + ", ".join(retained))
