# SerialTerminal logging contract

This document defines the generic logging roles shared by the human terminal and the machine-facing agent.

## Companion paths

With an explicit `--log`, a CLI run uses one basename and four files:

```text
<name>.log
<name>.console.log
<name>.fttiming.jsonl
<name>.application.log
```

With the default unique name:

```text
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.log
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.console.log
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.fttiming.jsonl
```

If `--log <path>` is supplied, that path names the primary `.log`; console,
timing and application paths are derived from the same basename in the same directory.
For example, `--log /runs/test.log` creates `/runs/test.log`,
`/runs/test.console.log`, `/runs/test.fttiming.jsonl` and `/runs/test.application.log`.
A path without a trailing `.log` keeps its full name and appends each companion suffix.
The application log opens before frontend startup, so startup errors also go there.
Without `--log`, the application log retains its separate default name
`logs/serialterminal-application-<timestamp>-p<pid>.log` relative to the working directory.
Scan-only CLI mode has no session `--log` and uses that application-log default.

The timing companion is incremental. SerialTerminal captures timing points with
`time.perf_counter_ns()` and wall-clock timestamp, then writes batches of256 events
on a background worker (bounded queue of8 batches). Close appends the remaining
partial batch. If the writer falls behind, producers can block on that bounded queue;
there is no claim of zero logging overhead. Flushed batches survive process death,
but an unflushed tail may be lost. Write/close failure is reported in the application
log and timing completeness must not be assumed. The trace includes session/FT1 boundaries plus
logical BLE write start/done, per-GATT-fragment write start/done, BLE notify, BINARY
submit/presentation/return, FT1 events and ordinary log-write start/done markers. It
contains metadata and sizes, not BINARY/base64 payload bytes.


## Base64 payload policy

Raw base64 payloads are **not persisted by default** in any SerialTerminal log file.
Known BINARY USER text and structured `*_b64` fields retain their surrounding record
but replace the payload with the exact placeholder:

```text
<base64>
```

Examples:

```text
/bin <base64>
> [BINARY] <base64>
"data_b64":"<base64>"
```

This default applies to human primary logs, companion `.console.log` files and agent
forensic/API logs. It prevents file-transfer traffic and raw transport chunks from
inflating logs with duplicate base64 material.

Raw base64 persistence is an explicit forensic opt-in:

```bash
serialterminal --profile chatter --log-base64
serialterminal agent --log-base64
```

`--log-base64` affects log files only. It does not make Chatter BINARY presentation
visible in the human screen/TUI. The agent JSONL API also remains unchanged:
`observe(include_events=true)` may return exact `data_b64` to the caller even when
the persisted forensic log contains only `<base64>`.

## Primary `.log` roles

The primary file is frontend-specific and its role must not be inferred from the extension alone.

Human terminal:

```text
.log = timestamped all-stream execution timeline
```

Each physical record carries an offset-aware ISO timestamp with millisecond precision
and the process-local session token. Human input is tagged `[I]`, local
SerialTerminal status is tagged `[LOCAL]`, and completed received logical lines are
tagged with their source stream, for example `[O chat]` or `[O telemetry]`.
Background Chatter telemetry is therefore present in the ordinary human `.log` even
when it is hidden from the interactive console. The old untimestamped compatibility
transcript format is no longer produced.

Agent:

```text
.log = forensic/API/transport record
```

It contains timestamped `[RUN]`, `[AGENT]`, request/response, state, TX, raw RX, error and generic sweep-mechanics records. Raw RX preserves transport chunk boundaries and event metadata. Exact RX bytes remain available through the live API; persisted `data_b64` is `<base64>` by default and is byte-accurate only with `--log-base64`. Persisted sequence gaps remain explicit through `forensic_gap`.

Do not replace the agent forensic log with the human all-stream line format.

### Sweep forensic records

When the agent runs a generic sweep job, its own mechanical job actions are written into the same forensic file as:

```text
[SWEEP]
```

A sweep record is structured JSON and contains at least the job identity and the same job-local event sequence used by `sweep_observe`:

```json
{
  "sweep_id":"sw1",
  "event_seq":17,
  "kind":"sample_completed",
  "coordinate":{"sf":8,"payload_bytes":32,"direction":"s1>s2"},
  "repetition":2
}
```

The exact fields vary by mechanical event kind. Current events include sweep/coordinate/sample lifecycle and terminal outcomes. A failed terminal event preserves the primary `failure`; when bounded cleanup independently fails, it may also carry a separate `cleanup_failure` rather than replacing the original cause.

These records are execution evidence, not RF/protocol analysis. They do not classify a point as CLEAN/DEGRADED, interpret CRC/HDR/retry quality, or replace the surrounding TX/RX/controller telemetry.

