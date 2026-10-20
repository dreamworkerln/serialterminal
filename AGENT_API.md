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

Prototype BLE discovery returns all devices seen by the active scan, plus currently connected BlueZ Device1 objects on Linux, including devices without fresh advertising. Results are deduplicated by the existing address-based `device_key`. BLE entries include `busy:true|false`; connected BlueZ entries have a plain ` (busy)` suffix in `label`. Human menus render that suffix yellow on a TTY; JSON never contains ANSI styling. Only currently connected BlueZ objects receive this marker; cached disconnected objects are not marked busy. Visibility does not prove NUS capability. The separate capability scanner/prober and its cache retain definitive NUS knowledge; advertised names and controller profiles do not whitelist a device.

Discovery does not disconnect devices. If active scan fails but connected BlueZ objects are available, discovery returns those objects and logs the scan failure. If BlueZ enumeration is unavailable, ordinary scan results remain available and the enumeration failure is logged. The known-device chooser refreshes BlueZ connection state without an active scan.

Human `--profile chatter` applies a separate chooser policy: BLE candidates require
advertised NUS or confirmed NUS cache evidence, including known-device/F2 lists
after profile switches. `generic` human selection and JSONL `discover` keep the
all-device behavior above. Selecting `profile:"chatter"` in `open` configures that
session; it does not filter the process's discovery results.

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

Selecting a BLE candidate marked `busy` explicitly requests takeover: before its first normal scan/connect, the transport reads the selected exact BlueZ Device1 path, disconnects it if still connected, and verifies release. This also disconnects any other application using that same device. Other device addresses are untouched. If release cannot be confirmed, no normal connect is attempted; the session stays `reconnecting` with an actionable `connect-failed` event, and release may be retried. After confirmed release the takeover marker is consumed: subsequent ordinary reconnects do not repeat it. A busy singleton in the human chooser requires explicit selection. Existing same-process `device_busy` session ownership remains enforced. There is no PID registry or cross-process ownership arbitration.

The `generic` profile sends no controller preamble. Generic BLE uses standard NUS: `0002` write and `0003` receive stream `main`.

Bundled controller profiles are explicit, for example:

```json
{"id":3,"op":"open","device_key":"ble-address:...","profile":"chatter"}
```

The Chatter profile supplies its controller preamble (including `/id`) and profile-defined BLE receive layout (`chat` plus optional `telemetry`). Profile selection is per session, not process-global. One process may hold sessions with different profiles simultaneously.

The human Chatter TUI additionally retries a missing USB identity response at
1-second intervals, at most three times after its Serial preamble, stopping on
canonical NODE. This is profile-owned human presentation initialization; JSONL
`open`/session initialization does not add these retries or change its schema.

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

Snapshots include `elapsed` seconds from the current runtime attempt's start;
it increases while active and freezes when terminal. Terminal snapshots may additionally
include `final_path` or structured `failure` with stable `code`, human `message`,
optional `phase` and details.

`file_send_start` rejects a basename exceeding the selected transport's META UTF-8
budget before preparation, reservation, claim or sender-journal lookup with
`filename_too_long` (`filename_bytes`, `max_filename_bytes` details). Chatter currently
allows 162 UTF-8 bytes including extension. The name is never truncated or renamed.
This adds no exception to agent session mutation ownership. Human TUI presentation
controls are a separate frontend/profile contract; agent `send_line`/`send_bytes`
remain rejected while file mutation ownership is held.
`/clear` is reserved locally by the TUI as F4's chat/scrollback clear, including during
active FT1. It sends no device command and adds no agent operation or exception to
agent `send_line` ownership/forwarding semantics.

TUI ROOT terminal events additionally produce a human chat summary and a LOCAL
primary-log record; this is frontend presentation, not a new JSONL outcome or proof
beyond the existing FT1 terminal contract.
The TUI also summarizes ROOT start/phase/recovery/resume/cancel-request/suspension
events. Its process-local attempt/ownership metadata is supplied separately by the
manager's `presentation_snapshot()` and is not added to JSONL transfer/status/history
snapshots. TUI background/close/reopen actions do not change agent mutation ownership.

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

Cancel is cooperative.
The existing negative `RESULT` with `code:"cancelled"` is an explicit peer abort,
accepted symmetrically from TX or RX and mapped to the matching ROOT and descendants.
It uses cooperative cancellation/cleanup, is idempotent and is not echoed back.
Unknown or already-terminal transfers ignore it. Other negative RESULT codes retain
`remote_failed` semantics and resumable sender journals. No new wire message or
firmware command is required. A `transfer_cancelled` event includes optional
`cancelled_by_peer:true|false`; process-local presentation carries the same origin
for TUI wording. Local acceptance still does not prove peer receipt.

