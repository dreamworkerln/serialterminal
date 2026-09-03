# Handoff snapshot 002

```text
Snapshot: HANDOFF_002.md
Previous: HANDOFF_001.md
Created: 2026-09-03T14:04:00Z
Handoff authority: dreamworkerln/serialterminal/dev_handoff@7b3d7039266e0733d5ddebcf98270dbad477b686 (checkpoint before snapshot creation)
Source checkpoints:
  Active source: dreamworkerln/serialterminal/dev@b5bd01eeb1f016ff58d3a69d3421087ac4027019
  Accepted implementation: dreamworkerln/serialterminal/dev@396f499305c7ab1c425483b5a5f10e8521125f4f
Knowledge base: dreamworkerln/serialterminal/dev@b5bd01eeb1f016ff58d3a69d3421087ac4027019:README.md, AGENT_API.md, TODO_INVENTORY.md, todos/TODO_001_AGENT_INTERFACE.md, source comments/tests
Transfer / promotion boundary: dev_handoff is recovery-only; source authority remains dev; LoRa/Chatter test skills belong in lora-sack-protocol and consume the generic SerialTerminal agent interface
```

This snapshot becomes immutable after publication through `HANDOFF_INDEX.md`.

## 1. Recovery / authority

- Active implementation authority is `dreamworkerln/serialterminal` branch `dev`.
- Authoritative handoff/recovery infrastructure for this workstream is `dreamworkerln/serialterminal` branch `dev_handoff`.
- Before new code work or any statement about current implementation, refetch moving `dev`; this snapshot records exact source state at `b5bd01eeb1f016ff58d3a69d3421087ac4027019`.
- `dev_handoff` remains recovery-only; do not implement production code there by default.
- `TODO_INVENTORY.md` is now initialized on `dev`. `TODO_001_AGENT_INTERFACE` is CLOSED with exact implementation and validation evidence.
- No exact Chatter firmware revision is claimed here. Project-specific LoRa/Chatter test semantics and skills remain outside this SerialTerminal source authority.

## 2. Material changes since snapshot 001

Snapshot 001 recorded the pre-agent-interface state at `dev@1e2f7632...`. Since then:

- Added `src/serialterminal/session.py` with generic headless `ManagedSession`.
- Moved reconnect, ordered reconnect-safe TX, RX worker lifecycle and retained structured events into the shared session core.
- Migrated the existing human `TerminalSession` to that shared core while retaining prompt-toolkit, stdout, transcript and Chatter presentation behavior in the human layer.
- Added `src/serialterminal/agent.py` with `SessionManager` and request/response JSON Lines protocol.
- Added `src/serialterminal/runlog.py` for unique default process log paths and structured agent/session logging.
- Added multi-session support for multiple independent physical devices in one agent process.
- Added cursor-based retained event receive/wait with monotonic sequence numbers, stream filters and finite-window cursor-expiry reporting.
- Added reconnect-safe `send_line` and `send_bytes`; raw bytes and lines share the same TX ordering/retry mechanism.
- Added `serialterminal agent` CLI mode.
- Added agent connect preamble policy: `/id` is enabled by default for agent sessions on connect/reconnect and can be explicitly disabled with `auto_id=false` for generic targets.
- Preserved prior human behavior: automatic `/id` remains Serial-only for the interactive human terminal; BLE/SPP human connections were not given a new implicit command.
- Changed default normal human/agent run logging to unique paths under `logs/serialterminal-*.log`; explicit `--log` remains available.
- Agent JSON requests/responses and session state/TX/RX/error records share one chronological process log.
- Added `AGENT_API.md` and expanded README documentation.
- Initialized TODO management and closed `TODO_001_AGENT_INTERFACE` after automated gates passed.

## 3. Current implementation state

### Shared session core

`ManagedSession` owns one existing `Transport` and provides:

- sticky reconnect lifecycle using that transport's existing physical identity;
- independent RX/TX worker threads;
- ordered reconnect-safe TX queue;
- line TX with configurable EOL and raw-byte TX;
- monotonically increasing TX IDs;
- structured retained `SessionEvent` records for `state`, `rx`, `tx`, `error`;
- byte-accurate RX data plus independent incremental UTF-8 convenience decoding per stream;
- `events_after(after_seq, timeout, streams, kinds)` cursor-based wait/read;
- finite retained event window with explicit `SessionCursorExpired` rather than silent data loss;
- optional connect preamble executed after transport connect and before `connected` is published.

The shared core does not know LoRa delivery semantics and does not synthesize protocol success.

### Human terminal

`TerminalSession` now subclasses/adapts `ManagedSession` but keeps human-only behavior:

