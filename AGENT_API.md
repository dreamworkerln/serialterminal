# SerialTerminal agent interface

`serialterminal agent` is the canonical local machine-facing JSON Lines frontend over the same discovery, transports and reconnect/session core used by the human terminal.

The interface is intentionally generic. Firmware/project-specific scenarios and acceptance rules belong in consuming skills. Controller-specific behavior is selected explicitly per session through `profile`; the default is `generic`.

## Start and JSONL rules

```bash
python3 serialterminal.py agent
```

Use the privileges required by the host serial/Bluetooth environment.

The process reads one JSON object per stdin line and writes one correlated JSON response per request. It emits no unsolicited JSON events. `observe`, `sweep_observe` and `file_transfer_observe` may remain pending while later ordinary requests are accepted, so stdout response order is not globally request order; correlate by `id`.

Success envelope:

```json
{"id":1,"ok":true,"result":{}}
```

Error envelope:

```json
{"id":1,"ok":false,"error":{"code":"unknown_session","message":"unknown session: s1"}}
```

`observe`, `sweep_observe` and `file_transfer_observe` are asynchronous at the JSONL frontend and require a non-null `id`. Do not reuse an ID while any such long-poll with that ID is pending. Duplicate use returns `request_id_busy` without cancelling the original request.

## Operations

```text
discover
open
list_sessions
status
send_line
send_bytes
observe
close
file_send_start
file_transfer_observe
file_transfer_cancel
file_transfer_close
sweep_start
sweep_observe
sweep_cancel
sweep_close
```

`observe` remains the only session receive/cursor operation. Sweep jobs have their own independent job-local cursor through `sweep_observe`. Historical `events` and `wait_events` operations are removed and return `unknown_operation`.

## Run logs

The companion human-console record format is shared with the interactive frontend and is specified in `LOGGING.md`. The agent's primary `.log` remains the stronger forensic/API/transport record described below.

Every agent process creates forensic, human-console and buffered timing logs unless an explicit forensic path is supplied:

```text
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.log
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.console.log
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.fttiming.jsonl
```

With:

```bash
python3 serialterminal.py agent --log /tmp/serialterminal-agent.log
```

the companions are `/tmp/serialterminal-agent.console.log` and `/tmp/serialterminal-agent.fttiming.jsonl`.

The main `.log` is forensic/API/transport evidence and contains chronological records such as:

```text
[RUN]
[AGENT]
[AGENT REQUEST]
[AGENT RESPONSE]
[STATE]
[TX]
[RX <stream>]
[ERROR]
[SWEEP]
```

Raw RX records preserve event `seq`, stream, transport/session chunk boundaries and incremental decoded `text`. On disk, `data_b64` is redacted to `<base64>` by default; start the agent with `--log-base64` only when byte-accurate persisted base64 is explicitly required. The live `observe(include_events=true)` response remains byte-accurate regardless of that logging flag. There are no separate forensic `[RX LINE]` or `[RX PARTIAL]` records.

The event ring is bounded. If the persisted logger observes a sequence discontinuity because retained events were lost, it writes an explicit error record before the next retained event:

```json
{
  "event":"forensic_gap",
  "session":"s1",
  "last_logged_seq":100,
  "next_logged_seq":105,
  "lost_seq_first":101,
  "lost_seq_last":104
}
```

A log containing `forensic_gap` is explicitly incomplete for that session/range; never treat it as silently continuous evidence.

The companion `.console.log` is presentation/audit convenience:

```text
2026-09-05T08:23:01.100+00:00 [s1] [I] status
2026-09-05T08:23:01.420+00:00 [s1] [O] READY
```

`[I]` is text accepted through `send_line`. `[O]` is a completed logical line from a human-console stream declared by the selected profile. `send_bytes` is not rendered as ordinary human input. Background streams remain absent from the companion log even though their raw events remain in the forensic log and `observe.result.events`.

Startup `[AGENT]` metadata records all three paths.

The `.fttiming.jsonl` file is incremental: events use `time.perf_counter_ns()` and
accumulate in batches of256. A dedicated writer writes/flushes each complete batch;
close appends the final partial batch and joins the writer. At most8 queued batches
plus the current producer/writer batches are retained. If the writer falls behind,
producers apply backpressure rather than silently dropping events. There is no
per-batch fsync: flush hands data to the OS cache. SIGKILL may lose the current/queued
tail, but does not erase previously flushed batches. Writer failure is reported in
the application log and marks the timing trace incomplete. Each JSON line
contains a monotonic `perf_ns`, wall-clock `timestamp`, a trace `seq`, `event`, and
small structured fields without BINARY/base64 payload bytes.

The timing trace includes the existing session/FT1 boundaries plus explicit transport
and Chatter BINARY points such as `transport_write_start`,
`transport_write_done`, `ble_gatt_write_start`, `ble_gatt_write_done`,
`ble_notify`, `binary_submit`, `binary_presentation_line`,
`binary_presentation_match`, `binary_return` and `ft1_event`. It also records
forensic/console log-write start/done markers in the timing buffer so logging overhead can be
measured without writing the timing trace itself during the run.

Base64 persistence is opt-in:

```bash
python3 serialterminal.py agent --log-base64
```

Without that flag, BINARY USER payloads and structured `*_b64` fields in both log
files use the literal `<base64>` placeholder. This changes only persisted logs, not
JSONL responses.

## Discovery

Request:

```json
{"id":1,"op":"discover","scope":"auto"}
```