Publication order is intentional: the forensic `[SWEEP]` record is flushed before the corresponding event becomes visible in the in-memory sweep event ring. API `event.seq` and forensic `event_seq` therefore provide the correlation key between live progress and the durable timeline.

`sweep_close` and terminal-job eviction release only bounded in-memory job state; they do not delete or rewrite already persisted `[SWEEP]` records.

Sweep records are not copied into `.console.log`.

## Shared `.console.log`

Both frontends create a companion human-console audit view with the same physical record shape:

```text
2026-09-22T15:58:21.123+03:00 [s1] [I] /id
2026-09-22T15:58:21.287+03:00 [s1] [O] READY
```

Fields:

```text
timestamp  offset-aware host wall clock, ISO 8601, millisecond precision
session    process-local logical session token
[I]        one line queued through the frontend line-send path
[O]        one completed logical line from a profile human-console stream
```

The interactive frontend owns one logical managed session and uses `s1`. Agent mode uses its normal `s1`, `s2`, ... session identifiers.

A console record is one physical logfile line. Embedded CR/LF characters in input text are escaped as `\r` and `\n`.

The companion view is presentation/audit convenience, not transport or peer-delivery proof. `[I]` does not mean that the peer received or accepted the line.

## Receive-line semantics

`[O]` uses the canonical completed logical lines assembled by `ManagedSession`, with the receive-event timestamp that terminated the line.

Only streams declared as human-console streams by the selected profile are included.

Examples:

```text
generic BLE: main
Chatter BLE: chat
```

Background streams such as Chatter machine telemetry remain outside `.console.log`. In agent mode they remain available in the forensic `.log` and raw `observe.result.events`; in human mode they are present in the timestamped primary `.log` as stream-tagged completed logical lines.

## Lifecycle and compatibility

The old untimestamped human compatibility transcript has been removed. Human primary
logs are now timestamped all-stream timelines; agent primary logs remain forensic and
retain `forensic_gap` semantics unchanged.

The shared companion remains a filtered presentation/audit view and does not pretend
to be raw forensic evidence.

## Timing event identity and append

Each TimingTrace instance generates a fresh UUID segment_id. The correlation key
is `(segment_id, seq)`, where seq starts at1 and increases within that segment.
Session/profile replacement and process reopen append new segments without
truncating earlier events; seq alone is not file-global. Reserved identity and
clock fields cannot be overridden by caller-supplied metadata.

Cooperating POSIX writers lock each batch through flush, preserving complete JSON
lines even across concurrent instances/processes. A non-newline tail from a crash
is preserved and terminated before the next JSON record. That historical fragment
may remain invalid JSON/UTF-8 and is an explicit forensic gap, not recovered evidence.
Existing legacy rows without segment_id remain unchanged and lack the new
correlation guarantee; do not invent a shared segment for duplicated legacy seq.
Readers should tolerate/report malformed historical lines and use the pair for
new rows. perf_ns clock meanings do not change; physical append order across
segments is not guaranteed to match capture order. Neither a monotonic clock
across machine reboots nor complete SIGKILL evidence is promised.

Platforms without flock/pread retain the single-writer import/append path;
cross-process batch serialization is a POSIX guarantee.


## BLE release at shutdown

