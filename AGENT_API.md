# SerialTerminal agent interface

`serialterminal agent` is a local machine-facing JSON Lines frontend over the same discovery, transports and reconnect/session logic used by the normal human terminal.

It is intentionally generic. Device-, firmware- and project-specific test scenarios belong in consuming agent skills, not in this API.

## Start

Run this tool with elevated privileges when the host Bluetooth/serial environment requires them:

```bash
python3 serialterminal.py agent
```

The process reads one JSON object per line from stdin and writes exactly one JSON response per request to stdout.

`observe` requests may remain pending while later ordinary requests are accepted. Responses are therefore correlated by `id` and are not globally guaranteed to appear in request order.

SerialTerminal does not emit unsolicited JSON event messages on stdout. Every stdout line is a response to a request.

## Run logs

By default every agent process creates a paired forensic log and human-console companion log with the same timestamp/PID prefix:

```text
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.log
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.console.log
```

An explicit forensic path can be supplied:

```bash
python3 serialterminal.py agent --log /tmp/serialterminal-agent.log
```

Its companion path is derived from that path:

```text
/tmp/serialterminal-agent.console.log
```

The main `.log` is the forensic/API/transport truth. Its chronological records include:

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

There are no separate `[RX LINE ...]` or `[RX PARTIAL ...]` records in the forensic log. Raw `[RX <stream>]` records preserve transport/session chunk boundaries, raw event `seq`, incremental chunk-level `text`, and byte-accurate `data_b64`.

The companion `.console.log` is only a human-oriented presentation/audit view. Records look like:

```text
2026-09-05T08:23:01.100+00:00 [s1] [I] /both
2026-09-05T08:23:01.420+00:00 [s1] [O] [SYS] OUTPUT BOTH
2026-09-05T08:23:05.100+00:00 [s2] [I] hello
2026-09-05T08:23:06.750+00:00 [s2] [O] < [-33/+10 Q100] hello
```

Semantics:

- `[I]` is text accepted through `send_line` for that session;
- `[O]` is a completed logical line from that session's human-console RX stream;
- firmware-owned leading `>` / `<` remain part of the firmware line itself and are not replaced by the host-side `[I]` / `[O]` markers;
- all sessions share one chronological companion file and every record contains its session ID;
- `send_bytes` is not represented as ordinary human input;
- the companion log is presentation/audit convenience, not transport-write or protocol-delivery evidence.

For BLE, the separate machine telemetry stream is **not** written to `.console.log` merely because SerialTerminal is subscribed to it. The BLE human-console/chat stream is written. If firmware output mode such as `/both` causes telemetry text to appear in the human-console stream itself, that line naturally appears in `.console.log` because it is what a human console would have received.

Console RX lines come from the same canonical `ManagedSession` logical-line model used by `observe.result.lines`; there is no second line assembler in logging.

The forensic startup `[AGENT]` ready record contains both paths:

```json
{
  "event":"ready",
  "log_path":"logs/serialterminal-...-pPID.log",
  "console_log_path":"logs/serialterminal-...-pPID.console.log"
}
```

Both files are opened and closed with the same `RunLog` lifetime.

## Response envelope and request IDs

Success:

```json
{"id":1,"ok":true,"result":{}}
```

Error:

```json
{"id":1,"ok":false,"error":{"code":"unknown_session","message":"unknown session: s1"}}
```

For ordinary synchronous operations, `id` is copied from the request and may be any JSON value.

`observe` is asynchronous at the JSONL frontend and requires a non-null request `id`. Clients should use unique IDs and must not reuse an ID while an `observe` request with that ID is still pending.

A request that reuses an ID owned by a pending `observe` is rejected without cancelling the original request:

```json
{
  "id":100,
  "ok":false,
  "error":{
    "code":"request_id_busy",
    "message":"request id is already pending: 100",
    "details":{"id":100}
  }
}
```

Once the pending request finishes, that ID is no longer busy. Monotonically increasing IDs are recommended because they simplify correlation and log inspection.

