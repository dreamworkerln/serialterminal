import dataclasses,json,pathlib,subprocess,time
from serialterminal.voice_audio import _AlsaCapture
out = pathlib.Path(__file__).parent
results = []
for quiet in (True, False):
    args = ["arecord", "-D", "null", *(["-q"] if quiet else []), "-t", "raw", "-f", "S16_LE", "-r", "8000", "-c", "1"]
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    capture = _AlsaCapture(process, stop_timeout=1, kill_timeout=0.5)
    count = 0
    try:
        deadline = time.monotonic() + 2
        while count == 0 and time.monotonic() < deadline:
            chunk = capture.read(0.1)
            if chunk: count += len(chunk)
        assert count > 0
        capture.request_stop()
        while time.monotonic() < deadline:
            try:
                chunk = capture.read(0.1)
            except EOFError:
                break
            if chunk: count += len(chunk)
        else: raise AssertionError("null capture did not reach EOF")
        result = capture.finish()
        results.append({"argv": args, "pcm_bytes": count, "outcome": dataclasses.asdict(result), "graceful_stop": result.graceful_stop})
    finally: capture.close()
(out / "null-probe-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(results, ensure_ascii=False))