Scopes:

```text
auto
serial
ble
spp
```

Optional `baud` and `scan_seconds` may be supplied. An explicit discovery `baud`
is retained as the Serial override for candidates from that discovery. With no
`baud`, Serial baud is resolved when `open` selects the profile: generic 115200,
Chatter 921600. BLE and native SPP do not use UART baud. The terminal discovery
window defaults to 3 seconds; the aggressive scanner has a separate 5-second
window and 8-second probe timeout. Shared immutable defaults live in
`src/serialterminal/settings.py`; runtime overrides remain per selector/session.

Discovery returns transport candidates with stable-enough `device_key`, `kind`, `label`, and `detail`. The agent frontend uses the same sticky physical identity as the rest of SerialTerminal.

Default BLE discovery is capability-based. A device is eligible when it advertises standard Nordic UART Service or its address has cached confirmed NUS capability. Advertised name and controller profile do not whitelist a device. A transient scanner/probe result with unknown NUS status does not erase prior definitive cached NUS knowledge; definitive probe YES/NO remains authoritative.

If an expected BLE target is absent, use the Bluetooth capability scanner/prober, then run `discover` again. Machine clients open the returned `device_key`; there are no BLE name aliases in the JSONL API.

## Open

Generic/default:

```json
{"id":2,"op":"open","device_key":"ble-address:..."}
```

Equivalent explicit form:

```json
{"id":2,"op":"open","device_key":"ble-address:...","profile":"generic"}
```

Defaults:

```text
eol=lf
profile=generic
wait_connected_ms=10000
```

The returned session is long-lived until `close` or process shutdown. If the target is not connected within `wait_connected_ms`, `open` still returns the live session with `state:"reconnecting"`; reconnect continues in the background against the same physical target.

The `generic` profile sends no controller preamble. Generic BLE uses standard NUS: `0002` write and `0003` receive stream `main`.

Bundled controller profiles are explicit, for example:

```json
{"id":3,"op":"open","device_key":"ble-address:...","profile":"chatter"}
```

The Chatter profile supplies its controller preamble (including `/id`) and profile-defined BLE receive layout (`chat` plus optional `telemetry`). Profile selection is per session, not process-global. One process may hold sessions with different profiles simultaneously.

`open` does not accept the legacy `auto_id` toggle. Unknown profile names return `unknown_profile`.

The successful result includes `session`, `device_key`, `description`, `state`, `streams`, `latest_seq`, and `profile`. Save `latest_seq` when earlier startup activity should be ignored by later `observe` calls.

The same `device_key` cannot be owned by two sessions in one `SessionManager`.

## Status and session list

```json
{"id":4,"op":"status","session":"s1"}
```

Typical result fields:

```text
session
device_key
description
profile
connected
state
streams
latest_seq
queued_tx
file_transfer_supported
file_transfer
```

`file_transfer_supported` is profile-capability based. The bundled `generic`
profile returns `false`; the bundled `chatter` profile supplies an opaque binary
USER capability. `file_transfer` is the current or most recently retained transfer
snapshot for that session, or `null`.

```json
{"id":5,"op":"list_sessions"}
```

## Send text

```json
{"id":6,"op":"send_line","session":"s1","text":"hello"}
```

Optional per-message EOL:

```text
lf
crlf
cr
```

Example response:

```json
{"id":6,"ok":true,"result":{"tx_id":12,"state":"queued"}}
```

`queued` proves only that the reconnect-safe SerialTerminal TX queue accepted the item.

A later raw event:

```json
{"kind":"tx","tx_id":12,"tx_state":"written"}
```

means the transport `write()` call completed successfully. It does **not** prove peer receipt, RF delivery, firmware acceptance, ACK, or higher-level operation completion.

Ordinary transport failures that are known safe to repeat remain reconnect/retry ordered by the session queue.

A transport may instead report an ambiguous write outcome. Current BLE examples are a GATT write timeout, where cancellation cannot prove that the backend/native side effect did not already occur, and a fragmented write failure after at least one write-without-response ATT chunk completed. The session then records:

```json
{"kind":"tx","tx_id":12,"tx_state":"unknown"}
```

and an associated error event with:

```json
{"kind":"error","tx_id":12,"state":"send-outcome-unknown"}
```

`tx_state:"unknown"` is terminal for that queued item: SerialTerminal does **not** automatically resend it after reconnect because doing so could create a duplicate side effect. A machine scenario must decide success/failure from later application/protocol evidence or classify the case as ambiguous/inconclusive. Do not reinterpret `unknown` as either `written` or definitely-not-written.

Serial writes now use the same conservative outcome boundary: a nonzero short or
invalid backend write return, any exception from backend write, and any flush failure
after writing produce `unknown`. An explicit zero-byte return is a definite failure
and remains reconnect/retry eligible. Unexpected backend exceptions cannot silently
end a TX worker with an accepted item left pending.

Session shutdown settles writes that never started as `tx_state:"cancelled"` and
writes still in flight as `unknown`. A failed session worker emits an error with
`state:"worker-failed"`, stops new admission and settles dependent pending TX.
Notifier failures emit `state:"notifier-failed"`; they do not replay a completed TX.
These are host transport outcomes, not controller or RF queue settlement.

The internal profile lifecycle hooks include addressable `cancel_tx(tx_id)` and an
owned-TX drain. They affect only the caller's accepted writes; no new JSONL cancel
operation or firmware command is introduced. FT1 accounts for its host writes before
releasing ownership. If that drain times out, the transfer reports
`local_tx_drain_timeout` and retains ownership until the session is closed.