- prompt-toolkit local line editing and hotkeys;
- committed local prompt echo suppression;
- transcript/presentation handling;
- firmware-owned `>` success presentation and pending presentation queue;
- human output/view rules including background BLE `0004` handling;
- device chooser and Bluetooth scanner controls;
- previous Serial-only automatic `/id` behavior.

The human UI does not consume the JSONL frontend and the agent does not emulate the TUI.

### Agent manager / JSONL frontend

`SessionManager` provides the reusable machine-facing application API. The JSONL adapter is one frontend over it; a future MCP adapter should call the same manager rather than bypass it.

Current JSONL operations:

```text
discover
open
status
list_sessions
send_line
send_bytes
events
close
```

Important semantics:

- discovery reuses existing `DeviceSelector`/transport factory logic;
- no agent-side serial/Bleak/RFCOMM implementation exists;
- `open` returns a long-lived session ID (`s1`, `s2`, ...);
- different devices can be held simultaneously;
- duplicate `device_key` ownership inside one manager returns structured `device_busy`;
- default `open` uses `auto_id=true` and `wait_connected_ms=10000`;
- if initial wait expires, the session remains alive and returns `state=reconnecting` while retry continues;
- `auto_id=false` is available for generic/non-Chatter devices;
- `send_line` / `send_bytes` return `tx_id` and `state=queued` when accepted by the reconnect-safe queue;
- a later event `tx_state=written` means the existing transport write completed only; it does not mean LoRa/peer/protocol delivery;
- `events` timeout is a successful empty result with `timed_out=true`, not an exception;
- RX events preserve `stream`, `data_b64` and incremental UTF-8 `text` convenience output.

### Logging

Default run path:

```text
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.log
```

Human runs use a unique transcript path by default. Agent mode uses `RunLog` and records one chronological timeline including:

```text
[RUN]
[AGENT REQUEST]
[AGENT RESPONSE]
[STATE]
[TX]
[RX <stream>]
[ERROR]
```

Explicit `--log` is still supported for debugging/compatibility.

### TODO state

`TODO_INVENTORY.md` exists. `TODO_001_AGENT_INTERFACE` is CLOSED. No other active TODO is recorded at this snapshot.

## 4. Architecture / invariants

Preserve these unless an explicit later design task changes them:

- `Transport` and the existing concrete Serial/BLE/SPP transports remain I/O authority.
- Agent code must not open serial ports, instantiate `BleakClient`, or create RFCOMM sockets directly.
- Human and machine frontends share reconnect/TX/RX session logic rather than maintaining parallel retry stacks.
- Sticky reconnect retries the same selected physical identity.
- Ordered reconnect-safe TX applies to line and raw-byte sends.
- BLE logical streams remain separate, including decode state.
- Human Chatter presentation remains UI-level behavior; generic agent RX exposes actual transport data/events.
- `tx_state=written` is transport evidence only and must not be promoted to radio/protocol delivery success.
- Human automatic `/id` behavior remains Serial-only unless separately redesigned.
- Agent `auto_id=true` is the current default connect-preamble policy and has an explicit opt-out for generic targets.
- LoRa/Chatter Node A/Node B roles, fault injection, expected command responses and human hardware actions belong in `lora-sack-protocol` skills, not in SerialTerminal.
- Future MCP should be a thin adapter over `SessionManager`.
- `dev` remains source authority and `dev_handoff` remains recovery authority.

## 5. Validation evidence

### Actually run / observed

Human session-core migration regression checkpoint:

```text
dreamworkerln/serialterminal/dev@b9cebddfad326dc902d3adc94b773d39c0407605
GitHub Actions run 33763211529: SUCCESS
```

This is useful because the pre-existing full test suite passed immediately after moving the human terminal onto the shared core, before agent tests were added.

Agent implementation/tests checkpoint:

```text
dreamworkerln/serialterminal/dev@f9fae4c9ab0ae169fa44a29d6343f7425a5655a3
GitHub Actions run 33763807326: SUCCESS
```

Accepted documented implementation checkpoint:

```text
dreamworkerln/serialterminal/dev@396f499305c7ab1c425483b5a5f10e8521125f4f
GitHub Actions run 33764159009: SUCCESS
```

Final source/docs/TODO checkpoint recorded by this snapshot:

```text
dreamworkerln/serialterminal/dev@b5bd01eeb1f016ff58d3a69d3421087ac4027019
GitHub Actions run 33764490648: SUCCESS
```

Repository CI includes the clean-environment gates:

```text
python -m compileall -q src serialterminal.py tools
pytest -q
```

Automated coverage added for:

- shared session reconnect and ordered retry;
- connect preamble ordering;
- raw-byte and line TX through the same queue;
- stream-tagged incremental UTF-8 RX events;
- event waits and cursor expiry;
- multiple agent sessions and duplicate-device rejection;
- JSONL structured errors and timeout behavior;
- agent request/response and session event logging;
- unique default log path generation;
- CLI agent dispatch and default human log-path selection.