A positive observation timeout expiring without a new raw event is not an error; the response has `timed_out:true`.

## Operations

The machine-facing operations are:

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

`observe` is the only receive/cursor operation. The former machine operations `events` and `wait_events` are removed and return `unknown_operation`.

The cursor shape is always a `cursors` object, including when exactly one session is watched.

## Device discovery

Request:

```json
{"id":1,"op":"discover","scope":"auto"}
```

Supported scopes:

```text
auto
serial
ble
spp
```

Optional discovery settings:

```json
{"id":1,"op":"discover","scope":"serial","baud":115200,"scan_seconds":3.0}
```

Example response:

```json
{
  "id":1,
  "ok":true,
  "result":{
    "devices":[
      {
        "key":"ble-address:...",
        "kind":"ble",
        "label":"BLE Device",
        "detail":"..."
      }
    ]
  }
}
```

`device_key` is the existing SerialTerminal sticky physical identity. The agent frontend does not create a second identity system.

## Open a long-lived session

```json
{
  "id":2,
  "op":"open",
  "device_key":"ble-address:..."
}
```

The returned `session` remains alive until `close` or process exit. Its internal `ManagedSession` keeps retrying the same physical target after a disconnect.

Default open behavior:

```text
eol=lf
auto_id=true
wait_connected_ms=10000
```

`auto_id=true` sends the SerialTerminal `/id` connect preamble after every successful transport connect/reconnect and before the session is published as connected. For a target where this preamble is undesirable, use:

```json
{"id":2,"op":"open","device_key":"...","auto_id":false}
```

If the target does not connect within `wait_connected_ms`, `open` still returns the live session with:

```json
{"state":"reconnecting"}
```

The background session continues retrying the same device.

One `SessionManager` does not allow the same `device_key` to be opened twice. Different devices may be held simultaneously.

The response includes `latest_seq`. Save it as the initial raw cursor for subsequent `observe` calls when activity before completion of `open` has already been inspected or should be ignored.

## Session status

```json
{"id":3,"op":"status","session":"s1"}
```

Typical result fields:

```text
session
device_key
description
connected
state
streams
latest_seq
queued_tx
```

List all sessions:

```json
{"id":4,"op":"list_sessions"}
```

## Send a line

```json
{"id":5,"op":"send_line","session":"s1","text":"hello"}
```

Optional per-message EOL override:

```json
{"id":5,"op":"send_line","session":"s1","text":"AT","eol":"crlf"}
```

Supported EOL values:

```text
lf
crlf
cr
```

Response:

```json
{"id":5,"ok":true,"result":{"tx_id":12,"state":"queued"}}
```

`queued` means the reconnect-safe SerialTerminal TX queue accepted the item. The same accepted text is also written to the companion console log as `[session] [I] text` when run logging is enabled.

A later raw observation event with:

```json
{"kind":"tx","tx_id":12,"tx_state":"written"}
```

means the existing transport `write()` completed successfully. It does **not** mean a peer received the data or that a higher-level protocol accepted or completed the requested operation.

## Send raw bytes

Raw bytes use base64:

```json
{
  "id":6,
  "op":"send_bytes",
  "session":"s1",
  "data_b64":"FDE="
}
```

Line and raw-byte sends use the same ordered reconnect-safe TX queue. `send_bytes` is not rendered as ordinary human input in the companion console log.

## Observe raw events and logical lines

Request for one session:

```json
{
  "id":20,
  "op":"observe",
  "cursors":{
    "s1":42
  },
  "timeout_ms":15000
}
```

Request for multiple sessions uses exactly the same shape:

```json
{
  "id":21,
  "op":"observe",
  "cursors":{
    "s1":42,
    "s2":75
  },
  "timeout_ms":15000
}
```

`cursors` is required and must be a non-empty object. Each key is a session ID and each value is the last raw `SessionEvent.seq` already processed by the caller for that session. Sequence numbers are independent per session.

There is intentionally one cursor model. A single watched session still uses a `cursors` object; there is no separate single-session receive shape.