## Send raw bytes

```json
{"id":7,"op":"send_bytes","session":"s1","data_b64":"FDE="}
```

Raw and line sends share the same ordered TX queue. `send_bytes` does not create ordinary companion-console input records.

## Observe

One session:

```json
{"id":20,"op":"observe","cursors":{"s1":42},"timeout_ms":15000}
```

Multiple sessions use the same shape:

```json
{"id":21,"op":"observe","cursors":{"s1":42,"s2":75},"timeout_ms":15000}
```

By default, `observe` returns completed logical lines, cursors and timeout state only. Raw session events are opt-in:

```json
{"id":22,"op":"observe","cursors":{"s1":42,"s2":75},"timeout_ms":15000,"include_events":true}
```

`include_events` is optional and defaults to `false`; when present it must be a JSON boolean. With `false`, the `events` field is omitted from `result`. With `true`, `result.events` contains the same raw event objects used by the previous always-on response contract.

`cursors` is required and non-empty. Each value is the last raw `SessionEvent.seq` already processed for that session. Sequence spaces are independent per session. There is intentionally one raw cursor model and no separate line cursor.

Default result shape:

```json
{
  "lines":[...],
  "cursors":{"s1":44,"s2":75},
  "timed_out":false
}
```

With `"include_events":true`, the same result additionally contains:

```json
{
  "events":[...]
}
```

Opt-in `events` are forensic raw session events (`state`, `tx`, `rx`, `error`). Exact bytes are in `data_b64`. BLE notifications remain transport-sized chunks; SerialTerminal does not make transports pretend to be line-oriented. Raw events are still written to the forensic `.log` independently of whether they are projected into a JSON response.

`lines` are completed LF-terminated logical firmware lines assembled once on `ManagedSession`. Each stream has independent UTF-8/line state. A line record contains:

```text
session
stream
seq_first
seq_last
text
```

LF is omitted from `text`; CR immediately before LF is removed for the logical line view. Raw event bytes/text are not normalized. Empty LF-terminated lines are retained.

Use:

```text
firmware/protocol reasoning   -> default result.lines
transport/chunk forensics     -> include_events:true -> result.events / data_b64
```

Do not manually join RX chunks when the completed logical line is already present.

A completed line is returned when `line.seq_last` is newer than the input cursor. Its `seq_first` may be at or before that cursor because the line may have begun in a previous observation.

For each watched session, event and line views come from one cursor-consistent snapshot under the same session lock.

### Cursor expiry

The finite raw event ring defines the cursor window. If a requested cursor is older than retained history, the whole request fails with `cursor_expired`, including `session`, `requested_seq`, and `oldest_seq` in error details. There is no separate line-cursor error.

Unknown watched sessions fail with `unknown_session`.

### Lifecycle boundaries

Only LF-terminated lines become `result.lines`. Incomplete line state is discarded at connection lifecycle boundaries so bytes from different transport connections cannot be joined. Raw retained events remain the forensic evidence.

### Timeouts

`timeout_ms` must be non-negative.

`timeout_ms:0` returns an immediate snapshot. If no event exists, `timed_out:false` with empty `lines` (and empty `events` only when `include_events:true`).

A positive timeout long-polls until the first new raw event on any watched session. If nothing arrives by expiry, it returns empty `lines` with `timed_out:true`.

If raw activity arrives without completing a logical line, the request still returns immediately and advances the affected event cursor. In the default projection `lines` may therefore be empty while `cursors` changed. With `include_events:true`, the same response also exposes the triggering raw event(s). Continue with the returned cursors; do not manually reconstruct a line from chunks unless transport forensics is the actual task.

There are no receive-stream filters in `observe`; `include_events` controls only response projection, not collection, wakeup or forensic logging.

## File transfers

File transfer is a high-level application operation. Callers do not manually read the
file, base64 chunks, send firmware `/bin` commands or parse a human progress bar.

The selected session profile must provide an opaque binary USER capability. Otherwise
file operations fail with `file_transfer_unsupported`.

Agent receive directory defaults to the `files` directory in the SerialTerminal
source root (next to `pyproject.toml`) for a source checkout/editable install.
Packaged installs without that source root fall back to `./files` in the launch
directory. The directory is created on demand on Linux and Windows.

Override for the whole agent process with:

```bash
python3 serialterminal.py agent --receive-dir /path/to/incoming
```

### Start

```json
{"id":60,"op":"file_send_start","session":"s1","path":"/tmp/demo.bin"}
```

The request returns promptly after creating the background transfer. Typical initial
result:

```json
{
  "transfer_id":"2c0c98db8bfdd7d1",
  "direction":"TX",
  "filename":"demo.bin",
  "state":"preparing",
  "original_bytes":0,
  "wire_bytes":0,
  "chunks_total":0,
  "chunks_completed":0,
  "bytes_completed":0,
  "percentage":0.0,
  "events":{"cursor":0,"max_window":100,"retention":1024}
}
```

Only one active file transfer is allowed on a session. The transfer acquires mutation
ownership after settling a pre-transfer accepted-TX fence. While owned, ordinary
`send_line`, `send_bytes`, `close` and sweep acquisition on that session are
rejected with `session_busy`. Read-only `status` and ordinary `observe` remain
available.