### Not run / still pending

- Hardware smoke of `serialterminal agent` against actual Serial/BLE/SPP devices: NOT RUN.
- Live Codex-driven use of the JSONL process against actual hardware: NOT RUN.
- Cross-repository LoRa/Chatter skills using this interface: NOT YET IMPLEMENTED in the recorded source repositories by this task.
- MCP adapter: NOT IMPLEMENTED; intentionally deferred.
- The live scanner regressions recorded in snapshot 001 remain a separate hardware validation thread and were not closed by agent-interface CI.

## 6. Findings / limitations / risks

- The current first agent frontend is intentionally local JSONL stdin/stdout, not a daemon or network service.
- `SessionManager` currently reuses `DeviceSelector` as the discovery/factory owner through a noninteractive path; there is no second discovery implementation. A later cleanup may split a dedicated `DeviceCatalog` only if that provides concrete value without duplicating behavior.
- Agent event retention is finite (default core window 4096 events). Consumers must advance cursors; stale cursors receive explicit `cursor_expired` metadata.
- `text` in RX events is a convenience incremental UTF-8 view; `data_b64` is the byte-accurate representation.
- Agent auto-ID can be inappropriate for a generic target. The explicit `auto_id=false` switch is therefore part of the public JSONL contract.
- Agent session logs are intentionally verbose/less pretty because they prioritize reconstruction of request -> session state -> TX/RX -> response chronology.
- No hardware claim should be inferred from green CI.

## 7. Knowledge references

At source checkpoint `dreamworkerln/serialterminal/dev@b5bd01eeb1f016ff58d3a69d3421087ac4027019`:

- `README.md` — current user-facing human + agent behavior and logging defaults.
- `AGENT_API.md` — authoritative first-stage JSONL contract and examples.
- `AGENTS.md` — repository engineering/validation rules.
- `HANDOFF_MANAGEMENT_POLICY.md` — recovery publication rules.
- `TODO_MANAGEMENT_POLICY.md` — task-management rules.
- `TODO_INVENTORY.md` — current TODO state; no active TODO at this snapshot.
- `todos/TODO_001_AGENT_INTERFACE.md` — closed design/implementation/validation record.
- `src/serialterminal/session.py` — shared `ManagedSession` core and event model.
- `src/serialterminal/agent.py` — `SessionManager`, JSONL protocol and agent process loop.
- `src/serialterminal/runlog.py` — per-process run log generation/writer.
- `src/serialterminal/terminal.py` — human frontend over shared core.
- `src/serialterminal/cli.py` — existing discovery/factory/UI plus agent CLI dispatch.
- `src/serialterminal/transports/` — unchanged transport authority.
- `tests/test_session.py`, `tests/test_agent.py`, `tests/test_cli.py`, existing terminal/transport tests — regression evidence.

## 8. Transfer / promotion notes

- No branch merge/promotion is required: implementation already lives on active source `dev`.
- `dev_handoff` must not be merged wholesale back as a source tree; it is recovery documentation authority only.
- LoRa/Chatter test skills should be created in `dreamworkerln/lora-sack-protocol`, referencing SerialTerminal's stable agent contract rather than copying its transport/session code.
- If MCP is later required, preserve dependency direction:

```text
LoRa/other project skill
        -> MCP or JSONL adapter
        -> SessionManager
        -> ManagedSession
        -> existing Transport implementations
```

## 9. Immediate continuation

1. Refetch `dev` before any new source work.
2. Run a live local agent smoke, for example `python3 serialterminal.py agent`, against actual visible hardware and inspect the generated `logs/serialterminal-*.log` timeline.
3. Verify a real `discover -> open -> events -> send_line/send_bytes -> events -> close` cycle and at least two simultaneous physical sessions if hardware permits.
4. In `lora-sack-protocol`, create the first project-specific Codex skill only when the concrete LoRa/Chatter scenario and acceptance criteria are defined.
5. Open a separate TODO before implementing MCP; it should wrap the existing `SessionManager` API rather than introduce a parallel stack.
6. Keep the snapshot-001 scanner/Bluetooth hardware follow-up separate unless it materially affects agent smoke results.

## 10. Standing reminders

- Automated CI is green for exact final source `dev@b5bd01eeb1f016ff58d3a69d3421087ac4027019`; agent hardware validation is not claimed.
- Preserve human console behavior while evolving machine-facing interfaces.
- Keep source authority (`dev`) and recovery authority (`dev_handoff`) separate.
- Keep project-specific test semantics in the consuming project skills, not in generic SerialTerminal.
- Future snapshots remain create -> read-back/verify -> advance index, with exact source SHAs.
