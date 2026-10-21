from __future__ import annotations

from dataclasses import dataclass
import queue
import shutil
import signal
import subprocess
import sys
import threading
from typing import Iterable, Protocol

from .application_log import report_exception
from .settings import DEFAULTS


class VoiceAudioError(RuntimeError):
    pass


class CaptureStream(Protocol):
    def read(self, timeout: float = 0.1) -> bytes | None:
        ...

    def request_stop(self) -> None:
        ...

    def finish(self) -> "CaptureResult":
        ...

    def close(self) -> None:
        ...


class AudioBackend(Protocol):
    def availability(self) -> tuple[bool, str]:
        ...

    def start_capture(self) -> CaptureStream:
        ...

    def play_pcm(self, chunks: Iterable[bytes], cancel_event: threading.Event) -> None:
        ...

    def stop_playback(self) -> None:
        ...


@dataclass(frozen=True)
class CaptureResult:
    returncode: int
    requested_stop: bool
    stderr: str
    forced_stop: bool = False

    @property
    def graceful_stop(self) -> bool:
        return (self.requested_stop and not self.forced_stop
                and self.returncode in (0, -signal.SIGINT))


_EOF = object()


class _StderrDrain:
    def __init__(self, stream, *, limit: int = 8192) -> None:
        self.stream = stream
        self.limit = limit
        self._data = bytearray()
        self._thread = threading.Thread(target=self._run, name="serialterminal-voice-stderr", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        if self.stream is None:
            return
        while True:
            chunk = self.stream.read(1024)
            if not chunk:
                return
            if len(self._data) < self.limit:
                self._data.extend(chunk[: self.limit - len(self._data)])

    def text(self) -> str:
        self._thread.join(timeout=0.2)
        return bytes(self._data).decode("utf-8", errors="replace").strip()


class _AlsaCapture:
    def __init__(self, process: subprocess.Popen, *, stop_timeout: float, kill_timeout: float) -> None:
        self.process = process
        self.stop_timeout = stop_timeout
        self.kill_timeout = kill_timeout
        self._chunks: queue.Queue[bytes | object] = queue.Queue(maxsize=32)
        self._drop = threading.Event()
        self._requested_stop = False
        self._forced_stop = False
        self._stop_lock = threading.Lock()
        self._stderr = _StderrDrain(process.stderr)
        self._reader = threading.Thread(
            target=self._read_stdout,
            name="serialterminal-voice-capture-reader",
            daemon=True,
        )
        self._reader.start()

    def _put(self, item: bytes | object) -> None:
        while not self._drop.is_set():
            try:
                self._chunks.put(item, timeout=0.1)
                return
            except queue.Full:
                continue

    def _read_stdout(self) -> None:
        try:
            if self.process.stdout is not None:
                while True:
                    chunk = self.process.stdout.read(4096)
                    if not chunk:
                        break
                    self._put(bytes(chunk))
        finally:
            self._put(_EOF)

    def read(self, timeout: float = 0.1) -> bytes | None:
        try:
            item = self._chunks.get(timeout=timeout)
        except queue.Empty:
            return None
        if item is _EOF:
            # Keep EOF observable for a second read by a cleanup path.
            try:
                self._chunks.put_nowait(_EOF)
            except queue.Full:
                pass
            raise EOFError
        return item  # type: ignore[return-value]

    def request_stop(self) -> None:
        with self._stop_lock:
            if self._requested_stop:
                return
            if self.process.poll() is None:
                try:
                    self.process.send_signal(signal.SIGINT)
                    self._requested_stop = True
                except ProcessLookupError:
                    pass

    def _wait_bounded(self) -> int:
        try:
            return self.process.wait(timeout=self.stop_timeout)
        except subprocess.TimeoutExpired:
            self._forced_stop = True
            try:
                self.process.terminate()
            except ProcessLookupError:
                pass
        try:
            return self.process.wait(timeout=self.kill_timeout)
        except subprocess.TimeoutExpired:
            try:
                self.process.kill()
            except ProcessLookupError:
                pass
            return self.process.wait(timeout=self.kill_timeout)

    def finish(self) -> CaptureResult:
        return CaptureResult(
            returncode=self._wait_bounded(),
            requested_stop=self._requested_stop,
            stderr=self._stderr.text(),
            forced_stop=self._forced_stop,
        )

    def close(self) -> None:
        self.request_stop()
        try:
            self._wait_bounded()
        finally:
            self._drop.set()
            self._reader.join(timeout=0.2)
            for stream in (self.process.stdout, self.process.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except OSError:
                    pass


class AlsaAudioBackend:
    def __init__(self, *, popen_factory=subprocess.Popen) -> None:
        self._popen_factory = popen_factory
        self._playback_lock = threading.Lock()
        self._playback_process: subprocess.Popen | None = None

    def availability(self) -> tuple[bool, str]:
        missing = [name for name in ("arecord", "aplay") if shutil.which(name) is None]
        if missing:
            return False, "missing ALSA tool(s): " + ", ".join(missing)
        return True, ""

    @staticmethod
    def _audio_argv(tool: str) -> list[str]:
        return [tool, "-q", "-t", "raw", "-f", "S16_LE", "-r", "8000", "-c", "1"]

    def start_capture(self) -> _AlsaCapture:
        available, reason = self.availability()
        if not available:
            raise VoiceAudioError(reason)
        process = self._popen_factory(
            self._audio_argv("arecord"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        return _AlsaCapture(
            process,
            stop_timeout=DEFAULTS.voice.process_stop_timeout_s,
            kill_timeout=DEFAULTS.voice.process_kill_timeout_s,
        )

    def play_pcm(self, chunks: Iterable[bytes], cancel_event: threading.Event) -> None:
        available, reason = self.availability()
        if not available:
            raise VoiceAudioError(reason)
        process = self._popen_factory(
            self._audio_argv("aplay"),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        with self._playback_lock:
            self._playback_process = process
        cancelled = False
        stderr = None
        try:
            stderr = _StderrDrain(process.stderr)
            if process.stdin is None:
                raise VoiceAudioError("aplay stdin is unavailable")
            for chunk in chunks:
                if cancel_event.is_set():
                    cancelled = True
                    break
                process.stdin.write(chunk)
            try:
                process.stdin.close()
            except (BrokenPipeError, OSError):
                if not cancel_event.is_set():
                    raise
            if cancelled or cancel_event.is_set():
                self._terminate_playback(process)
            else:
                try:
                    returncode = process.wait(timeout=DEFAULTS.voice.playback_finish_timeout_s)
                except subprocess.TimeoutExpired as exc:
                    self._terminate_playback(process)
                    raise VoiceAudioError("aplay did not finish within bounded playback timeout") from exc
                if returncode != 0:
                    detail = stderr.text()
                    raise VoiceAudioError(
                        f"aplay exited with status {returncode}" + (f": {detail}" if detail else "")
                    )
        except (BrokenPipeError, OSError) as exc:
            detail = "" if stderr is None else stderr.text()
            raise VoiceAudioError(
                f"aplay stream failed: {exc}" + (f": {detail}" if detail else "")
            ) from exc
        finally:
            # Decoder/iterator тоже может завершиться с ошибкой после Popen.
            # Ownership сохраняется до bounded stop/reap; cleanup не скрывает
            # первоначальную ошибку stream/decode.
            original_error = sys.exc_info()[1]
            reaped = False
            try:
                self._terminate_playback(process)
                reaped = True
            except Exception as cleanup:
                if original_error is None:
                    raise
                report_exception(cleanup, "voice playback cleanup")
            finally:
                with self._playback_lock:
                    if self._playback_process is process and reaped:
                        self._playback_process = None
                for stream in (process.stdin, process.stderr):
                    try:
                        if stream is not None and not stream.closed:
                            stream.close()
                    except OSError:
                        pass

    def _terminate_playback(self, process: subprocess.Popen) -> None:
        if process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=DEFAULTS.voice.process_stop_timeout_s)
            return
        except subprocess.TimeoutExpired:
            pass
        if process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=DEFAULTS.voice.process_kill_timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise VoiceAudioError("aplay could not be stopped") from exc

    def stop_playback(self) -> None:
        with self._playback_lock:
            process = self._playback_process
        if process is not None:
            self._terminate_playback(process)
