# SerialTerminal agent interface

`serialterminal agent` is a local machine-facing JSON Lines frontend over the same discovery, transports and reconnect/session logic used by the normal human terminal.

It is intentionally generic. LoRa/Chatter hardware test scenarios belong in external Codex skills, not in this API.

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

A wait timeout is not an error. `events` returns an empty array with `timed_out: true`.

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
        "label":"BLE  LoRa-Chatter-1B44",
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

`auto_id=true` sends the normal `/id` line as a connect preamble after every successful transport connect/reconnect and before the session is published as connected. This is intentionally enabled for agent sessions so the hardware transcript contains an identity probe. For a non-Chatter target where sending `/id` is undesirable, explicitly use:

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

means the existing transport `write()` completed successfully. It does **not** mean a LoRa packet reached a peer or that any higher-level protocol accepted the command.

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

## Close

```json
{"id":10,"op":"close","session":"s1"}
```

Process EOF also closes all remaining sessions.

## Multiple devices

A single agent process can keep independent sessions open simultaneously:

```text
discover
open Node A -> s1
open Node B -> s2
send_line s1
wait events s2
...
close s1
close s2
```

No Node A/Node B or LoRa-specific meaning is built into SerialTerminal. Those roles and acceptance rules belong in the calling Codex skill.

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
