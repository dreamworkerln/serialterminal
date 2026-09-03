# TODO_001 — Agent interface over shared SerialTerminal sessions

Status: OPEN

## Problem statement

`serialterminal` is currently optimized for a human interactive console. Codex/test automation needs a stable machine-facing interface without emulating the TUI and without duplicating Serial/BLE/SPP transport logic.

## Purpose

Expose the existing SerialTerminal device discovery, transport, reconnect and stream behavior through a small reusable session layer and a minimal JSONL frontend suitable for local Codex-driven hardware testing. Keep SerialTerminal generic; LoRa/Chatter test scenarios remain external skills.

## Current behavior

- `DeviceSelector` already discovers Serial/BLE/SPP candidates and creates the existing transports.
- `Transport` already exposes `connect`, `disconnect`, `read_chunk`, `write`, `device_key` and `stream_capabilities`.
- `TerminalSession` currently combines reconnect/TX/RX/session lifecycle with human stdout/logging, prompt-toolkit controls and Chatter presentation.
- Human-mode logging currently uses caller-provided/default log paths rather than a mandatory unique per-process file under `logs/`.

## Target behavior

- A reusable long-lived `ManagedSession` owns one existing `Transport`, reconnect lifecycle, reconnect-safe ordered TX and received/session events.
- Existing human `TerminalSession` uses the shared session core without observable regression in console behavior.
- A `SessionManager` can hold multiple independent `ManagedSession` instances and rejects duplicate ownership of the same `device_key` within one manager.
- A JSONL `serialterminal agent` frontend provides machine-readable discovery/open/status/send/events/close operations.
- Receive/wait is cursor-based using monotonically increasing event sequence numbers so separate agent calls do not need to destructively consume output.
- `send_line` and `send_bytes` share reconnect-safe TX behavior; successful transport write is reported distinctly from any higher-level protocol delivery/acceptance.
- Automatic `/id` after connect/reconnect remains enabled for both human and agent sessions.
- Every process invocation creates one mandatory unique logfile under `logs/` unless an explicit compatible override is deliberately retained; agent requests/responses and session/transport events are recorded in the same chronological log.

## Scope

### Implementation

- [ ] Extract shared session/reconnect/I/O core into `ManagedSession`.
- [ ] Define structured session events with monotonically increasing `seq`.
- [ ] Preserve tagged streams from `ReceivedChunk`.
- [ ] Support reconnect-safe line and raw-byte TX through the shared core.
- [ ] Adapt `TerminalSession` to the shared core while preserving human UI/presentation semantics.
- [ ] Separate non-interactive device catalog/factory behavior from human menu code where needed, reusing existing discovery and transports.
- [ ] Add `SessionManager` with multi-session ownership.
- [ ] Add JSONL agent request/response adapter and `serialterminal agent` CLI mode.
- [ ] Add mandatory per-process log creation under `logs/` and include agent JSON/session events.
- [ ] Document the generic agent API and logging behavior.

### Validation

- [ ] New deterministic unit tests for `ManagedSession` reconnect, ordered TX, event cursors and stream tags.
- [ ] Existing terminal tests remain green after the session-core extraction.
- [ ] Multi-session manager tests cover two independent sessions and duplicate-device rejection.
- [ ] JSONL tests cover success responses, structured errors and wait timeout behavior.
- [ ] Logging tests verify unique per-process path generation and agent request/response recording.
- [ ] `python -m compileall -q src serialterminal.py tools` PASS on exact checkpoint.
- [ ] Full `pytest -q` PASS on exact checkpoint.
- [ ] GitHub Actions clean-environment CI PASS on exact checkpoint.

## Non-goals

- MCP implementation in this phase.
- Daemon/service deployment, REST, WebSocket or global installation.
- A Chatter-only transport/tool.
- Node A/Node B, LoRa fault/recovery or other protocol-specific test scenarios.
- A regex/expect scripting DSL.
- Reimplementation of serial, Bleak/NUS or RFCOMM I/O in agent code.

## Constraints / invariants

- `SerialTransport`, `BleNusTransport` and `BluetoothSppTransport` remain the transport authorities.
- Sticky reconnect must retry only the selected physical identity.
- Ordered reconnect-safe TX behavior must be shared by human and agent frontends.
- BLE logical streams remain separate; no merging of human/chat and telemetry for convenience.
- Human Chatter presentation remains a UI-level concern and must not redefine generic agent RX data.
- Agent transport-write success must not be represented as LoRa/peer delivery success.
- Project-specific Codex skills belong in `lora-sack-protocol`, not in this implementation.

## Design decisions agreed before implementation

1. Reuse the existing session/transport architecture; extract a generic reconnect/I/O core rather than build a parallel stack.
2. Long-lived device connections are `ManagedSession` instances managed by `SessionManager`.
3. Receive/wait uses an append-only cursor/event model (`after_seq`, timeout) rather than destructive reads.
4. Multiple devices are represented by multiple independent sessions.
5. Initial wire/frontend interface is request/response JSON Lines.
6. Future MCP should wrap the same `SessionManager` rather than bypass it.
7. Automatic `/id` is intentionally preserved for agent sessions.
8. One process run produces one logfile under `logs/`; JSON agent traffic is logged with the device/session timeline.

## Exact checkpoints

Baseline before implementation:

```text
dreamworkerln/serialterminal/dev@1e2f7632e7ea6d0cd20283ef713d811ca32dd178
```

Implemented: pending
Validated: pending

## Follow-up work

- MCP adapter, if/when required, should become a separate task and thinly wrap the stable manager API.
- LoRa/Chatter Codex skills and hardware acceptance scenarios are owned by `lora-sack-protocol`.