A terminal transfer can be closed to release retained
progress/event history after ownership and terminal settlement finish. An active
or still-settling transfer returns `file_transfer_active`; retry close after
settlement. Unresolved ownership requires session close.

### FT1 / Chatter boundary

The maintained file protocol is documented in `FILE_TRANSFER.md`. Chatter local
machine framing is `/m1 <BASE64>` as specified in
[CHATTER_MACHINE_PROTOCOL_V1.md](CHATTER_MACHINE_PROTOCOL_V1.md).
Old firmware uses the explicit legacy `/bin <BASE64>` and human BINARY presentation.

Base64 exists only on the local controller boundary. The LoRa BINARY USER and FT1
transport payload are raw bytes up to the profile-advertised capacity (currently 243
bytes for Chatter).

The experimental coordinator uses FT1 v3 and requires both host endpoints updated.
DATA remains transfer_id + uint32 chunk_index, with227 payload bytes at capacity243.
After END, the receiver sends the full missing list back as an internal FT1 file;
that service file can itself be repaired recursively. META carries parent_transfer_id
and depth; END carries repair_id, the child-list identity for that selective pass.
Service META also carries previous_repair_id: it must answer the parent's latest
END repair_id. Each parent holds at most one queued verified repair request and
one completed child META for replay; older children are rejected after eviction by
this link. Slow useful progress has no total cycle limit. Settled ROOT frames retire;
retained terminal records and completed tombstones own late completion replies.
ROOT retains the external lease, with one active leaf and one transport/outbox.
Parent control/idle waits pause during children. Services are not public downloads.

ROOT missing threshold defaults to30% (strictly greater fails); service files are
exempt. Depth1..8 is permitted, needing9 fails. Three consecutive completed repair
cycles without decreased missing count fail; any decrease resets that file's counter.
Snapshots optionally include repair={missing_total,depth,no_progress}; no_progress is
receiver-owned. The sender learns missing_total from each hash-verified full list.
A nested negative RESULT preserves its original remote code in the ROOT sender
failure.details.remote_code; the sender failure.code remains remote_failed.
A negative remote RESULT other than explicit `code:"cancelled"` also interrupts cancellation-aware binary send,
controller-readiness and pipeline submit/settle waits. It does not set the operator
cancel event: the outcome stays `remote_failed` and the sender journal is retained.
Owned pipeline cleanup/drain still runs; an ambiguous drain retains the lease and
a secondary cleanup error does not replace the original remote failure. A backend
that ignores the supplied stop signal keeps its own blocking-call limitation.
There is no overall3600 s deadline or fixed8-cycle repair cap in this coordinator.
Unanswered idle control remains bounded by interval/max_control_replays. No per-DATA
FT1 ACK, midstream watchdog, PHY retries or LoRa SACK is implemented.

Explicit file_send_start with unchanged source reuses a matching resumable ROOT
journal/ID. Remote wire/original hash, decompression, invalid_chunk quarantine and
invalid_metadata identity failures durably mark the journal terminal, so the next
explicit start allocates a fresh ID. Other resumable timeout/restart outcomes keep
the existing identity; remote_code is preserved even for early META rejection.
Matching RX META during timeout settlement is coalesced and retried by RX after
drain, ownership release and recursive cleanup; RX does not wait for transport.
Unsettled ownership or a competing active transfer returns `busy`, preserving the
resumable identity. Queue failure is observable as `meta_replay_failed`; close
does not reopen deferred transfers. See FT1_RESUME.md for the recovery contract.
An exactly matching valid receiving/suspended RX manifest with an absent `.part`
automatically resets to durable zero proof and returns `RESUME 0` for the same ID.
`resume_state_reset` records `reason:missing_partial`, `previous_chunks` and
`next_chunk:0`. No client cleanup or new request flag is needed. Existing partials,
publishing/quarantined state, conflicting identities and unsafe paths are not reset.
Concurrent final files sharing a basename are published under distinct names through
POSIX namespace coordination, durable publishing-intent reservation and exclusive
publication. Existing final files are never overwritten. RX restore rolls durable
and runtime state back before releasing its lease; failed durable rollback keeps
admission blocked. Invalid cancel IDs return invalid_transfer_id.

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
For a confirmed missing-part reset, preserved history does not restore old progress:
rollback and shutdown retain zero proof because the old bytes are absent.

## Sweep jobs

Sweep jobs are a generic long-running execution primitive inside the same `serialterminal agent` process. They do not create a second transport/session implementation and do not perform experiment analytics.

