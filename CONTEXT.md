# Current work context

Status: COMPLETED

## Current operation

Add a minimal Codex/agent-facing interface on top of the existing SerialTerminal architecture without duplicating transport implementations or changing normal human-console behavior.

The operation is complete at the exact source checkpoint below. Stable recovery state is being published as the next numbered handoff snapshot.

## Exact baselines / result

Operation start source: dreamworkerln/serialterminal/dev@1e2f7632e7ea6d0cd20283ef713d811ca32dd178
Operation start handoff authority: dreamworkerln/serialterminal/dev_handoff@f2c4ed5e7a28261256897e439025a1e773318030
Completed source: dreamworkerln/serialterminal/dev@b5bd01eeb1f016ff58d3a69d3421087ac4027019
Accepted implementation checkpoint: dreamworkerln/serialterminal/dev@396f499305c7ab1c425483b5a5f10e8521125f4f
Final source CI: GitHub Actions run 33764490648 SUCCESS for dev@b5bd01eeb1f016ff58d3a69d3421087ac4027019

## Completed scope

- Added generic long-lived `ManagedSession` for shared reconnect, ordered reconnect-safe TX, RX and structured session events.
- Existing `SerialTransport`, `BleNusTransport`, `BluetoothSppTransport`, identity, discovery and stream implementations remain authoritative and are not duplicated by agent code.
- Existing human `TerminalSession` now runs on the shared core while retaining prompt/presentation behavior.
- Added `SessionManager` for multiple independent long-lived device sessions and duplicate-device ownership rejection.
- Added request/response JSONL frontend exposed as `serialterminal agent`.
- Added discovery, open, status/list sessions, reconnect-safe `send_line`/`send_bytes`, cursor-based `events` wait and close.
- Agent `open` defaults `auto_id=true`; `/id` is a connect/reconnect preamble before `connected`, with explicit `auto_id=false` for generic targets.
- Human automatic `/id` behavior remains its previous Serial-only behavior.
- Default normal human/agent runs use unique `logs/serialterminal-*.log` paths; agent request/response and session state/TX/RX/error events share the same chronological log.
- Added `AGENT_API.md`, README coverage, deterministic session/agent/CLI/logging tests and TODO records.
- `TODO_001_AGENT_INTERFACE` is CLOSED.

## Invariants / do not change

- Human interactive input remains line-oriented and is written to the device only after Enter.
- Sticky reconnect remains locked to the same selected physical device.
- Reconnect-safe ordered TX semantics remain shared rather than reimplemented in an adapter.
- BLE human/chat and telemetry streams remain logically separate.
- Existing Chatter-oriented presentation behavior remains human-UI-level state, not generic agent receive semantics.
- The agent layer does not instantiate Bleak clients, serial ports or RFCOMM sockets directly.
- `tx_state=written` means existing transport write success only, not LoRa/peer delivery.
- `dev` remains source authority; `dev_handoff` remains recovery-only.
- MCP, daemon/service, REST/WebSocket and Chatter-specific test scenarios remain outside this completed phase.
- LoRa/Chatter hardware test skills belong in `lora-sack-protocol` and should use this generic interface.

## Validation actually completed

Human shared-core regression checkpoint:

```text
dev@b9cebddfad326dc902d3adc94b773d39c0407605
GitHub Actions run 33763211529 SUCCESS
```

Agent implementation/tests checkpoint:

```text
dev@f9fae4c9ab0ae169fa44a29d6343f7425a5655a3
GitHub Actions run 33763807326 SUCCESS
```

Accepted documented implementation checkpoint:

```text
dev@396f499305c7ab1c425483b5a5f10e8521125f4f
GitHub Actions run 33764159009 SUCCESS
```

Final source/docs/TODO checkpoint:

```text
dev@b5bd01eeb1f016ff58d3a69d3421087ac4027019
GitHub Actions run 33764490648 SUCCESS
```

The repository CI includes:

```text
python -m compileall -q src serialterminal.py tools
pytest -q
```

Hardware validation of the new agent frontend was NOT RUN and is not claimed.

## Last completed action

`TODO_001` and `TODO_INVENTORY.md` were closed against exact green CI checkpoints.

## Next action

1. Publish/verify the next immutable handoff snapshot and advance `HANDOFF_INDEX.md` only after verification.
2. Follow-up outside this completed implementation: live local Codex/JSONL smoke with actual devices and inspect generated logs.
3. Create LoRa/Chatter-specific Codex skills in `lora-sack-protocol` when those hardware scenarios are defined.
4. If MCP becomes necessary, open a separate TODO and wrap the existing `SessionManager` rather than bypassing it.

## Blockers / findings

- No implementation blocker remains.
- Live hardware validation of the agent frontend remains pending follow-up.
- The scanner hardware regression items recorded by snapshot 001 remain a separate validation thread and were not silently closed by this work.