Graceful BLE cleanup records `ble_release` in the timing companion and a JSON
`BLE release` entry in the application log, including backend, exact BlueZ device
path where available, generation, `result`, `forced`, property observations and
intermediate cleanup errors. Session shutdown adds a `transport-release` state or
error event to the agent forensic log before its logger is stopped. A failed or
unknown release is also reported on stderr and durably in the application error
log. Successful local session closure and process exit do not by themselves prove
host disconnection; inspect the release result. SIGKILL may leave no final report.
See [AGENT_API.md](AGENT_API.md#verified-ble-release-on-close) for the contract.


## Bounded offline excerpts

`scripts/analyze_file_transfer.py <run-directory>` normally prints one aggregate
summary and writes `analysis.json` and `analysis.md`; it does not print raw logs.
For an already identified failure or anomaly, extract a narrow time window:

```bash
python3 scripts/analyze_file_transfer.py /path/to/run \
  --excerpt-at '2026-10-17T10:00:00+03:00' --before 2 --after 3 \
  --excerpt-log application
```

This mode scans the selected ST logs without running the full analysis or capture
decoders. It writes a new `excerpt-<UTC>.json` in the run directory and prints only
its path, counters and completeness metadata. `--excerpt-log` is repeatable and
accepts `primary`, `console`, `timing`, `application`; omitted means all four logs.
The time must include a timezone (`Z` or an explicit offset). Boundaries are
inclusive; `before` and `after` are seconds around the requested instant and default
to 2 each. Timing JSONL uses its wall-clock `timestamp`, not `perf_ns`. Untimestamped
application traceback lines inherit the preceding application record's timestamp.
Records retain the source filename and original physical line number and are sorted
by timestamp. Missing files, unparseable timestamps and oversized lines are counted.

Only explicit `--show-excerpt` prints selected raw records, as escaped JSON lines,
for focused failure/bug diagnosis under the workspace evidence policy. Limits are
global across selected logs: default `--max-lines 80 --max-bytes 16384`, hard maximum
200 lines and 32768 UTF-8 bytes of serialized records, including provenance.
The time window cannot exceed 300 seconds. Long records are shortened and marked
`text_truncated`; omitted or shortened records set `truncated`. Read limits also
bound memory for oversized source lines. Counts expose truncation so it cannot be
mistaken for complete evidence. Unparseable or shortened source records may require
a more specific parser; source logs are never modified. Exit 1 means no matching
records; invalid requests exit 2 and do not fall back to a full-log analysis.
Do not stitch successive excerpts together to load the entire log into context.


## File-run radio preflight report

`scripts/run_file_transfer.py` configures both nodes before `file_send_start`.
`--sf` defaults to 7, `--bw-khz` to 500, and `--power-dbm` to 2.
`--freq-mhz` defaults to 470 MHz for both nodes; supply it explicitly to override
the frequency. Frequency has 1 kHz precision. The runner does
not enable out-of-band policy, change heartbeat/diagnostic settings, reset defaults,
repair/reboot the radio, or retry rejected setters.

Each node receives `/sf`, `/bw`, `/power`, `/freq` setters sequentially. Each requires
an exact matching SAVED response and a correlated ST TX-written event; queued alone
is insufficient. On rejection/busy or an unconfirmed outcome, later setters stop.
Read-only `/config`, `/radio read config` and `/radio validate config` must then prove
persisted values, NVS storage, readable LoRa registers, RX mode and validation OK.
Frequency register validation belongs to firmware because it accounts for FRF
quantization and RX errata. Configuration values still must match the exact request.

`radio_preflight.json` in the run directory records requested settings, per-node
setter outcomes, config/register values, validation differences and failed or
unverified fields. The same structured result is embedded in `result.json`. Failure
returns nonzero and does not call `file_send_start`; the source and its run copy are
preserved. The next node is marked NOT_ATTEMPTED when an earlier node fails.
`--preflight-timeout` bounds each control response (default 5 seconds).
`--timeout` bounds file-transfer observation after `file_send_start` (default
3600 seconds, one hour); it does not include the preceding configuration phase.

Full node readiness/current-work status is currently SKIPPED, with the reason and
TODO_057 link in that report. M1 STATUS credits/counters and host session status are
not full node readiness. Firmware work and its hardware acceptance remain separate.
All these reports stay on disk; normal stdout retains bounded progress and summaries.


## USB capture across buses

The file runner defaults to `--usbmon-interface usbmon0`: one capture covers all
USB buses, including a pair of nodes on different buses or after moving ports.
`dream` must have read access to `/dev/usbmon0`; network capabilities on `tcpdump`
do not grant that device-file access. The runner checks the device and tools before
starting capture and does not silently switch interfaces or elevate privileges.

For USB runs with capture enabled, passive serial discovery and sysfs ancestry
resolve each selected device key to tty, USB bus number and device address before
capture. No tty is opened by this metadata step. The mapping is saved in
`result.json` as `usb_capture_targets`. An explicitly chosen `usbmonN` with N>0
must cover both nodes; otherwise the runner stops before capture or file transfer.

The original `usb.pcap` contains all captured traffic and remains unchanged.
The analyzer filters endpoint counters to selected `(bus, device)` pairs, reports
missing traffic for either node, and records unattributed legacy captures as an
evidence gap. This presence check is not proof that every file packet was captured.
Mapping is a pre-capture snapshot: re-enumeration or address reuse requires separate
identity verification. BLE runs with optional USB capture retain host-wide USB
statistics because BLE device keys do not identify USB endpoints.

Persistent read-only access for `dream` can be configured by root in a separate
udev file, preserving any existing per-bus rule:

```text
# /etc/udev/rules.d/99-usbmon0-dream.rules
SUBSYSTEM=="usbmon", KERNEL=="usbmon0", OWNER="dream", MODE="0400"
```

After reloading udev rules and loading `usbmon`, trigger the usbmon subsystem.
For automatic module loading, `/etc/modules-load.d/usbmon.conf` contains `usbmon`.
These are host preparation steps; the runner does not edit system permissions.


## File-run progress and USB capture scope

Runner stdout shows paired, independently measured ROOT statuses, for example:

```text
t=25.0с TX 40.0% [передача] | RX 27.0% [приём] | Δ=+13.0п.п.
```

Each side uses its own `bytes_completed / wire_bytes`; compression never becomes
DATA progress. RX stays unknown until the matching ROOT transfer appears; previous
files and recursive service-file percentages cannot stand in for ROOT reception.
TX counts serviced DATA, RX counts unique stored DATA. A node reaches displayed
100% only in its own completed state; all bytes before verification display at most
99.9%. Run success is a separate `итог=PASS SHA256=OK` line after both nodes complete,
received size/SHA-256 match, and owned sessions close. Capture/agent cleanup and the
offline analyzer still determine the final overall evidence verdict.

The runner samples approximately once a second. It prints when either side crosses
a percentage threshold (`--progress-step`, default 1), changes phase, reports a
repair/control activity, or regresses. Use `--progress-step 10` for less frequent
progress. Both endpoints have independent thresholds, including after progress
resets during recovery.
Repeated unchanged samples stay silent regardless of elapsed time. Phase changes
produce an immediate observation when detected, independently of percentage; short
phase transitions are retained in ROOT events. There is no timed stdout heartbeat.
Values are the actual sampled percentages (one decimal), rather than invented
intermediate observations when a sample crosses several thresholds. Lines include
elapsed time, phases, percentages and a signed TX-minus-RX difference. Full
wire-byte/chunk counters remain in `progress.jsonl` and ST logs, keeping stdout compact. The two
snapshots are sequential observations, not an atomic measurement or a BLE loss rate;
a difference can also reflect queues, LoRa losses or repairs. Different wire sizes
produce an explicit unavailable delta, never a loss estimate.

Phases cover preparation/compression, send/receive, waiting RESULT, repair request,
selective delivery, verification/decompression, recovery, suspension and terminal
states. Both ROOT event cursors are drained inside the Python process to preserve
short transitions between samples without printing DATA events. Repair snapshots
show the last requested missing count, its frame depth and receiver no-progress
cycles where supplied. These are not a live nested-child progress meter. An expired
event cursor is reported and retained in `result.json:monitor_event_gaps`; current
snapshots continue, with an explicit phase-history gap rather than invented events.
A receiver failure stops the run immediately rather than waiting the whole hour.

`прогресс DATA не менялся Nс` measures time since the byte/size counters changed.
It is not time since the last packet: selective retransmissions need not increase
TX's original DATA counter. The phase and repair activities explain that distinction.
All executed-run stdout is mirrored by Python to `runner.stdout.log` in the same
run directory, including the run path and the analyzer summary; no shell `tee` is
needed. Analyzer stderr is saved separately as `analyzer.stderr.log`. Dry-run plans
create no directory or log.

Printed paired observations, timestamps, activities, deltas and verification flags
are also saved as structured `progress.jsonl` in the run directory; API transcripts
and all four ST logs remain there. Raw records stay on disk under workspace policy.

For usbmon0, pcap records with `included < original` indicate a snapshot-limited
record; the file may still be structurally complete. The analyzer records bounded
header-only diagnostics and differentiates selected-node truncation from truncation
on unrelated devices. Selected-node truncation remains an evidence gap; unrelated
snapshot truncation is retained as a capture warning without invalidating selected
node evidence. An actually incomplete pcap record/file is a gap regardless of which
device it concerns. Missing node traffic, missing mapping and kernel drops retain
their existing evidence gates. PASS does not claim complete capture of unrelated
USB traffic or zero packet loss.


### Runner completion and progress evidence

`completed` can precede FT1 drain/release. The runner retries only
`file_transfer_close` on `file_transfer_active`, for at most five seconds per
endpoint, and reports a bounded wait phase. Other errors fail immediately; it
never resends the file to fix a close failure. Per-request API waits and long-poll
waits are bounded by the remaining file-observation deadline. Timeout/scan inputs
must be finite and positive. Cleanup has its own bounded waits after observation.

The analyzer now reports `runner_progress`: independent intermediate counts,
phases, maximum observed absolute TX/RX difference and consistency. It fingerprints
recorded ROOT snapshots and matches them, by endpoint, to preceding `agent.jsonl`
responses from ST. Wrong roles/ROOT identities, invented counters, incorrect deltas,
backward elapsed times, premature verified claims and missing progress for a started
run become evidence gaps. A successful run must include a verified paired
observation. FT1 event counts must also agree between primary and timing logs.
These checks verify recorded observations, not events hidden between samples or
loss localization. A monitor event-history gap remains explicitly reported.

`run_file_transfer.py --skip-analysis` сохраняет evidence и завершает только
механический прогон без запуска анализатора. Проверка обеих completed сторон,
размера и SHA-256 остаётся обязательной; `result.json` отмечает `analysis_skipped`.
