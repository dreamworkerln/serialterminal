# TODO_001 — Agent interface over shared SerialTerminal sessions

Status: CLOSED

## Problem statement

`serialterminal` was optimized for a human interactive console. Codex/test automation needed a stable machine-facing interface without emulating the TUI and without duplicating Serial/BLE/SPP transport logic.

## Purpose

Expose the existing SerialTerminal device discovery, transport, reconnect and stream behavior through a small reusable session layer and a minimal JSONL frontend suitable for local Codex-driven hardware testing. Keep SerialTerminal generic; LoRa/Chatter test scenarios remain outside the generic agent implementation.

## Implemented behavior

- `ManagedSession` is the shared headless reconnect/RX/TX core used by the human terminal and agent sessions.
- Existing `SerialTransport`, `BleNusTransport`, `BluetoothSppTransport`, discovery identity and stream logic remain the only transport implementations.
- Human `TerminalSession` is an adapter/subclass over the shared session core and preserves its prompt/presentation behavior.
- `SessionManager` owns multiple independent long-lived sessions and rejects duplicate ownership of the same `device_key` inside one manager.
- `serialterminal agent` provides request/response JSON Lines operations for discovery, open/status/list, line/raw send, cursor-based events/wait and close.
- Receive/wait uses monotonically increasing event `seq` cursors and a finite retained event buffer rather than destructive TUI scraping.
- RX events preserve the existing `ReceivedChunk.stream` tag and byte-accurate base64 data plus incremental UTF-8 convenience text.
- `send_line` and `send_bytes` share the same ordered reconnect-safe TX mechanism. `tx_state=written` means only that existing transport `write()` completed; it is not promoted to protocol/radio delivery success.
- Human auto-ID behavior remains unchanged: automatic `/id` is the Serial connect/reconnect preamble; human BLE/SPP do not gain a new implicit command.
- Agent `open` defaults `auto_id=true`, so `/id` is sent after every successful transport connect/reconnect before the agent session publishes `connected`. Generic/non-Chatter callers can explicitly set `auto_id=false`.
- Normal human runs and agent runs default to unique files under `logs/serialterminal-*.log`; explicit `--log` remains available.
- Agent JSON requests/responses and session state/TX/RX/error events are recorded in the same chronological process log.
- `AGENT_API.md` documents the generic contract and future MCP boundary.
- LoRa/Chatter Node A/Node B, fault/recovery and acceptance scenarios remain outside the generic agent implementation. The active project-specific node skill is stored at `.agents/skills/node-agent/SKILL.md` in this repository so it is independent of the currently selected `lora-sack-protocol` branch/worktree; firmware/protocol source authority remains `lora-sack-protocol`.

## Scope

### Implementation

- [x] Extract shared session/reconnect/I/O core into `ManagedSession`.
- [x] Define structured session events with monotonically increasing `seq`.
- [x] Preserve tagged streams from `ReceivedChunk`.
- [x] Support reconnect-safe line and raw-byte TX through the shared core.
- [x] Adapt `TerminalSession` to the shared core while preserving human UI/presentation semantics.
- [x] Reuse existing `DeviceSelector` discovery/transport factory non-interactively from the manager; no parallel transport/discovery implementation was added.
- [x] Add `SessionManager` with multi-session ownership.
- [x] Add JSONL agent request/response adapter and `serialterminal agent` CLI mode.
- [x] Add default unique per-process log creation under `logs/` and include agent JSON/session events.
- [x] Document the generic agent API and logging behavior.

### Validation

- [x] New deterministic unit tests for `ManagedSession` reconnect, ordered TX, event cursors and stream tags.
- [x] Existing terminal tests remained green after the session-core extraction.
- [x] Multi-session manager tests cover two independent sessions and duplicate-device rejection.
- [x] JSONL tests cover structured errors, send/receive and wait timeout behavior.
- [x] Logging tests verify unique default paths and agent request/response/session-event recording.
- [x] `python -m compileall -q src serialterminal.py tools` PASS in GitHub Actions on exact checkpoint.
- [x] Full `pytest -q` PASS in GitHub Actions on exact checkpoint.
- [x] GitHub Actions clean-environment CI PASS on exact checkpoint.

Hardware validation of the new agent frontend was **NOT RUN as a closure gate** for this implementation TODO. A post-closure live hardware/Codex smoke was completed later and is recorded below; it does not retroactively change the implementation/CI checkpoints used to close the task.

