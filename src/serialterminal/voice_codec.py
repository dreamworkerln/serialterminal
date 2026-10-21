from __future__ import annotations

import ctypes
from dataclasses import dataclass
import json
import platform
from pathlib import Path
import struct
import threading
from typing import BinaryIO, Iterator


C2_MAGIC = b"\xc0\xde\xc2"
C2_HEADER_SIZE = 7
CODEC2_MODE_3200 = 0
CODEC2_3200_SAMPLES_PER_FRAME = 160
CODEC2_3200_BITS_PER_FRAME = 64
CODEC2_3200_BYTES_PER_FRAME = 8
CODEC2_SAMPLE_RATE = 8000
CODEC2_SAMPLE_BYTES = 2
EXPECTED_CODEC2_UPSTREAM = "310777b1c6f1af0bc7c72f5b32f80f6fd9136962"
EXPECTED_CODEC2_VERSION = "1.2.0"


class VoiceCodecError(RuntimeError):
    pass


class VoiceFormatError(VoiceCodecError):
    pass


class UnsupportedVoiceMode(VoiceFormatError):
    pass


@dataclass(frozen=True)
class C2Header:
    version_major: int
    version_minor: int
    mode: int
    flags: int

    def to_bytes(self) -> bytes:
        values = (self.version_major, self.version_minor, self.mode, self.flags)
        if any(value < 0 or value > 255 for value in values):
            raise VoiceFormatError("Codec2 header fields must fit one byte")
        return C2_MAGIC + bytes(values)


def parse_c2_header(data: bytes) -> C2Header:
    if len(data) != C2_HEADER_SIZE:
        raise VoiceFormatError("truncated Codec2 header")
    if data[:3] != C2_MAGIC:
        raise VoiceFormatError("invalid Codec2 magic")
    return C2Header(
        version_major=data[3],
        version_minor=data[4],
        mode=data[5],
        flags=data[6],
    )


def _runtime_platform() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux" and machine in {"x86_64", "amd64"}:
        return "linux-x86_64"
    return f"{system}-{machine}"


def _safe_child(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise VoiceCodecError("Codec2 library resolves outside configured SDK tree") from exc
    return resolved


class Codec2Library:
    """Pinned codec2-sdk loader. It never falls back to a system libcodec2."""

    def __init__(self, sdk_dir: str | Path, *, cdll_factory=ctypes.CDLL) -> None:
        self.sdk_dir = Path(sdk_dir).expanduser()
        self._cdll_factory = cdll_factory
        self._lock = threading.Lock()
        self._lib = None
        self._manifest: dict | None = None
        self.version_major = 0
        self.version_minor = 0

    @property
    def manifest(self) -> dict:
        if self._manifest is None:
            raise VoiceCodecError("Codec2 SDK has not been loaded")
        return dict(self._manifest)

    def _read_manifest(self) -> dict:
        path = self.sdk_dir / "manifest.json"
        try:
            raw = path.read_text(encoding="utf-8")
            value = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise VoiceCodecError(f"cannot read Codec2 SDK manifest: {exc}") from exc
        if not isinstance(value, dict) or value.get("sdk_format") != 1:
            raise VoiceCodecError("unsupported Codec2 SDK manifest format")
        if value.get("platform") != _runtime_platform():
            raise VoiceCodecError(
                f"Codec2 SDK platform mismatch: {value.get('platform')!r} != {_runtime_platform()!r}"
            )
        build = value.get("build")
        if not isinstance(build, dict) or build.get("shared_library") is not True:
            raise VoiceCodecError("Codec2 SDK is not a shared-library build")
        upstream = value.get("upstream")
        if not isinstance(upstream, dict):
            raise VoiceCodecError("Codec2 SDK manifest has no upstream provenance")
        if upstream.get("commit") != EXPECTED_CODEC2_UPSTREAM:
            raise VoiceCodecError("Codec2 SDK upstream commit does not match pinned integration checkpoint")
        if upstream.get("codec2_version") != EXPECTED_CODEC2_VERSION:
            raise VoiceCodecError("Codec2 SDK version does not match pinned integration checkpoint")
        return value

    def _library_path(self) -> Path:
        lib_dir = self.sdk_dir / "lib"
        candidates = [lib_dir / "libcodec2.so", *sorted(lib_dir.glob("libcodec2.so.*"))]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return _safe_child(self.sdk_dir, candidate)
        raise VoiceCodecError("configured Codec2 SDK tree has no lib/libcodec2.so")

    @staticmethod
    def _bind(lib) -> None:
        lib.codec2_create.argtypes = [ctypes.c_int]
        lib.codec2_create.restype = ctypes.c_void_p
        lib.codec2_destroy.argtypes = [ctypes.c_void_p]
        lib.codec2_destroy.restype = None
        lib.codec2_encode.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_short),
        ]
        lib.codec2_encode.restype = None
        lib.codec2_decode.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_short),
            ctypes.POINTER(ctypes.c_ubyte),
        ]
        lib.codec2_decode.restype = None
        for name in (
            "codec2_samples_per_frame",
            "codec2_bits_per_frame",
            "codec2_bytes_per_frame",
        ):
            function = getattr(lib, name)
            function.argtypes = [ctypes.c_void_p]
            function.restype = ctypes.c_int

    def load(self) -> "Codec2Library":
        with self._lock:
            if self._lib is not None:
                return self
            manifest = self._read_manifest()
            try:
                lib = self._cdll_factory(str(self._library_path()))
                self._bind(lib)
            except (OSError, AttributeError) as exc:
                raise VoiceCodecError(f"cannot load Codec2 shared library: {exc}") from exc
            version = str(manifest["upstream"]["codec2_version"]).split(".")
            self.version_major = int(version[0])
            self.version_minor = int(version[1])
            self._manifest = manifest
            self._lib = lib
        return self

    def create(self, mode: int = CODEC2_MODE_3200) -> "Codec2Codec":
        self.load()
        return Codec2Codec(self, mode)