### Result

```json
{
  "id":21,
  "ok":true,
  "result":{
    "events":[
      {
        "session":"s1",
        "seq":43,
        "kind":"rx",
        "stream":"chat",
        "data_b64":"U0VTU0lPTiBUWCBvaw==",
        "text":"SESSION TX ok"
      },
      {
        "session":"s1",
        "seq":44,
        "kind":"rx",
        "stream":"chat",
        "data_b64":"PTEK",
        "text":"=1\n"
      }
    ],
    "lines":[
      {
        "session":"s1",
        "stream":"chat",
        "seq_first":43,
        "seq_last":44,
        "text":"SESSION TX ok=1"
      }
    ],
    "cursors":{
      "s1":44,
      "s2":75
    },
    "timed_out":false
  }
}
```

`events` and `lines` are two views over the same session receive history:

```text
events = forensic raw SessionEvent/chunk truth
lines  = completed LF-terminated logical firmware lines
```

The caller should use `result.lines` for line-oriented protocol/human-readable reasoning and `result.events` when exact transport/session evidence is required.

### Raw events

`result.events` preserves the existing `SessionEvent` representation. It may contain:

```text
state
tx
rx
error
```

Fields already present on those events remain unchanged, including exact `seq`, `stream`, `data_b64`, chunk-level incremental UTF-8 `text`, `tx_id`, `tx_state`, timestamp and device/description metadata where applicable.

BLE notifications remain BLE-sized chunks. SerialTerminal does not make a transport pretend to be line-oriented. `data_b64` is the byte-accurate source of truth.

### Logical lines

Logical line assembly lives once on `ManagedSession`, above the transport layer. Each receive stream has independent assembly state, so `main`, `chat`, `telemetry`, or future streams are never concatenated with one another.

Assembly uses the same incremental UTF-8 decoded text already produced for the raw RX event. It does not run a second independent decoder over raw chunks.

A line record has:

```text
session
stream
seq_first
seq_last
text
```

Rules:

- LF terminates a logical line and is omitted from `text`;
- a CR immediately before the terminating LF is removed from line-view `text`, so CRLF is one logical boundary;
- raw event bytes and raw event text are not normalized;
- empty LF-terminated lines are retained;
- `seq_first` is the first raw RX event participating in the line;
- `seq_last` is the raw RX event containing the terminating LF;
- if the first raw chunk contains only the beginning of a split UTF-8 code point and incremental decoding yields empty text, that raw event still becomes `seq_first`.

The same completed `SessionLine` objects feed `observe.result.lines` and the companion console logger. The logger merely selects human-console streams; it does not assemble text independently.

### One raw cursor controls both views

There is no line cursor.

A completed line is returned when:

```text
line.seq_last > input_cursor_for_that_session
```

Its `seq_first` may be less than or equal to the input cursor. This is deliberate and lets the session retain an incomplete line across observation calls without forcing the caller to assemble RX fragments itself.

For example, suppose the first observation returns:

```text
seq 100  RX text="DELIVERY WA"
```

The caller advances its raw cursor to 100. Later the next raw RX event is:

```text
seq 101  RX text="IT_ACK...\n"
```

Then:

```json
{"id":30,"op":"observe","cursors":{"s1":100},"timeout_ms":0}
```

returns raw event 101 and the complete line spanning both chunks:

```json
{
  "session":"s1",
  "stream":"telemetry",
  "seq_first":100,
  "seq_last":101,
  "text":"DELIVERY WAIT_ACK..."
}
```

Do not manually join raw RX chunks when the required completed logical line is already present in `result.lines`.

### Cursor-consistent snapshot

For each watched session, raw events and completed lines are read from one `ManagedSession` snapshot under the same session lock. An observation therefore cannot expose the raw event that terminates a logical line while accidentally omitting the line that the same event completed.

Across multiple sessions the manager merges the per-session snapshots and returns independent cursors for each session.

### Retention and cursor expiry

