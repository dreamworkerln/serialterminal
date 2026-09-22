# SerialTerminal agent interface

`serialterminal agent` is the canonical local machine-facing JSON Lines frontend over the same discovery, transports and reconnect/session core used by the human terminal.

The interface is intentionally generic. Firmware/project-specific scenarios and acceptance rules belong in consuming skills. Controller-specific behavior is selected explicitly per session through `profile`; the default is `generic`.

## Start and JSONL rules

```bash
python3 serialterminal.py agent
```

Use the privileges required by the host serial/Bluetooth environment.

The process reads one JSON object per stdin line and writes one correlated JSON response per request. It emits no unsolicited JSON events. `observe` may remain pending while later ordinary requests are accepted, so stdout response order is not globally request order; correlate by `id`.

Success envelope:

```json
{"id":1,"ok":true,"result":{}}
```

Error envelope:

```json
{"id":1,"ok":false,"error":{"code":"unknown_session","message":"unknown session: s1"}}
```

`observe` is asynchronous at the JSONL frontend and requires a non-null `id`. Do not reuse an ID while an `observe` with that ID is pending. Duplicate use returns `request_id_busy` without cancelling the original request.

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
```

`observe` is the only receive/cursor operation. Historical `events` and `wait_events` operations are removed and return `unknown_operation`.

## Run logs

The companion human-console record format is shared with the interactive frontend and is specified in `LOGGING.md`. The agent's primary `.log` remains the stronger forensic/API/transport record described below.

Every agent process creates a paired forensic and human-console log unless an explicit forensic path is supplied:

```text
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.log
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.console.log
```

With:

```bash
python3 serialterminal.py agent --log /tmp/serialterminal-agent.log
```

the companion is `/tmp/serialterminal-agent.console.log`.

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
```

Raw RX records preserve event `seq`, stream, transport/session chunk boundaries, incremental decoded `text`, and byte-accurate `data_b64`. There are no separate forensic `[RX LINE]` or `[RX PARTIAL]` records.

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

Startup `[AGENT]` metadata records both paths.

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

Optional `baud` and `scan_seconds` may be supplied.

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
```

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

A transport may instead report an ambiguous write outcome. BLE GATT write timeout is the current example: cancellation can be requested, but SerialTerminal cannot prove that the backend/native side effect did not already occur. The session then records:

```json
{"kind":"tx","tx_id":12,"tx_state":"unknown"}
```

and an associated error event with:

```json
{"kind":"error","tx_id":12,"state":"send-outcome-unknown"}
```

`tx_state:"unknown"` is terminal for that queued item: SerialTerminal does **not** automatically resend it after reconnect because doing so could create a duplicate side effect. A machine scenario must decide success/failure from later application/protocol evidence or classify the case as ambiguous/inconclusive. Do not reinterpret `unknown` as either `written` or definitely-not-written.

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

`cursors` is required and non-empty. Each value is the last raw `SessionEvent.seq` already processed for that session. Sequence spaces are independent per session. There is intentionally one raw cursor model and no separate line cursor.

Result shape:

```json
{
  "events":[...],
  "lines":[...],
  "cursors":{"s1":44,"s2":75},
  "timed_out":false
}
```

`events` are forensic raw session events (`state`, `tx`, `rx`, `error`). Exact bytes are in `data_b64`. BLE notifications remain transport-sized chunks; SerialTerminal does not make transports pretend to be line-oriented.

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
firmware/protocol reasoning   -> result.lines
transport/chunk forensics     -> result.events / data_b64
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

`timeout_ms:0` returns an immediate snapshot. If no event exists, `timed_out:false` with empty arrays.

A positive timeout long-polls until the first new raw event on any watched session. If nothing arrives by expiry, it returns empty arrays with `timed_out:true`.

If an event arrives without completing a logical line, the request returns immediately with non-empty `events` and possibly empty `lines`; issue the next `observe` using returned cursors.

There are no receive filters in `observe`; callers may filter returned arrays.

## Concurrent JSONL behavior

Only `observe` is asynchronous. Ordinary commands are serialized by the main reader, preserving mutation order while one or more observations remain pending.

Example:

```text
id=100 observe(s1,s2) -> pending
id=101 send_line(s1)  -> response 101
id=102 status(s1)     -> response 102
... event on s2 ...   -> response 100
```

Multiple observations may pend under different IDs. stdout JSON lines are serialized and cannot interleave. `[AGENT RESPONSE]` ordering in the forensic log matches stdout response ordering.

Continuous observation means issuing a new `observe` after each response using the returned cursors; there is no unsolicited push.

## Close and shutdown

```json
{"id":30,"op":"close","session":"s1"}
```

EOF/process shutdown cancels pending observations, allows correlated shutdown responses, then closes remaining sessions while logs/stdout are still available. A pending observation cancelled by process shutdown may return structured `agent_stopping`.

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
        ├─ raw SessionEvent ring ────────> observe.result.events
        └─ canonical logical lines ──────> observe.result.lines
                                      └──> human-console companion logger
        ↓
Transport abstraction
        ↓
SerialTransport / BleNusTransport / BluetoothSppTransport
```

The agent layer must not directly open serial ports, create Bleak clients, or create RFCOMM sockets. A future adapter or broad autonomous test harness should wrap the same `SessionManager`/JSONL contract instead of duplicating transport/session logic.
