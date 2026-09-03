# TODO_002 — Multi-session agent event wait and concurrent JSONL

Status: PARTIAL

## Problem statement

The current machine-facing `events` operation waits on one session at a time, so an agent watching multiple devices must alternate requests. The JSONL frontend also processes requests synchronously, so a long-running wait prevents the same agent process from accepting commands until that wait returns.

## Purpose

Add a generic multi-session long-poll operation and then allow command requests to proceed while such waits are pending, without adding unsolicited stdout push messages and without duplicating transport/session logic.

## Target behavior

### Stage 1 — `wait_events`

- One `wait_events` request watches one or more existing sessions.
- Request field `cursors` maps each watched session ID to its last observed event `seq`.
- The request sleeps until a matching event appears or `timeout_ms` expires; it must not busy-poll sessions.
- A manager-level wakeup/doorbell is notified whenever a `ManagedSession` records an event; session event rings remain the source of truth.
- On wake, collect all currently available matching events from all watched sessions and tag each returned event with its `session`.
- Optional `kinds` and `streams` filters match existing `events` semantics.
- Returned cursors advance through all inspected events, including filtered-out events, so ignored events are not reconsidered on the next wait.
- Timeout is a successful response with `events: []` and `timed_out: true`.
- Invalid/expired cursors identify the affected session in structured error details.

### Stage 2 — concurrent JSONL request handling

- `wait_events` may remain pending while the same JSONL process accepts ordinary commands such as `send_line`, `status`, `events`, and `close`.
- Ordinary non-wait commands remain serialized in input order; only pending `wait_events` calls are executed asynchronously so existing mutation ordering is preserved.
- Responses may therefore arrive out of request order and are correlated by request `id`.
- A non-null request `id` is required for `wait_events`.
- Reuse of an ID that is still pending is rejected with structured `request_id_busy`; the original request remains pending.
- stdout remains response-only: no unsolicited event messages are emitted.
- stdout writes are serialized so each response remains exactly one complete JSON line.

## Scope

### Implementation

- [x] Add manager-level event wakeup fed by `ManagedSession` event creation.
- [x] Add `SessionManager.wait_events(...)` for one or N sessions.
- [x] Add JSONL `wait_events` dispatch and validation.
- [x] Add deterministic Stage 1 tests for one session, multiple sessions, filters/cursor advancement, timeout, and structured cursor/session errors.
- [x] Document Stage 1 in `AGENT_API.md`.
- [x] Validate Stage 1 in GitHub Actions before starting Stage 2.
- [ ] Allow pending `wait_events` while non-wait JSONL requests continue to execute.
- [ ] Add pending request-ID tracking and `request_id_busy` handling.
- [ ] Serialize response writes while allowing out-of-order completion by `id`.
- [ ] Add deterministic Stage 2 tests proving a command completes while a wait is pending and duplicate pending IDs are rejected.
- [ ] Document concurrency, response ordering, and ID rules in `AGENT_API.md`.
- [ ] Run final full CI and close this TODO only after success.

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

Stage 1:

```text
dreamworkerln/serialterminal/dev@faf42369ef58660189608ecc16befdcee59c488a
GitHub Actions run 33781308586: SUCCESS
python -m compileall -q src serialterminal.py tools: PASS
pytest -q: PASS
```

Stage 2: OPEN

## Follow-up work

Hardware/Codex smoke of the new wait/concurrency behavior is useful after implementation but is not a substitute for deterministic regression tests and clean-environment CI.