The finite raw `SessionEvent` ring is the authoritative cursor window. Completed logical lines are retained in relation to that same window so every still-valid raw cursor can retrieve completed lines whose `seq_last` is newer than the cursor.

If a requested raw cursor has fallen before the retained event window, the whole `observe` request fails with `cursor_expired`. There is no separate line-cursor error.

Example:

```json
{
  "id":25,
  "ok":false,
  "error":{
    "code":"cursor_expired",
    "message":"s2: event cursor 10 expired; oldest available seq is 57",
    "details":{
      "session":"s2",
      "requested_seq":10,
      "oldest_seq":57
    }
  }
}
```

An unknown watched session similarly fails the request with `unknown_session` and identifies the session in `details`.

### Lifecycle boundaries and incomplete lines

Only LF-terminated lines become first-class `result.lines` records.

An incomplete line is not promoted to a separate API record on disconnect, reconnect or close. Its raw bytes/text remain available in `result.events`. Incomplete assembly state is cleared at connection lifecycle boundaries so text from one transport connection cannot be joined to bytes received after reconnect.

The forensic log likewise does not create partial-line records.

### Timeout semantics

`timeout_ms` must be non-negative.

`timeout_ms:0` is an immediate snapshot. If no new raw event exists:

```json
{
  "events":[],
  "lines":[],
  "cursors":{"s1":42},
  "timed_out":false
}
```

A positive timeout long-polls until the first new raw event on any watched session. If no raw event appears before expiry:

```json
{
  "events":[],
  "lines":[],
  "cursors":{"s1":42},
  "timed_out":true
}
```

If a raw event arrives but does not complete a logical line, the request returns immediately with non-empty `events` and empty `lines`. A caller waiting for a specific firmware line should issue the next `observe` using the returned `cursors`.

There are no receive filters in `observe`; it returns all raw events after the watched cursors and all completed logical lines whose `seq_last` is newer than the corresponding input cursor. Callers may filter the returned arrays themselves.

## Concurrent JSONL behavior

Only `observe` requests are dispatched asynchronously. Ordinary operations remain serialized by the main JSONL reader in input order. This preserves mutation ordering while allowing one or more long-poll observations to remain pending.

Example timeline:

```text
request id=100  observe(s1,s2, 30s)         -> pending
request id=101  send_line(s1,"hello")       -> response id=101
request id=102  status(s1)                   -> response id=102
... raw event arrives on s2 ...
                                           -> response id=100
```

The exact result fields depend on current activity; correlation is by request `id`, not stdout position.

Multiple `observe` requests with different IDs may be pending simultaneously. Reusing any still-pending ID is rejected with `request_id_busy` and does not cancel the original request.

stdout writes are serialized, so concurrent completions cannot interleave fragments of JSON objects. The forensic log uses the same response emission lock for `[AGENT RESPONSE]`, so response-line order in the log matches response-line order on stdout. `[AGENT REQUEST]` entries remain in input order and may appear before responses to earlier pending observations.

There is no unsolicited push. Continuous observation is implemented by issuing a new `observe` after each completed response, using its returned `cursors`.

## Close and process shutdown

```json
{"id":10,"op":"close","session":"s1"}
```

Process EOF cancels pending `observe` calls, lets them finish with their correlated response, then closes remaining sessions. An observation cancelled specifically because the agent process is stopping may complete with structured `agent_stopping` before stdout closes.

The forensic and companion console logs close together when the agent run ends.

## Multiple devices

A single agent process can keep independent sessions open simultaneously:

```text
discover
open Device A -> s1
open Device B -> s2
send_line s1
observe {s1,s2}
...
close s1
close s2
```

SerialTerminal assigns no application-specific roles or acceptance rules to those devices. Such semantics belong in the calling agent skill.

## Architecture boundary

```text
Codex / future MCP
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
existing Transport abstraction
        ↓
SerialTransport / BleNusTransport / BluetoothSppTransport
```

The agent layer must not directly open serial ports, create Bleak clients or RFCOMM sockets. A future MCP frontend should wrap `SessionManager` rather than add another transport/session implementation.