class Codec2Codec:
    def __init__(self, library: Codec2Library, mode: int) -> None:
        if library._lib is None:
            raise VoiceCodecError("Codec2 SDK is not loaded")
        self.library = library
        self.mode = int(mode)
        self._lib = library._lib
        self._lock = threading.Lock()
        self._closed = False
        pointer = self._lib.codec2_create(self.mode)
        if not pointer:
            raise UnsupportedVoiceMode(f"Codec2 mode {self.mode} is unavailable")
        self._pointer = ctypes.c_void_p(pointer)
        try:
            self.samples_per_frame = int(self._lib.codec2_samples_per_frame(self._pointer))
            self.bits_per_frame = int(self._lib.codec2_bits_per_frame(self._pointer))
            self.bytes_per_frame = int(self._lib.codec2_bytes_per_frame(self._pointer))
            if min(self.samples_per_frame, self.bits_per_frame, self.bytes_per_frame) <= 0:
                raise VoiceCodecError("Codec2 returned invalid frame geometry")
            if (self.bits_per_frame + 7) // 8 != self.bytes_per_frame:
                raise VoiceCodecError("Codec2 bit/byte frame geometry is inconsistent")
            if self.mode == CODEC2_MODE_3200 and (
                self.samples_per_frame != CODEC2_3200_SAMPLES_PER_FRAME
                or self.bits_per_frame != CODEC2_3200_BITS_PER_FRAME
                or self.bytes_per_frame != CODEC2_3200_BYTES_PER_FRAME
            ):
                raise VoiceCodecError("Codec2 3200 frame geometry differs from pinned ABI")
        except Exception:
            self.close()
            raise

    @property
    def pcm_bytes_per_frame(self) -> int:
        return self.samples_per_frame * CODEC2_SAMPLE_BYTES

    def _require_open(self) -> None:
        if self._closed:
            raise VoiceCodecError("Codec2 codec is closed")

    def encode(self, pcm_s16le: bytes) -> bytes:
        self._require_open()
        if len(pcm_s16le) != self.pcm_bytes_per_frame:
            raise ValueError(
                f"expected {self.pcm_bytes_per_frame} PCM bytes, got {len(pcm_s16le)}"
            )
        samples = struct.unpack(f"<{self.samples_per_frame}h", pcm_s16le)
        pcm = (ctypes.c_short * self.samples_per_frame)(*samples)
        encoded = (ctypes.c_ubyte * self.bytes_per_frame)()
        with self._lock:
            self._require_open()
            self._lib.codec2_encode(self._pointer, encoded, pcm)
        return bytes(encoded)

    def decode(self, encoded: bytes) -> bytes:
        self._require_open()
        if len(encoded) != self.bytes_per_frame:
            raise ValueError(
                f"expected {self.bytes_per_frame} encoded bytes, got {len(encoded)}"
            )
        bits = (ctypes.c_ubyte * self.bytes_per_frame).from_buffer_copy(encoded)
        pcm = (ctypes.c_short * self.samples_per_frame)()
        with self._lock:
            self._require_open()
            self._lib.codec2_decode(self._pointer, pcm, bits)
        return struct.pack(f"<{self.samples_per_frame}h", *pcm)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            pointer = getattr(self, "_pointer", None)
            self._pointer = None
            if pointer:
                self._lib.codec2_destroy(pointer)

    def __enter__(self) -> "Codec2Codec":
        return self

    def __exit__(self, *_args) -> None:
        self.close()