The bundled Chatter profile negotiates the protected local `/m1` interface on open.
A WELCOME selects machine mode; only an explicit old-firmware command rejection
selects legacy `/bin` compatibility. Silence is `machine_negotiation_timeout`.
The [shared contract](CHATTER_MACHINE_PROTOCOL_V1.md) defines CRC, epoch/request
identity, two outstanding slots and the cached local QUERY recovery path.
ACCEPTED and TX_DONE do not settle a machine send: LINK_OK requires the existing
matching radio ACK. It still does not prove remote ST storage. Human DELIVERY
telemetry never drives FT1. UNKNOWN/unsettled outcomes block new submissions.
A terminal DATA LINK_FAIL records `binary_send_link_failed` and continues the
file stream to END; this applies to ROOT, missing-list DATA and requested repair
DATA. M1 releases that request, so other admitted pipeline slots remain valid.
ST does not immediately replay the failed DATA: the receiver requests actual
holes through recursive final repair. DATA may also have arrived despite a lost
ACK. Only verified FT1 RESULT OK completes the file. Progress counts the serviced
DATA stream, including these known link failures; it is not proof of storage.
LINK_FAIL of META/END/control, REJECTED and UNAVAILABLE remain fatal. UNKNOWN
and unresolved ownership still block new submissions; no hidden RF replay or reboot.

A transient local HELLO/bootstrap failure can be renegotiated once the previous
machine owner has settled. The lifecycle worker also retries this negotiation
for an idle receiver; a new file operation can trigger it directly. Only local
HELLO is repeated, within each operation's deadline: no RF SUBMIT is replayed.
The owner nonce and same-epoch request sequence are retained, while a fresh
HELLO request rejects stale negotiation replies. Pending machine tickets,
UNKNOWN/unsettled outcomes and incompatible WELCOME remain blocking conditions.
Timing events `machine_negotiation_failed` and `machine_negotiation_retry` expose
the negotiation failure/recovery separately from file DATA delivery.

File transfer never sends `/both`, `/chat` or `/tele`, including reconnect and
terminal cleanup. Machine mode works independently of that human output mode.
Only legacy compatibility reads `/help` and fails in TELEMETRY-only before `/bin`.
Machine frames are hidden on the human screen and redacted in default logs;
`--log-base64` retains them for explicit forensic capture.

Remote completion remains FT1-level: stable transfer/chunk identity, MISSING repair and
final `RESULT OK`. A controller reboot may occur without transport disconnect. The
profile waits for a new `CHATTER READY` and FT1 can replay the same idempotent message.
The Chatter profile reads `/config` and actual `/radio read config` before deriving
radio-dependent deadlines; cached PHY belongs to the controller epoch and connection
generation. During a local reboot, the last verified PHY may estimate existing
control/idle waits; it never authorizes a new RF send. SAVED/repair clears that
estimate, and after READY the profile reads fresh PHY. Missing, mismatched or stale
readback for RF admission fails with `radio_timing_unavailable`
(or `local_controller_reset`) before RF submission. Deadlines cover LoRa ToA, firmware
ACK/retry/backoff and both machine slots. They add no pacing or host RF retransmission.
The full timing inventory and formulas are in [TIMING_AUDIT.md](TIMING_AUDIT.md).

Abandoned incoming transfers fail with `remote_sender_timeout` after a derived
inactivity budget: `(max_control_replays + 1) * control_budget + drain_budget`.
An active recursive child pauses its parent's idle check. Control and RESUME waits
use the profile roundtrip budget; there is no implicit one-hour file deadline.
Observe `timeout_ms` remains only the caller's long-poll bound. Terminal cleanup uses
remaining admitted machine-ticket deadlines plus a local guard, preserving ownership
if settlement cannot be proved and preserving the primary error in diagnostics.

### Observe

```json
{
  "id":61,
  "op":"file_transfer_observe",
  "session":"s1",
  "transfer_id":"2c0c98db8bfdd7d1",
  "cursor":0,
  "window":100,
  "timeout_ms":30000
}
```

This is an asynchronous JSONL long-poll and requires a non-null request `id`.
It has a transfer-local bounded cursor/event model analogous to sweep jobs. Result
contains `events`, `cursor`, `head_cursor`, `state`, `progress` and
`timed_out`.

Progress fields include:

```text
transfer_id
direction
filename
state
original_bytes
wire_bytes
chunks_total
chunks_completed
bytes_completed
percentage
```

Terminal snapshots may additionally include `final_path`, `elapsed` or structured
`failure` with stable `code`, human `message`, optional `phase` and details.

Exactly `100.0` means `state=completed`. A sender that has delivered every DATA
chunk but is still waiting for the receiver's final verified RESULT remains below
100%.

DATA with an incorrect META-derived length is discarded with `chunk_rejected`
(`chunk_index`, `reason=length_mismatch`, `actual_length`, `expected_length`). RX
keeps its partial file and valid chunks; END/MISSING selectively requests any
remaining hole. A malformed duplicate does not erase an already stored valid copy.

Reconnect-repair states include `waiting_result`, `repair_requested` and
`repairing`. Transfer events may include `missing_detected`, `repair_requested`,
`repair_round_sent` and `control_replay`; these are structured application events
and do not require parsing human TUI output.

Receiver `completed` means the wire stream and original file were verified and the
final file was atomically published. Sender `completed` means it received remote
`RESULT OK`; it does not mean merely that the last local BLE/USB write succeeded.

### Cancel and close retained state

