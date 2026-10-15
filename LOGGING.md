# SerialTerminal logging contract

This document defines the generic logging roles shared by the human terminal and the machine-facing agent.

## Companion paths

A normal run uses one basename and three files:

```text
<name>.log
<name>.console.log
<name>.fttiming.jsonl
```

With the default unique name:

```text
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.log
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.console.log
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.fttiming.jsonl
```

If `--log <path>` is supplied, that path names the primary `.log`; companion paths are derived from the same basename.

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
