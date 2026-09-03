# TODO_002 — Multi-session agent event wait and concurrent JSONL

Status: CLOSED

## Problem statement

The original machine-facing `events` operation waited on one session at a time, so an agent watching multiple devices had to alternate requests. The JSONL frontend also processed requests synchronously, so a long-running wait prevented the same agent process from accepting commands until that wait returned.

## Purpose

Add a generic multi-session long-poll operation and then allow command requests to proceed while such waits are pending, without adding unsolicited stdout push messages and without duplicating transport/session logic.

## Implemented behavior

### Stage 1 — `wait_events`

- One `wait_events` request watches one or more existing sessions.
- Request field `cursors` maps each watched session ID to its last inspected event `seq`.
- The request sleeps until a matching event appears or `timeout_ms` expires; it does not busy-poll sessions.
- A manager-level condition acts only as a wakeup/doorbell when a `ManagedSession` records an event; per-session event rings remain authoritative.
- On wake, all currently available matching events across watched sessions are collected and each returned event includes its source `session`.
- Optional `kinds` and `streams` filters follow the existing event model.
- Returned cursors advance through all inspected events, including filtered-out events.
- Positive timeout expiry is a successful response with `events: []` and `timed_out: true`.
- Invalid/expired cursors and unknown sessions identify the affected session in structured error details.

### Stage 2 — concurrent JSONL request handling

- `wait_events` may remain pending while the same JSONL process accepts ordinary commands such as `send_line`, `status`, `events`, and `close`.
- Ordinary non-wait commands remain serialized in input order; only pending `wait_events` calls execute asynchronously, preserving mutation ordering among ordinary requests.
- Responses may arrive out of request order and are correlated by request `id`.
- A non-null request `id` is required for `wait_events`.
- Reuse of an ID still owned by a pending wait returns structured `request_id_busy`; the original wait remains pending.
- Multiple waits with distinct IDs may be pending simultaneously.
- stdout remains response-only; no unsolicited event messages are emitted.
- Response logging/stdout emission is serialized so each response remains one complete JSON line and `[AGENT RESPONSE]` order matches stdout response order.
- On process shutdown, pending waits are cancelled/woken before sessions are closed rather than waiting for arbitrary long-poll timeouts.
- Existing `events` remains available and synchronous; clients that need a non-blocking command channel while waiting should use `wait_events`.

## Scope

### Implementation

- [x] Add manager-level event wakeup fed by `ManagedSession` event creation.
- [x] Add `SessionManager.wait_events(...)` for one or N sessions.
- [x] Add JSONL `wait_events` dispatch and validation.
- [x] Add deterministic Stage 1 tests for one session, multiple sessions, filters/cursor advancement, timeout, and structured cursor/session errors.
- [x] Document Stage 1 in `AGENT_API.md`.
- [x] Validate Stage 1 in GitHub Actions before starting Stage 2.
- [x] Allow pending `wait_events` while non-wait JSONL requests continue to execute.
- [x] Add pending request-ID tracking and `request_id_busy` handling.
- [x] Serialize response writes while allowing out-of-order completion by `id`.
- [x] Add deterministic Stage 2 tests proving a command completes while a wait is pending and duplicate pending IDs are rejected.
- [x] Document concurrency, response ordering, and ID rules in `AGENT_API.md`.
- [x] Synchronize the README agent operation summary with the new API.
- [x] Run final full CI and close this TODO only after success.

## Non-goals

- Unsolicited push messages on stdout.
- WebSocket, daemon, REST, or MCP implementation.
- Project/device-specific protocol acceptance logic.
- Parallel reimplementation of Serial/BLE/SPP transports.
- Making all mutating JSONL operations execute concurrently with each other.

## Constraints / invariants

- Existing `ManagedSession` event rings and monotonically increasing per-session `seq` values remain authoritative.
- `SerialTransport`, `BleNusTransport`, and `BluetoothSppTransport` remain the transport authorities.
- Existing single-session `events` remains supported.
- JSON stdout stays machine-clean and contains only request-correlated responses.
- No hardware success claim may be derived from unit/CI tests alone.

## Baseline

```text
dreamworkerln/serialterminal/dev@33f9719f0dd048084a4423de83babd1ab2d76ee7
GitHub Actions run 33775808413: SUCCESS
```

## Validation checkpoints

Stage 1 accepted checkpoint:

```text
dreamworkerln/serialterminal/dev@faf42369ef58660189608ecc16befdcee59c488a
GitHub Actions run 33781308586: SUCCESS
python -m compileall -q src serialterminal.py tools: PASS
pytest -q: PASS
```

Stage 2 implementation + canonical `AGENT_API.md` checkpoint:

```text
dreamworkerln/serialterminal/dev@c2167099ad6b6fb9aa8ee07cdba9c724b5b368c4
GitHub Actions run 33782053409: SUCCESS
python -m compileall -q src serialterminal.py tools: PASS
pytest -q: PASS
```

Accepted implementation/documentation checkpoint including README synchronization:

```text
dreamworkerln/serialterminal/dev@aaeab3002e60bd1e85595d73e3248d42c3141c1f
GitHub Actions run 33782252791: SUCCESS
```

Implemented: `aaeab3002e60bd1e85595d73e3248d42c3141c1f`
Validated: `aaeab3002e60bd1e85595d73e3248d42c3141c1f` / GitHub Actions run `33782252791` SUCCESS

## Hardware validation

A live hardware/Codex smoke specifically exercising the new multi-session `wait_events` and concurrent command behavior was **NOT RUN as part of the implementation closure gates**. The deterministic tests and clean-environment CI above remain the exact closure evidence.

Post-closure on 2026-09-03, a live smoke was observed with two physical BLE LoRa-Chatter nodes in one `serialterminal agent` process:

- both nodes were opened as independent sessions;
- Codex used a multi-session `wait_events` request;
- while that wait remained pending, the same process continued issuing ordinary commands;
- TX was then issued from both sessions close together, exercising the independent per-session TX paths on physical devices.

This is direct post-closure evidence for the practical multi-session/concurrent-wait workflow. It does **not** by itself prove successful peer receipt of both close-together LoRa transmissions; RF delivery still requires corresponding peer RX/telemetry evidence.

The exact process log/checkpoint for this manual smoke was not recorded in this TODO, so no guessed run-log identifier is claimed.

## Follow-up work

The generic hardware/Codex concurrency smoke is now complete as post-closure validation. Project/device-specific RF acceptance scenarios remain outside the generic API contract and are documented in `.agents/skills/node-agent/SKILL.md` when they are relevant to LoRa-Chatter hardware.
