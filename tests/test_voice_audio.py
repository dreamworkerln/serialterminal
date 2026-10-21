from serialterminal.voice_audio import AlsaAudioBackend


def test_alsa_backend_reports_missing_tools(monkeypatch):
    monkeypatch.setattr("serialterminal.voice_audio.shutil.which", lambda name: None)
    available, reason = AlsaAudioBackend().availability()
    assert available is False
    assert "arecord" in reason and "aplay" in reason


def test_alsa_audio_argv_is_raw_s16le_8k_mono():
    assert AlsaAudioBackend._audio_argv("arecord") == [
        "arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", "8000", "-c", "1"
    ]
    assert AlsaAudioBackend._audio_argv("aplay")[0] == "aplay"


class _ChunkStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.closed = False

    def read(self, _size=-1):
        if self._chunks:
            return self._chunks.pop(0)
        return b""

    def close(self):
        self.closed = True


class _FakeCaptureProcess:
    def __init__(self, *, wait_results):
        import io
        self.stdout = _ChunkStream([b"ab", b"cdef"])
        self.stderr = io.BytesIO(b"")
        self._wait_results = list(wait_results)
        self.signals = []
        self.terminated = 0
        self.killed = 0

    def poll(self):
        return None

    def send_signal(self, value):
        self.signals.append(value)

    def wait(self, timeout=None):
        import subprocess
        value = self._wait_results.pop(0)
        if value == "timeout":
            raise subprocess.TimeoutExpired("arecord", timeout)
        return value

    def terminate(self):
        self.terminated += 1

    def kill(self):
        self.killed += 1


def test_alsa_capture_preserves_fragmented_stdout_and_expected_stop():
    import signal
    from serialterminal.voice_audio import _AlsaCapture

    process = _FakeCaptureProcess(wait_results=[0, 0])
    capture = _AlsaCapture(process, stop_timeout=0.01, kill_timeout=0.01)
    try:
        assert capture.read(timeout=0.5) == b"ab"
        assert capture.read(timeout=0.5) == b"cdef"
        try:
            capture.read(timeout=0.5)
        except EOFError:
            pass
        else:
            raise AssertionError("EOF not observed")
        capture.request_stop()
        result = capture.finish()
        assert result.returncode == 0
        assert result.requested_stop is True
        assert process.signals == [signal.SIGINT]
    finally:
        capture.close()


def test_alsa_capture_bounded_terminate_then_kill_fallback():
    from serialterminal.voice_audio import _AlsaCapture

    process = _FakeCaptureProcess(wait_results=["timeout", "timeout", 0, 0])
    capture = _AlsaCapture(process, stop_timeout=0.01, kill_timeout=0.01)
    try:
        capture.request_stop()
        result = capture.finish()
        assert result.returncode == 0
        assert process.terminated == 1
        assert process.killed == 1
    finally:
        capture.close()
