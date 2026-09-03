# SerialTerminal agent interface

`serialterminal agent` is a local machine-facing JSON Lines frontend over the same discovery, transports and reconnect/session logic used by the normal human terminal.

It is intentionally generic. Device-, firmware- and project-specific test scenarios belong in the consuming agent skills, not in this API.

## Start

```bash
python3 serialterminal.py agent
```

The process reads one JSON object per line from stdin and writes exactly one JSON response per request to stdout.

By default one unique logfile is created under:

```text
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.log
```

An explicit path can be supplied for debugging/tests:

```bash
python3 serialterminal.py agent --log /tmp/serialterminal-agent.log
```

The same chronological log contains:

```text
[AGENT REQUEST]
[AGENT RESPONSE]
[STATE]
[TX]
[RX <stream>]
[ERROR]
```

RX/TX byte payloads are represented as base64 in structured records. Text is a UTF-8 convenience view; `data_b64` remains the byte-accurate representation.

## Response envelope

Success:

```json
{"id":1,"ok":true,"result":{}}
```

Error:

```json
{"id":1,"ok":false,"error":{"code":"unknown_session","message":"unknown session: s1"}}
```

`id` is copied from the request and may be any JSON value.

A wait timeout is not an error. `events` and `wait_events` return an empty event array with `timed_out: true` when a positive timeout expires without a matching event.

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
        "key":"ble-address:44:1b:f6:8d:b7:a9",
        "kind":"ble",
        "label":"BLE  Device-1B44",
        "detail":"44:1B:F6:8D:B7:A9"
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
  "device_key":"ble-address:44:1b:f6:8d:b7:a9"
}
```

The returned `session` remains alive until `close` or process exit. Its internal `ManagedSession` keeps retrying the same physical target after a disconnect.

Default open behavior:

```text
eol=lf
auto_id=true
wait_connected_ms=10000
```

`auto_id=true` sends the current SerialTerminal `/id` connect preamble after every successful transport connect/reconnect and before the session is published as connected. For a target where sending this preamble is undesirable, explicitly use:

```json
{"id":2,"op":"open","device_key":"...","auto_id":false}
```

If the target does not connect within `wait_connected_ms`, `open` still returns the live session with:

```json
{"state":"reconnecting"}
```

The background session continues retrying the same device.

One `SessionManager` does not allow the same `device_key` to be opened twice. Different devices may be held simultaneously.

## Session status

```json
{"id":3,"op":"status","session":"s1"}
```

Example result fields:

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

`queued` means the reconnect-safe SerialTerminal TX queue accepted the item.

A later session event with:

```json
{"kind":"tx","tx_id":12,"tx_state":"written"}
```

means the existing transport `write()` completed successfully. It does **not** mean a peer received the data or that any higher-level protocol accepted or completed the requested operation.

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

Line and raw-byte sends use the same ordered reconnect-safe TX queue.

## Receive / wait using an event cursor

Each session has monotonically increasing event sequence numbers.

Request all retained events after cursor 40:

```json
{"id":7,"op":"events","session":"s1","after_seq":40}
```

Wait up to five seconds:

```json
{
  "id":8,
  "op":"events",
  "session":"s1",
  "after_seq":40,
  "timeout_ms":5000
}
```

Filter to RX on one stream:

```json
{
  "id":9,
  "op":"events",
  "session":"s1",
  "after_seq":40,
  "timeout_ms":5000,
  "kinds":["rx"],
  "streams":["chat"]
}
```

Typical RX event:

```json
{
  "seq":47,
  "kind":"rx",
  "stream":"chat",
  "data_b64":"W1NZU10gT0sK",
  "text":"[SYS] OK\n"
}
```

Typical state events include:

```text
reconnecting
connected
disconnected
closed
```

Typical TX events include:

```text
queued
written
connect-preamble-written
```

The event buffer is retained in memory with a finite window. If a caller holds an obsolete cursor after that window has rotated, the API returns structured error `cursor_expired` with the oldest available sequence number.

## Wait for events across one or more sessions

`wait_events` is the preferred long-poll operation when an agent may need to react to any of several open sessions. It also works with exactly one session, so the same operation can be used for a single-device echo/response test and for a multi-device exchange.

`cursors` is a non-empty object that maps every watched session ID to the last event sequence already inspected for that session:

```json
{
  "id":20,
  "op":"wait_events",
  "cursors":{
    "s1":42
  },
  "timeout_ms":10000
}
```

Watch two sessions with one request:

```json
{
  "id":21,
  "op":"wait_events",
  "cursors":{
    "s1":42,
    "s2":75
  },
  "timeout_ms":30000
}
```

Sequence numbers are independent per session. There is intentionally no single global `after_seq` for multi-session waits.

SerialTerminal does not repeatedly poll each session while waiting. Every `ManagedSession` keeps its own authoritative event ring and notifies a manager-level condition when an event is recorded. `wait_events` sleeps on that shared wakeup and then inspects the watched session rings.

When at least one matching event is available, the response contains all matching events already available across the watched sessions. Every returned event includes its source `session`:

```json
{
  "id":21,
  "ok":true,
  "result":{
    "events":[
      {
        "session":"s1",
        "seq":43,
        "kind":"tx",
        "tx_id":7,
        "tx_state":"written"
      },
      {
        "session":"s2",
        "seq":76,
        "kind":"rx",
        "stream":"chat",
        "text":"hello\n"
      }
    ],
    "cursors":{
      "s1":43,
      "s2":76
    },
    "timed_out":false
  }
}
```

Returned `cursors` are the positions the caller should use for its next `wait_events` request.

### Filters and cursor advancement

`wait_events` accepts the same optional `kinds` and `streams` filters as `events`:

```json
{
  "id":22,
  "op":"wait_events",
  "cursors":{
    "s1":43,
    "s2":76
  },
  "kinds":["rx"],
  "streams":["chat"],
  "timeout_ms":30000
}
```

A filter controls which events are returned and which events cause the wait to complete. Cursors nevertheless advance through every inspected event, including events excluded by the filter.

For example, if a session produces:

```text
seq 44  tx
seq 45  state
seq 46  rx/chat
```

while `kinds:["rx"]` is active, only `seq=46` is returned, and the returned cursor for that session is `46`. If only `tx` and `state` events arrive before timeout, no events are returned, but the response cursor advances past those inspected events so the next wait does not reconsider them.

With `timeout_ms:0`, `wait_events` is an immediate multi-session snapshot. An empty immediate snapshot has `timed_out:false`, matching the existing `events` convention that only an expired positive timeout is reported as a timeout.

### Timeout

If no matching event appears before a positive timeout expires:

```json
{
  "id":23,
  "ok":true,
  "result":{
    "events":[],
    "cursors":{
      "s1":43,
      "s2":76
    },
    "timed_out":true
  }
}
```

The cursor values may be higher than the input values if non-matching events were inspected while the request was waiting.

### Errors

An empty `cursors` object is `invalid_request`. Cursor keys must be non-empty session strings and cursor values must be non-negative integers.

If a watched session does not exist, the request fails with `unknown_session` and identifies the affected session:

```json
{
  "id":24,
  "ok":false,
  "error":{
    "code":"unknown_session",
    "message":"unknown session: missing",
    "details":{"session":"missing"}
  }
}
```

If one watched cursor is older than that session's retained event window, the complete `wait_events` request fails with `cursor_expired`. The error identifies the affected session, requested cursor, and oldest retained sequence:

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

At the current Stage 1 implementation checkpoint the JSONL reader is still synchronous: while one `wait_events` request is pending, the process does not read the next request line. Concurrent command handling while a wait is pending is the next stage of the same API work.

## Close

```json
{"id":10,"op":"close","session":"s1"}
```

Process EOF also closes all remaining sessions.

## Multiple devices

A single agent process can keep independent sessions open simultaneously:

```text
discover
open Device A -> s1
open Device B -> s2
send_line s1
wait_events {s1, s2}
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
        ↓
existing Transport abstraction
        ↓
SerialTransport / BleNusTransport / BluetoothSppTransport
```

The agent layer must not directly open serial ports, create Bleak clients or RFCOMM sockets. A future MCP frontend should wrap `SessionManager` rather than add another transport/session implementation.