```json
{"id":62,"op":"file_transfer_cancel","session":"s1","transfer_id":"2c0c98db8bfdd7d1"}
{"id":63,"op":"file_transfer_close","session":"s1","transfer_id":"2c0c98db8bfdd7d1"}
```

Cancel is cooperative. A terminal transfer can be closed to release retained
progress/event history. An active transfer cannot be closed.

### FT1 / Chatter boundary

The maintained file protocol is documented in `FILE_TRANSFER.md`. Chatter local
machine framing is `/m1 <BASE64>` as specified in
[CHATTER_MACHINE_PROTOCOL_V1.md](CHATTER_MACHINE_PROTOCOL_V1.md).
Old firmware uses the explicit legacy `/bin <BASE64>` and human BINARY presentation.

Base64 exists only on the local controller boundary. The LoRa BINARY USER and FT1
transport payload are raw bytes up to the profile-advertised capacity (currently 243
bytes for Chatter).

The experimental coordinator uses FT1 v2 and requires both host endpoints updated.
DATA remains transfer_id + uint32 chunk_index, with227 payload bytes at capacity243.
After END, the receiver sends the full missing list back as an internal FT1 file;
that service file can itself be repaired recursively. META carries parent_transfer_id
and depth; END carries repair_id, the child-list identity for that selective pass.
ROOT retains the external lease, with one active leaf and one transport/outbox.
Parent control/idle waits pause during children. Services are not public downloads.

ROOT missing threshold defaults to30% (strictly greater fails); service files are
exempt. Depth1..8 is permitted, needing9 fails. Three consecutive completed repair
cycles without decreased missing count fail; any decrease resets that file's counter.
Snapshots optionally include repair={missing_total,depth,no_progress}; no_progress is
receiver-owned. The sender learns missing_total from each hash-verified full list.
A nested negative RESULT preserves its original remote code in the ROOT sender
failure.details.remote_code; the sender failure.code remains remote_failed.
There is no overall3600 s deadline or fixed8-cycle repair cap in this coordinator.
Unanswered idle control remains bounded by interval/max_control_replays. No per-DATA
FT1 ACK, midstream watchdog, PHY retries or LoRa SACK is implemented.

Explicit file_send_start with unchanged source reuses a matching ROOT journal/ID.
Restart does not restore a nested stack: durable ROOT resume builds a fresh context.
Drain ambiguity retains ownership; close the session before new work. No new JSONL
configuration operation is introduced. Constructor policy defaults and exact wire
layout are documented in FILE_TRANSFER.md; FT1_RESUME.md owns durable-state guarantees.
Full physical recursive repair validation is pending; old stage8 evidence covers v1 only.

A generic `tx_state=unknown` is never blindly resent by `ManagedSession`. FT1 replay
also requires accounting for the previous controller operation. Legacy lost echo or
unresolved pipeline tickets block further BINARY with `local_tx_unsettled` until an
observed controller reset changes the epoch. Host drain/reconnect alone is insufficient.
Restore failures preserve the old terminal record/history; failed lease rollback retains
admission and reports `local_ownership_unsettled` / `resume_rollback_failed`.

## Sweep jobs

Sweep jobs are a generic long-running execution primitive inside the same `serialterminal agent` process. They do not create a second transport/session implementation and do not perform experiment analytics.

A sweep executes exactly the requested ordered Cartesian plan and repetition count. It does not autonomously add repetitions, classify RF quality, or interpret CRC/HDR/retry/ACK quality.

### Start a sweep

Participating sessions must already be open. Discovery and `open` remain ordinary caller-owned API steps.

Generic request shape:

```json
{
  "id":100,
  "op":"sweep_start",
  "adapter":"chatter.reliable_user",
  "sessions":["s1","s2"],
  "plan":{
    "constants":{
      "frequency_hz":470000000,
      "power_dbm":2,
      "bandwidth_hz":500000
    },
    "axes":[
      {"name":"sf","values":[7,8]},
      {"name":"payload_bytes","values":[8,32]},
      {"name":"direction","values":["s1>s2","s2>s1"]}
    ],
    "repetitions":3
  }
}
```

The generic plan accepts only:

```text
constants    object; optional, default {}
axes         ordered array of {name, values}; optional, default []
repetitions positive integer; required
options      adapter-owned object; optional, default {}
```

Axis order defines traversal order. Axis names must be unique, must not collide with `constants`, and every axis must have at least one value.

Current generic admission bounds are:

```text
maximum serialized plan size: 64 KiB
maximum axes:                16
maximum total samples:       100000
maximum sessions in request: 32
```

The sample count is the Cartesian point count multiplied by `repetitions`; oversized plans are rejected synchronously before a job is created.

Only one active sweep is allowed per agent process. A second start while the current job is `running` or `cancelling` returns `sweep_busy`.

A successful start returns promptly:

```json
{
  "id":100,
  "ok":true,
  "result":{
    "sweep_id":"sw1",
    "state":"running",
    "total_samples":24,
    "events":{
      "cursor":0,
      "max_window":100,
      "retention":4096
    },
    "jobs":{
      "max_active":1,
      "max_retained_terminal":16
    }
  }
}
```

The initial response describes job creation, not experiment success. Adapter preparation and execution continue in a background worker.

### Session mutation ownership

A successful `sweep_start` atomically acquires mutation ownership of every declared participating session.