## Non-goals

- MCP implementation in this phase.
- Daemon/service deployment, REST, WebSocket or global installation.
- A Chatter-only transport/tool.
- Node A/Node B, LoRa fault/recovery or other protocol-specific test scenarios inside the generic agent implementation.
- A regex/expect scripting DSL.
- Reimplementation of serial, Bleak/NUS or RFCOMM I/O in agent code.

## Constraints / invariants

- `SerialTransport`, `BleNusTransport` and `BluetoothSppTransport` remain the transport authorities.
- Sticky reconnect retries only the selected physical identity.
- Ordered reconnect-safe TX behavior is shared by human and agent frontends.
- BLE logical streams remain separate; human/chat and telemetry are not merged for convenience.
- Human Chatter presentation remains a UI-level concern and does not redefine generic agent RX data.
- Agent transport-write success is not represented as LoRa/peer delivery success.
- Project-specific node guidance must not redefine the generic JSONL API. The active node skill may live in `serialterminal` for stable availability, while firmware/protocol truth remains owned by the relevant `lora-sack-protocol` source checkpoint and hardware evidence.

## Design decisions

1. Reuse the existing session/transport architecture; extract a generic reconnect/I/O core rather than build a parallel stack.
2. Long-lived device connections are `ManagedSession` instances managed by `SessionManager`.
3. Receive/wait uses an append-only cursor/event model (`after_seq`, timeout) rather than destructive reads.
4. Multiple devices are represented by multiple independent sessions.
5. Initial wire/frontend interface is request/response JSON Lines.
6. Future MCP should wrap the same `SessionManager` rather than bypass it.
7. Agent automatic `/id` is intentionally enabled by default and explicitly disableable for generic targets.
8. One normal human or agent run produces one default logfile under `logs/`; JSON agent traffic is logged with the device/session timeline.

## Exact checkpoints

Baseline before implementation:

```text
dreamworkerln/serialterminal/dev@1e2f7632e7ea6d0cd20283ef713d811ca32dd178
```

Human-session extraction regression checkpoint:

```text
dreamworkerln/serialterminal/dev@b9cebddfad326dc902d3adc94b773d39c0407605
GitHub Actions run 33763211529: SUCCESS
```

Agent implementation + deterministic agent tests checkpoint:

```text
dreamworkerln/serialterminal/dev@f9fae4c9ab0ae169fa44a29d6343f7425a5655a3
GitHub Actions run 33763807326: SUCCESS
```

Documented accepted implementation checkpoint:

```text
dreamworkerln/serialterminal/dev@396f499305c7ab1c425483b5a5f10e8521125f4f
GitHub Actions run 33764159009: SUCCESS
```

The CI workflow on that exact checkpoint ran the repository clean-environment gates including:

```text
python -m compileall -q src serialterminal.py tools
pytest -q
```

Implemented: `396f499305c7ab1c425483b5a5f10e8521125f4f`
Validated: `396f499305c7ab1c425483b5a5f10e8521125f4f` / GitHub Actions run `33764159009` SUCCESS

## Post-closure hardware validation history

Observed on physical hardware on 2026-09-03:

- `python3 serialterminal.py agent` was used with two physical BLE LoRa-Chatter nodes in one process;
- Codex independently inspected node `/help` and used the discovered command surface without a pre-scripted node workflow;
- both physical nodes were opened as independent sessions;
- multi-session `wait_events` was used and the same agent process continued issuing ordinary commands while the wait was pending;
- TX was issued from both sessions close together, exercising independent per-session TX paths on physical devices.

This post-closure smoke is evidence that the generic agent frontend is practically usable with multiple physical sessions. It is **not** by itself proof that both close-together LoRa transmissions were received by their peers; RF delivery still requires peer RX/telemetry evidence.

The exact process log/checkpoint for this manual smoke was not recorded in this TODO, so no guessed run-log identifier is added here.

## Follow-up work

- Live local Codex/JSONL multi-device smoke: COMPLETED post-closure on 2026-09-03 as recorded above.
- Maintain LoRa/Chatter hardware observations and node-level acceptance guidance in `.agents/skills/node-agent/SKILL.md`; do not move the generic SerialTerminal API contract out of `AGENT_API.md`.
- MCP adapter, if/when required, should become a separate task and thinly wrap the stable `SessionManager` API.
