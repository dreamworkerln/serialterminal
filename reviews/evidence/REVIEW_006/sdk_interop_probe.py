import hashlib, io, json, math, os, pathlib, struct, subprocess
from serialterminal.voice_codec import Codec2Library, C2FileEncoder, iter_decoded_pcm, validate_c2_file
out = pathlib.Path(__file__).parent
sdk = pathlib.Path(os.environ.get("CODEC2_SDK", "/home/dream/coding/python/codec2-sdk/dist/linux-x86_64"))
library = Codec2Library(sdk).load()
pcm = struct.pack("<8000h", *(int(5000 * math.sin(2 * math.pi * 240 * i / 8000)) for i in range(8000)))
(out / "synthetic.raw").write_bytes(pcm)
codec = library.create(0)
try:
    with (out / "st-encoded.stvoice.c2").open("wb") as output:
        writer = C2FileEncoder(output, codec)
        for offset in range(0, len(pcm), 254): writer.feed_pcm(pcm[offset:offset+254])
        frames = writer.finalize()
finally: codec.close()
with (out / "sdk-interop-cli.log").open("w") as log:
    subprocess.run([str(sdk / "bin/c2dec"), "ignored", str(out / "st-encoded.stvoice.c2"), str(out / "sdk-decoded.raw")], check=True, stdout=log, stderr=log)
    subprocess.run([str(sdk / "bin/c2enc"), "3200", str(out / "synthetic.raw"), str(out / "sdk-encoded.c2")], check=True, stdout=log, stderr=log)
header = validate_c2_file(out / "sdk-encoded.c2")
codec = library.create(0)
try: decoded = b"".join(iter_decoded_pcm(out / "sdk-encoded.c2", codec))
finally: codec.close()
(out / "st-decoded.raw").write_bytes(decoded)
result = {"sdk_path": str(sdk), "sdk_manifest_sha256": hashlib.sha256((sdk / "manifest.json").read_bytes()).hexdigest(),
          "sdk_upstream": library.manifest["upstream"], "ST_frames": frames,
          "ST_encoded_bytes": (out / "st-encoded.stvoice.c2").stat().st_size,
          "SDK_decoded_ST_bytes": (out / "sdk-decoded.raw").stat().st_size,
          "ST_decoded_SDK_bytes": len(decoded),
          "encoded_payload_identical": (out / "st-encoded.stvoice.c2").read_bytes() == (out / "sdk-encoded.c2").read_bytes(),
          "library_sha256": hashlib.sha256(library._library_path().read_bytes()).hexdigest()}
assert result["ST_encoded_bytes"] == 407 and result["SDK_decoded_ST_bytes"] == result["ST_decoded_SDK_bytes"] == 16000
result["outcome"] = "PASS"
(out / "sdk-interop-summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(result, ensure_ascii=False))