At that same ownership boundary the agent captures a **pre-sweep TX fence** for every participating session. The background job must settle every externally accepted TX through that fence before adapter `prepare` begins. A pre-lease TX with known `written` outcome is allowed to finish before measurement preparation; it is never silently dropped. If the fence cannot settle within its bounded phase, the job fails with `session_fence_timeout`. If any fenced TX reached `tx_state:"unknown"`, the job fails with `session_tx_unknown`; the session must be closed/reopened or otherwise re-established by a higher-level workflow before attempting a measurement. Empty queue depth alone is not treated as proof that an ambiguous TX had no side effect.

While that sweep is active, external mutating operations on an owned session are rejected before side effects, including:

```text
send_line
send_bytes
close
```

The error is `session_busy` and identifies the sweep owner.

Read-only operations such as `status`, `list_sessions` and ordinary `observe` remain available.

Ownership is released when the sweep reaches `completed`, `failed`, or `cancelled`; it is not held until `sweep_close`.

Ownership covers only declared participating sessions. It does not isolate the physical RF environment from unrelated sessions/processes/devices. The caller is responsible for keeping other experiment-affecting transmitters quiescent.

### Observe sweep progress

```json
{
  "id":101,
  "op":"sweep_observe",
  "sweep_id":"sw1",
  "cursor":0,
  "window":1000,
  "timeout_ms":30000
}
```

`cursor` is required and means the last sweep-event sequence already consumed by that reader. The server returns events with `seq > cursor`.

`window` is optional and defaults to the advertised `max_window`. A caller may request a larger number; the server returns at most `max_window` events. There is no `more` flag.

`timeout_ms` is optional and defaults to 0. With a positive timeout, `sweep_observe` long-polls until a new retained sweep event appears, the job becomes terminal, or the timeout expires.

Typical result:

```json
{
  "events":[
    {
      "seq":17,
      "kind":"sample_completed",
      "coordinate":{
        "frequency_hz":470000000,
        "power_dbm":2,
        "bandwidth_hz":500000,
        "sf":8,
        "payload_bytes":32,
        "direction":"s1>s2"
      },
      "repetition":2
    }
  ],
  "cursor":17,
  "head_cursor":19,
  "state":"running",
  "progress":{
    "completed_samples":12,
    "total_samples":24,
    "current":{
      "coordinate":{},
      "repetition":3,
      "phase":"sample_settlement"
    }
  },
  "timed_out":false
}
```

`response.cursor` is the last event returned to this reader. `head_cursor` is the newest event existing in the same coherent job snapshot. If `cursor < head_cursor`, retained backlog exists and the caller may immediately request the next window.

Event sequence is job-local, monotonically increasing and gap-free while retained. Current execution events are mechanical, for example:

```text
sweep_started
coordinate_started
sample_completed
coordinate_completed
sweep_completed
sweep_failed
sweep_cancelled
```

They are not RF-quality classifications.

If retained events are `101..500`, then `oldest_valid_cursor=100`. A request below that boundary fails with `sweep_cursor_expired` and reports `oldest_valid_cursor`, `oldest_retained_event_seq` and `head_cursor`. A cursor newer than the head fails with `invalid_sweep_cursor`.

Cursor, window and timeout use strict integer validation; booleans, floats/strings where integers are required, negative cursors/timeouts, and non-positive windows are rejected.

Job execution failure is not an API request failure. A valid observe of a failed job is still:

```json
{
  "id":101,
  "ok":true,
  "result":{
    "state":"failed",
    "failure":{"code":"adapter_failed","message":"..."},
    "cleanup_failure":{"code":"cleanup_timeout","phase":"cleanup","message":"..."}
  }
}
```

`failure` preserves the primary execution cause. When cleanup also fails, `cleanup_failure` is reported separately instead of overwriting that primary cause. If cleanup is the only failure, it is also the primary `failure`.

Top-level `ok:false` is reserved for request/API errors such as unknown sweep ID, invalid cursor/window/timeout, expired cursor, or an invalid control operation.

### Cancel a sweep

```json
{"id":102,"op":"sweep_cancel","sweep_id":"sw1"}
```

For an active job the immediate response reports `state:"cancelling"`. This acknowledges the cancellation request; it does not claim that an in-flight physical operation was interrupted unsafely.

Maintained adapters are **cooperatively deadline-bounded**: every blocking phase must use the supplied phase deadline/cancellation context. The generic Python worker does not attempt unsafe thread termination of a non-cooperative adapter callback.

The bundled Chatter adapter switches an active sample to a separate short cancellation-settlement budget after `sweep_cancel`; it does not keep waiting through a potentially multi-minute slow-PHY sample budget merely because the cancel response was lost. The job subsequently converges to terminal `cancelled` or, if bounded safe cancellation/cleanup cannot complete, `failed`. Observe the terminal transition with `sweep_observe`.

Calling cancel on an already terminal retained job returns its existing terminal state.

### Close retained job state

```json
{"id":103,"op":"sweep_close","sweep_id":"sw1"}
```

`sweep_close` succeeds only for a terminal job. It releases the retained in-memory job/event/progress state; later operations on that ID return `unknown_sweep`.

Terminal jobs are also globally bounded to the advertised `max_retained_terminal`; the oldest retained terminal job is evicted when the bound is exceeded.

Closing/evicting a job does not remove its already-written forensic `[SWEEP]` records.

### Bundled Chatter reliable-USER adapter

The bundled `chatter` profile registers:

```text
chatter.reliable_user
```

The generic agent/sweep engine does not special-case this name; it resolves adapters through the selected session profiles.

