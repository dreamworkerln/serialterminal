# Current work context

Status: IN PROGRESS

## Current operation

Add a minimal Codex/agent-facing interface on top of the existing SerialTerminal architecture without duplicating transport implementations or changing normal human-console behavior.

## Exact baselines

Source: dreamworkerln/serialterminal/dev@1e2f7632e7ea6d0cd20283ef713d811ca32dd178
Handoff authority baseline: dreamworkerln/serialterminal/dev_handoff@f2c4ed5e7a28261256897e439025a1e773318030

## Scope

- Extract a generic long-lived `ManagedSession` from the reconnect/I/O responsibilities currently embedded in `TerminalSession`.
- Keep existing `SerialTransport`, `BleNusTransport`, `BluetoothSppTransport`, device identity, discovery and stream logic as the only transport implementations.
- Keep the existing human terminal behavior by adapting `TerminalSession` to the shared session core.
- Add a `SessionManager` capable of keeping multiple independent device sessions open at once.
- Add a minimal request/response JSONL agent frontend exposed as `serialterminal agent`.
- Support discovery, open, status/list sessions, reconnect-safe line/raw-byte send, cursor-based receive/wait over session events, and close.
- Preserve automatic `/id` after connect/reconnect for agent and human sessions.
- Make logging mandatory: each SerialTerminal process gets a separate log under `logs/`; agent JSON requests/responses and session/transport events share the same chronological log.
- Keep LoRa/Chatter hardware test scenarios out of SerialTerminal; project-specific Codex skills belong in `lora-sack-protocol`.

## Invariants / do not change

- Human interactive input remains line-oriented and is written to the device only after Enter.
- Sticky reconnect remains locked to the same selected physical device.
- Reconnect-safe ordered TX semantics remain shared rather than reimplemented in the agent adapter.
- BLE human/chat and telemetry streams remain logically separate.
- Existing Chatter-oriented presentation behavior for the human console remains unchanged.
- The agent layer must not instantiate Bleak clients, serial ports, or RFCOMM sockets directly.
- `dev` remains source authority; `dev_handoff` remains recovery-only.
- No MCP, daemon/service, REST/WebSocket layer or Chatter-specific test DSL in this phase.

## Last completed action

Architecture and interface boundaries were agreed with the user. Handoff snapshot 001 records the pre-change source state.

## Current / next action

1. Initialize TODO tracking for this substantial task on `dev`.
2. Implement `ManagedSession` plus deterministic tests.
3. Adapt `TerminalSession` to use the shared session core and verify old human-terminal tests remain green.
4. Add `SessionManager`, JSONL agent frontend and per-process logging.
5. Add agent/multi-session/logging tests and documentation.
6. Run/inspect GitHub Actions after each meaningful source checkpoint.
7. When implementation reaches a stable recovery checkpoint, publish the next numbered handoff snapshot using create -> read-back/verify -> advance-index order.

## Required validation

- `python -m compileall -q src serialterminal.py tools`
- full `pytest -q`
- GitHub Actions clean-environment CI on exact implementation checkpoints
- no claim of hardware validation unless separately performed

## Blockers / findings

- No current blocker.
- A live hardware scanner regression from snapshot 001 remains separate/pending and must not be conflated with this agent-interface implementation.