A sweep executes exactly the requested ordered Cartesian plan and repetition count. It does not autonomously add repetitions, classify RF quality, or interpret CRC/HDR/retry/ACK quality.

### Start a sweep

Examples below require an adapter supplied by a participating profile. The old
`chatter.reliable_user` is deprecated and rejected before device operations.

Participating sessions must already be open. Discovery and `open` remain ordinary caller-owned API steps.

Generic request shape:

```json
{
  "id":100,
  "op":"sweep_start",
  "adapter":"project.measurement",
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

### Deprecated Chatter reliable-USER adapter

`chatter.reliable_user` is **DEPRECATED / disabled**. Its registered factory returns
`deprecated_sweep_adapter` before creating a job, acquiring mutation ownership or
sending commands. The old preflight requires `/echo-loop stop` and `echo=...` in
`/help`, which current firmware no longer provides. There is no bundled replacement.
Do not bypass the guard by constructing the legacy class. The old implementation
remains only for comparison; direct-class tests do not establish current-firmware
compatibility. Generic sweep machinery remains available for supported adapters
registered by participating profiles. `project.measurement` in the schema example
is illustrative, not a provided adapter.

## Close and shutdown

```json
{"id":30,"op":"close","session":"s1"}
```

EOF/process shutdown cancels pending session observations, requests cancellation of an active sweep, gives bounded sweep workers a chance to settle, force-closes remaining sessions, then joins sweep/observe workers while logs/stdout are still available. A pending ordinary `observe` cancelled by process shutdown may return structured `agent_stopping`.

For FT1, EOF closes the file manager through its bounded suspension path: receiver partial bytes/durable ranges and sender journal remain eligible for same-transfer resume. It does not invoke `file_transfer_cancel`. Explicit `file_transfer_cancel` retains its cancellation/cleanup semantics. Shutdown failure is reported separately; a manifest alone does not prove retained bytes.

### Verified BLE release on close

For BLE sessions, `close` additionally returns `transport_release`. `state:"closed"`
means the local session was closed; only `transport_release.result:"disconnected"`
confirms backend release at the verification boundary. Other transports may omit
this optional field. Example:

```json
{"session":"s1","state":"closed","transport_release":{"backend":"bluez","result":"disconnected","device_path":"/org/bluez/hci1/dev_AA_BB_CC_DD_EE_FF","connected_before":true,"connected_after":false,"forced":true,"generation":1,"cleanup_errors":[]}}
```

BLE cleanup bounds notification shutdown and Bleak disconnect separately. For a
BlueZ client it then reads `org.bluez.Device1.Connected` through a fresh system-bus
connection, using the exact client object path captured before cleanup. If still
connected and the client was connected when cleanup began, it issues one targeted
`Disconnect` and checks the property again. An already disconnected/stale client
cannot authorize a forced disconnect of a connection another application may have
opened. Missing/unusable client path, access errors and timeouts remain explicit
`failed`/`unknown`; local Bleak flags do not substitute for BlueZ verification.
A removed Device1 object counts as disconnected. Non-BlueZ backends report the
client's state under `backend:"bleak"`, without claiming independent host proof.

The report includes intermediate cleanup errors even if the final release succeeds.
It is saved in a `ble_release` timing event and the application log. Session stop
also emits a `transport-release` state/error event into the forensic log before
closing it. On unconfirmed release, stderr and the application error log report the
failure. Other sessions still receive cleanup. EOF has no `close` response: use the
saved reports, not process exit code alone, to establish release.

Lifecycle serialization and close admission prevent an old cleanup from releasing
an ST replacement generation or a late connect from publishing after permanent
close. Shutdown normally has an 8-second BLE cleanup wait per transport, with
separate 1-second notification, 2-second disconnect and 3-second BlueZ verification
budgets; failures remain observable rather than implying success.

This covers graceful shutdown only. SIGKILL/power loss cannot execute Python cleanup.
Connected BlueZ devices are included in discovery as `busy`; explicitly selecting
one requests the targeted disconnect-before-connect described under Open.
Discovery does not disconnect devices or classify connections as orphaned. No
adapter restart, device removal/unpair or PID-based ownership registry is used.

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

With `--log /path/test.log`, each CLI process also creates `/path/test.application.log`
next to the primary, console and timing logs. The same basename rule applies without
an extension: `--log /path/test` produces `/path/test.application.log`.
Without `--log`, the application log defaults to
`logs/serialterminal-application-<timestamp>-p<pid>.log` in the working directory.
It opens before frontend startup and records start/stop, TUI cancel/manager-close/session-replacement phases and
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

## FT1 host metadata bounds

Host metadata resource policy: received chunks are stored as canonical intervals,
not one dictionary entry per chunk. Defaults are65,536 received intervals and4 MiB
per JSON manifest; manager constructor overrides are `max_received_ranges` and
`max_manifest_bytes`. A fragment that would exceed the interval limit fails with
`storage_failed` before writing that DATA, preserving the useful partial and map.
Large manifest reads are bounded and oversized documents are not accepted/written.
LIST has at most `max_received_ranges + 1` ranges, validated before allocation;
service META size is bounded by that representation before decompression. These
limits do not cap sequential file size or the number of successful repair cycles.

Within a live ROOT each creator allocates monotonic child IDs from a random seed;
ROOT receiver uses odd IDs and ROOT sender even IDs. Durable IDs and live contexts
are skipped, and creation is protected by namespace lock plus outgoing lease.
This permits bounded replay history without reusing evicted child identities.

## Live cyclic partial retention

Cyclic retention runs on durable saves/checkpoints, admission and ownership release;
partial growth checks the shared logical byte budget before writing. Defaults:
7 days since state update,32 incoming,32 outgoing,64 completed tombstones and1 GiB
of `.part` files per receive directory. Count/TTL eviction skips active leases,
including another process and the pre-manifest window. Counts include live
identities without a manifest; a new admission fails explicitly if all slots are live.
Under byte-budget or filesystem-free-space pressure, the oldest inactive parts
and their manifests are removed automatically. ENOSPC/EDQUOT during an idempotent
write/checkpoint/publication is retried only after an actual eviction, so retry
is finite. The namespace lock covers capacity checks and the write across processes.
If nothing eligible remains, the transfer fails with storage_failed; it retains
the last useful partial and received proof. Partial writes never advance that proof.
Final downloaded files and user source files are never eviction candidates.
No periodic cleanup timer or `/clean` command is added. Active data alone can
exhaust the budget; the1 GiB storage budget still applies to growing wire files.

## FT1 chunk-space admission

META-derived chunk_count is computed with integer ceiling division and must fit
0..0xffffffff, matching END.chunk_count and RESUME.next_chunk. Invalid wire_size
or chunk_size is rejected before RX records, leases, part files or recursive frame
admission with RESULT invalid_metadata. The sender checks its actual prepared
wire stream before journal/META and reports invalid_metadata if unrepresentable.
Exactly0xffffffff chunks is representable (last DATA index0xfffffffe); larger
counts are rejected without allocating a chunk bitmap. No smaller protocol file
limit or new wire layout is introduced; separate storage/RAM budgets still apply.

## Outgoing peer binding

Outgoing journals and leases are scoped by a stable `peer_key`, stored in each
journal and represented by a SHA-256 filename prefix. Agent uses the selected
`open.device_key`; TUI uses the selected transport's device_key. Generic layers
pass an opaque identity string and do not recognize controller names or key
prefixes. In the fixed two-radio topology this binds work to the local radio path;
it does not discover or authenticate a remote RF peer. Changing remote topology
requires a new binding rather than assuming this key proves remote identity.
The same explicit key supports reconnect/process-restart resume; different keys,
including USB/BLE paths with distinct keys, never merge automatically.

Candidate selection, journal update and deletion verify the binding. Two peer
keys can use the same source and transfer_id without sharing a journal or lease.
Same-key concurrent owners of one identity are rejected until the lease releases.
Global outgoing count/TTL still applies across namespaces and preserves live
scoped leases. Old unbound journals are retained for normal retention/inspection
but are not automatically assigned to a peer. Standalone managers without an
explicit key get a per-instance volatile binding: same-instance retry works,
but another instance cannot claim that anonymous sender journal for restart resume.
A cancellation that cannot safely delete its bound journal reports
local_ownership_unsettled and keeps admission until close rather than deleting
foreign state. Incoming wire layout and firmware behavior are unchanged.

## Timing correlation across appended sessions

Timing rows now contain an authoritative UUID `segment_id` per TimingTrace
instance. Correlate with `(segment_id, seq)`; seq is monotonic within that segment,
not across the whole appended file. TUI session/profile replacement and process
reopen preserve old records and create a new segment. Cooperating POSIX writers
serialize each batch through flush. A truncated historical tail is preserved and
separated by LF so it cannot absorb the next valid JSON record; malformed old
fragments remain evidence gaps. Legacy rows without segment_id are unchanged and
do not acquire a fabricated unique key. Clocks, bounded256/8 batching, close-tail
flush and application-log error reporting remain as described in LOGGING.md.

On platforms without POSIX flock/pread, the single-writer path remains available;
cooperating cross-process serialization is guaranteed on POSIX only.