This adapter requires exactly two distinct, already-connected `profile:"chatter"` sessions. Its plan must define these coordinate fields across `constants` and/or axes:

```text
frequency_hz
power_dbm
bandwidth_hz
sf
payload_bytes
direction
```

Current accepted values follow the Chatter firmware contract:

```text
frequency_hz   470000000..510000000 in 1 kHz steps
power_dbm      2..17 or 20
bandwidth_hz   7800, 10400, 15600, 20800, 31250, 41700,
               62500, 125000, 250000, 500000
sf             7..12
payload_bytes  1..200
direction      "<session-a>session-b>" or reverse
```

`plan.options` is currently empty for this adapter.

The Chatter adapter does **not** require a firmware sweep mode. After the generic pre-sweep TX fence has settled, the host-side adapter uses only existing Chatter control commands to establish a quiet diagnostic baseline on both participating sessions:

```text
/cancel all
/diag off
/heartbeat off
/echo-loop stop
/echo        only when /help reports echo=ON
/both
```

The active `SweepJob` plus SerialTerminal session ownership is the sweep mode: external `send_line`, `send_bytes` and `close` are blocked on participating sessions, while the profile-owned adapter alone may submit control commands and measured USER traffic through its capability-limited context. No firmware command, scheduler state, wire flag or protocol token named "sweep" is required.

This host-side isolation cannot prevent RF generated independently by firmware in response to unrelated over-the-air traffic. The operator/coordinator must therefore use a quiet measurement frequency/environment and keep unrelated nodes quiescent. Third-party RF is measurement contamination, not something SerialTerminal can classify as sweep/non-sweep traffic.

For each coordinate the adapter applies and verifies requested radio configuration before sampling. For each repetition it submits exactly one reliable USER and waits for that operation to settle before any next sample or radio-configuration mutation. Host `queued`/`written` state alone is never treated as device/RF settlement.

The adapter may parse delivery telemetry to synchronize execution, but generic sweep events do not classify ACK/retry/CRC/HDR/RSSI/SNR quality. Detailed interpretation remains a caller/reviewer task using the forensic log.

On normal completion or cancellation cleanup, the adapter sends `/cancel all` to every participating session and waits within the bounded cleanup phase for delivery cancellation/settlement evidence. Background modes that preparation forced OFF are not silently re-enabled; after the job releases session ownership, ordinary SerialTerminal control is available again.

## Concurrent JSONL behavior

`observe` and `sweep_observe` are asynchronous long-polls. Ordinary JSONL requests are handled by the main reader while those waits remain pending; a running sweep also has its own background worker, with participating-session mutations protected by the sweep ownership gate.

Example:

```text
id=100 sweep_observe(sw1) -> pending
id=101 status(s1)          -> response 101
id=102 list_sessions       -> response 102
... sweep event ...        -> response 100
```

Multiple `observe`/`sweep_observe` requests may pend under different IDs. stdout JSON lines are serialized and cannot interleave. `[AGENT RESPONSE]` ordering in the forensic log matches stdout response ordering. Completed async observation worker objects are removed from runner bookkeeping; a long-lived process retains only currently active/pending observation workers rather than the historical thread list.

Continuous observation means issuing a new `observe` or `sweep_observe` after each response using the returned cursor(s); there is no unsolicited push.

## Close and shutdown

```json
{"id":30,"op":"close","session":"s1"}
```

EOF/process shutdown cancels pending session observations, requests cancellation of an active sweep, gives bounded sweep workers a chance to settle, force-closes remaining sessions, then joins sweep/observe workers while logs/stdout are still available. A pending ordinary `observe` cancelled by process shutdown may return structured `agent_stopping`.

For FT1, EOF closes the file manager through its bounded suspension path: receiver partial bytes/durable ranges and sender journal remain eligible for same-transfer resume. It does not invoke `file_transfer_cancel`. Explicit `file_transfer_cancel` retains its cancellation/cleanup semantics. Shutdown failure is reported separately; a manifest alone does not prove retained bytes.

## Multiple devices

A single process may keep independent sessions open simultaneously:

```text
discover
open Device A profile=generic -> s1
open Device B profile=chatter -> s2
send/observe using {s1,s2}
close s1
close s2
```

SerialTerminal assigns no application-specific roles or acceptance rules. Those belong in the consuming project skill/test scenario.

## Architecture boundary

```text
Codex / future MCP / scenario runner
        ↓
JSONL adapter / future MCP adapter
        ↓
SessionManager
        ↓
ManagedSession
        ├─ raw SessionEvent ring ────────> observe(include_events=true).result.events
        └─ canonical logical lines ──────> observe.result.lines
                                      └──> human-console companion logger
        ↓
Transport abstraction
        ↓
SerialTransport / BleNusTransport / BluetoothSppTransport
```

The agent layer must not directly open serial ports, create Bleak clients, or create RFCOMM sockets. A future adapter or broad autonomous test harness should wrap the same `SessionManager`/JSONL contract instead of duplicating transport/session logic.


### FT1 forensic log records

Primary interactive and agent logs include payload-free `[FT1]` records for lifecycle
and local binary-send stages. Records identify transfer, direction, message type and DATA
`chunk_index` where applicable; raw FT1 bytes/base64 are not included. Agent records also
include the owning session id. This logging is diagnostic only and does not change
file-transfer state.


### BLE target absent: operator-authorized recovery through USB