class C2FileEncoder:
    """Streaming standard .c2 writer with one final zero-padding operation."""

    def __init__(self, output: BinaryIO, codec: Codec2Codec) -> None:
        self.output = output
        self.codec = codec
        self._buffer = bytearray()
        self.frames_written = 0
        self._finalized = False
        self.output.write(
            C2Header(
                codec.library.version_major,
                codec.library.version_minor,
                codec.mode,
                0,
            ).to_bytes()
        )

    def feed_pcm(self, data: bytes) -> int:
        if self._finalized:
            raise VoiceCodecError("Codec2 file writer is finalized")
        self._buffer.extend(data)
        frame_bytes = self.codec.pcm_bytes_per_frame
        written = 0
        while len(self._buffer) >= frame_bytes:
            frame = bytes(self._buffer[:frame_bytes])
            del self._buffer[:frame_bytes]
            self.output.write(self.codec.encode(frame))
            self.frames_written += 1
            written += 1
        return written

    def finalize(self) -> int:
        if self._finalized:
            return self.frames_written
        self._finalized = True
        if self._buffer:
            if len(self._buffer) % CODEC2_SAMPLE_BYTES:
                raise VoiceFormatError("PCM stream ended mid-sample")
            frame_bytes = self.codec.pcm_bytes_per_frame
            frame = bytes(self._buffer) + b"\x00" * (frame_bytes - len(self._buffer))
            self._buffer.clear()
            self.output.write(self.codec.encode(frame))
            self.frames_written += 1
        self.output.flush()
        return self.frames_written


def validate_c2_file(
    path: str | Path,
    *,
    expected_major: int = 1,
    expected_minor: int = 2,
    expected_mode: int = CODEC2_MODE_3200,
    frame_bytes: int = CODEC2_3200_BYTES_PER_FRAME,
) -> C2Header:
    source = Path(path)
    try:
        size = source.stat().st_size
        with source.open("rb") as handle:
            header = parse_c2_header(handle.read(C2_HEADER_SIZE))
    except OSError as exc:
        raise VoiceFormatError(f"cannot open Codec2 file: {exc}") from exc
    if (header.version_major, header.version_minor) != (expected_major, expected_minor):
        raise VoiceFormatError(
            f"unsupported Codec2 file version {header.version_major}.{header.version_minor}"
        )
    if header.flags != 0:
        raise VoiceFormatError(f"unsupported Codec2 file flags 0x{header.flags:02x}")
    if header.mode != expected_mode:
        raise UnsupportedVoiceMode(f"unsupported Codec2 mode {header.mode}")
    body = size - C2_HEADER_SIZE
    if body <= 0:
        raise VoiceFormatError("Codec2 voice file has no encoded frames")
    if body % frame_bytes:
        raise VoiceFormatError("Codec2 voice file body is truncated")
    return header


def iter_decoded_pcm(path: str | Path, codec: Codec2Codec) -> Iterator[bytes]:
    validate_c2_file(
        path,
        expected_major=codec.library.version_major,
        expected_minor=codec.library.version_minor,
        expected_mode=codec.mode,
        frame_bytes=codec.bytes_per_frame,
    )
    with Path(path).open("rb") as handle:
        handle.read(C2_HEADER_SIZE)
        while True:
            encoded = handle.read(codec.bytes_per_frame)
            if not encoded:
                return
            if len(encoded) != codec.bytes_per_frame:
                raise VoiceFormatError("Codec2 voice file body is truncated")
            yield codec.decode(encoded)
