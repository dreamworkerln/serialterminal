import json
from pathlib import Path

import pytest

from serialterminal.voice_codec import (
    C2FileEncoder,
    C2_MAGIC,
    CODEC2_MODE_3200,
    Codec2Library,
    VoiceCodecError,
    VoiceFormatError,
    parse_c2_header,
    validate_c2_file,
)


class _Fn:
    def __init__(self, fn):
        self.fn = fn
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.fn(*args)


class _FakeLib:
    def __init__(self):
        self.destroyed = []
        self.codec2_create = _Fn(lambda mode: 123 if mode == 0 else 0)
        self.codec2_destroy = _Fn(lambda pointer: self.destroyed.append(pointer.value))
        self.codec2_samples_per_frame = _Fn(lambda pointer: 160)
        self.codec2_bits_per_frame = _Fn(lambda pointer: 64)
        self.codec2_bytes_per_frame = _Fn(lambda pointer: 8)
        self.codec2_encode = _Fn(self._encode)
        self.codec2_decode = _Fn(self._decode)

    @staticmethod
    def _encode(pointer, encoded, pcm):
        del pointer
        seed = sum(int(pcm[i]) for i in range(8)) & 0xFF
        for i in range(8):
            encoded[i] = (seed + i) & 0xFF

    @staticmethod
    def _decode(pointer, pcm, encoded):
        del pointer
        value = int(encoded[0])
        for i in range(160):
            pcm[i] = value


def _sdk(tmp_path: Path, *, commit="310777b1c6f1af0bc7c72f5b32f80f6fd9136962") -> Path:
    sdk = tmp_path / "sdk"
    (sdk / "lib").mkdir(parents=True)
    (sdk / "lib" / "libcodec2.so").write_bytes(b"fake")
    (sdk / "manifest.json").write_text(json.dumps({
        "sdk_format": 1,
        "platform": "linux-x86_64",
        "build": {"shared_library": True},
        "upstream": {
            "commit": commit,
            "codec2_version": "1.2.0",
        },
    }))
    return sdk


def test_codec2_loader_rejects_wrong_pinned_commit(tmp_path, monkeypatch):
    monkeypatch.setattr("serialterminal.voice_codec._runtime_platform", lambda: "linux-x86_64")
    library = Codec2Library(_sdk(tmp_path, commit="wrong"), cdll_factory=lambda path: _FakeLib())
    with pytest.raises(VoiceCodecError, match="upstream commit"):
        library.load()


def test_codec2_wrapper_geometry_encode_decode_and_idempotent_close(tmp_path, monkeypatch):
    monkeypatch.setattr("serialterminal.voice_codec._runtime_platform", lambda: "linux-x86_64")
    fake = _FakeLib()
    library = Codec2Library(_sdk(tmp_path), cdll_factory=lambda path: fake).load()
    codec = library.create(CODEC2_MODE_3200)
    assert (codec.samples_per_frame, codec.bits_per_frame, codec.bytes_per_frame) == (160, 64, 8)
    encoded = codec.encode(b"\x01\x00" * 160)
    assert len(encoded) == 8
    decoded = codec.decode(encoded)
    assert len(decoded) == 320
    codec.close()
    codec.close()
    assert fake.destroyed == [123]


def test_standard_c2_stream_writer_fragments_and_pads_only_once(tmp_path, monkeypatch):
    monkeypatch.setattr("serialterminal.voice_codec._runtime_platform", lambda: "linux-x86_64")
    codec = Codec2Library(_sdk(tmp_path), cdll_factory=lambda path: _FakeLib()).load().create(0)
    path = tmp_path / "voice.stvoice.c2"
    with path.open("wb") as handle:
        writer = C2FileEncoder(handle, codec)
        assert writer.feed_pcm(b"\x01\x00" * 50) == 0
        assert writer.feed_pcm(b"\x02\x00" * 110) == 1
        writer.feed_pcm(b"\x03\x00" * 3)
        assert writer.finalize() == 2
        assert writer.finalize() == 2
    assert path.read_bytes()[:3] == C2_MAGIC
    assert path.stat().st_size == 7 + 2 * 8
    header = validate_c2_file(path)
    assert (header.version_major, header.version_minor, header.mode, header.flags) == (1, 2, 0, 0)
    codec.close()


def test_c2_validation_rejects_header_only_truncated_and_wrong_magic(tmp_path):
    header = bytes.fromhex("c0dec201020000")
    path = tmp_path / "bad.c2"
    path.write_bytes(header)
    with pytest.raises(VoiceFormatError, match="no encoded frames"):
        validate_c2_file(path)
    path.write_bytes(header + b"123")
    with pytest.raises(VoiceFormatError, match="truncated"):
        validate_c2_file(path)
    with pytest.raises(VoiceFormatError, match="magic"):
        parse_c2_header(b"BAD" + header[3:])