A target missing from BLE discovery is not proof of a failed node or a LoRa radio
failure. A connected peripheral may stop advertising. On Linux, check both the
local SerialTerminal processes and BlueZ's connection state for the target:

```bash
pgrep -af 'serialterminal.py'
bluetoothctl info <target-BLE-address>
busctl --system list --no-pager
```

Inspect matching command lines/PIDs rather than killing by name. No live ST
process does not prove that the node is free: another client may own it, or a
connection may remain after ST exits. `Connected: yes` does not identify the
application that originally opened it. Do not kill unrelated clients, restart
BlueZ or reset the adapter as automatic recovery.

When the operator authorizes USB access and a node reboot, use this procedure:

1. Start one persistent interactive ST agent with a fresh unique `--log` path;
   retain its PID. Keep stdin open through discovery, access and cleanup.
2. Discover serial devices in that process, using the node's known runtime baud:

   ```json
   {"id":1,"op":"discover","scope":"serial","baud":921600}
   ```

   `921600` is the tested Chatter runtime baud, not a universal serial default.
   Open the exact returned USB `device_key` with `profile:"generic"`. This sends
   no controller preamble and leaves BLE ownership untouched.

   ```json
   {"id":2,"op":"open","device_key":"<returned-USB-device-key>","profile":"generic"}
   ```

3. Save the returned session and `latest_seq`. Send `/id`, then observe from that
   cursor and require the intended node's identity before rebooting. `/config`
   can record the existing radio/link state. These are Chatter-specific commands;
   the generic API does not supply or interpret a reboot command for arbitrary
   devices. Use the returned session instead of assuming it is `s1`.
4. With reboot authorization and no active work that must be preserved, send one
   `/reboot` through the USB session:

   ```json
   {"id":3,"op":"send_line","session":"s1","text":"/reboot"}
   ```

   Observe incrementally with the actual returned cursors. A queued/written
   response is not reboot confirmation: require `[SYS] REBOOTING`, subsequent
   `[SYS] CHATTER READY`, and a fresh `/id` response. Boot-time serial bytes may
   be undecodable at the runtime baud; preserve them in the forensic log without
   treating them alone as a failed boot. If confirmation is absent, report the
   boundary instead of sending repeated reboots blindly.
5. Run BLE discovery in the same ST process after the node is ready:

   ```json
   {"id":4,"op":"discover","scope":"ble","scan_seconds":5}
   ```

   Require the intended target in the returned candidates. USB responsiveness
   and restored BLE visibility are separate results; neither proves successful
   LoRa delivery or fixes the unknown cause of the previous connection.
6. Close the USB session, consume the close response, then end agent stdin
   normally and verify that the retained PID exited. Preserve all three logs:
   `.log`, `.console.log`, and `.fttiming.jsonl`. The timing companion is finalized
   during graceful shutdown; a crash may prevent its completion. Record the
   pre-reboot state, authorization, identity, reboot evidence and post-reboot
   discovery in the experiment description.

This procedure was verified on a Chatter node that was absent from ST BLE discovery
while BlueZ reported `Connected: yes` and no live ST process was found. USB `/id`
responded, the authorized `/reboot` reached READY, and subsequent BLE discovery
returned the node. The original connection owner/cause was not established.


### Busy serial target

POSIX serial sessions request exclusive tty ownership. If another cooperating
SerialTerminal process already owns the same port, the session remains in reconnect
state and emits one deduplicated raw `error` event for that failure epoch with
`state="connect-failed"` and text `serial device busy: <path>`. It may connect later
after the other owner releases the port; no second SerialTerminal reader is allowed
to consume the same serial byte stream concurrently.

Protected Chatter recovery: an addressed full-credit STATUS for a pending SUBMIT,
or LINK_OK/LINK_FAIL for a later pending SUBMIT in the same epoch, schedules one
cached local QUERY for an earlier missing terminal outcome after 100 ms. Lost
ACCEPTED/TX_DONE do not disable this recovery. Unowned request/old-epoch frames
cannot schedule it. These hints are not success evidence: each ticket settles
only from its own correlated outcome, and RF SUBMIT is not repeated. UNKNOWN
remains unresolved and blocks new submissions. The original bounded deadline
fallback remains if this diagnostic query cannot recover a terminal result.

Same-epoch WELCOME after reconnect preserves the Chatter request counter; fresh
epoch starts a new counter. This prevents new payloads from reusing retained cache
identities after a live USB controller reconnect.


## Application error log and interactive errors

Each CLI process also creates `logs/serialterminal-application-<timestamp>-p<pid>.log`
in the working directory, independently of session `--log`. It records start/stop, TUI cancel/manager-close/session-replacement phases and
application errors with full Python traceback. Error records are immediately flushed
and fsynced; they do not wait for process close or the timing writer. Unhandled thread
exceptions and caught session/FT1 worker failures use this same log. A logger I/O
failure is reported briefly to stderr; successful persistence is not claimed.

TUI action errors keep the screen open and light a white-on-red `ERROR` badge in the
upper-right corner. Status contains a short error and application log path; an action
that failed is not automatically repeated. Ctrl+C remains an ordinary quit, without
printing a traceback. Cleanup attempts all resources independently; cleanup failures
are logged as errors. A fatal CLI/frontend error outside a recoverable TUI action
returns1 with a short log-path notice, without traceback text on stderr. Ctrl+C at the
CLI boundary returns130. Neither Python catch nor cleanup can run after SIGKILL.
