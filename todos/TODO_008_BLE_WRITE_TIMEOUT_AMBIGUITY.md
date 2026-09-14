# TODO_008 — BLE write-timeout completion ambiguity

Status: CLOSED

## Purpose

Define and enforce safe ownership of a BLE GATT write when the synchronous transport call times out while the submitted asyncio write coroutine may still be running.

## Finding checkpoint

```text
dev@1490078c85bde05ce54ded0c96752ff24d0ca7c1
```

At that checkpoint every BLE write exception/timeout was treated as a definite `TransportError`; `ManagedSession` could then reconnect and retry the same queued item even though a timed-out backend write might still complete late.

## Implemented

- Added generic `TransportWriteOutcomeUnknown`, a `TransportError` subtype for writes whose side effect cannot be proven absent.
- BLE GATT timeout requests cancellation of the submitted future, clears local connected state, and raises `TransportWriteOutcomeUnknown` with an explicit `outcome unknown` message.
- `ManagedSession` records a terminal TX event with `tx_state="unknown"` plus an `error` event with `state="send-outcome-unknown"`.
- An ambiguous TX is consumed and is **not** automatically retried after reconnect.
- Ordinary definite `TransportError`/`OSError` failures retain the existing reconnect-and-retry behavior and ordering.
- `tx_state="written"` still means only that transport `write()` completed; it does not prove peer or application delivery.

This is deliberately not an exactly-once guarantee. It is an explicit ambiguity contract that prevents SerialTerminal from turning an uncertain BLE side effect into an unqualified duplicate retry.

## Validation

The fake BLE test holds a GATT write beyond `write_timeout`, observes cancellation, then deliberately completes the backend side effect late. The session-level test verifies the ambiguous first TX is attempted once, receives `tx_state="unknown"`, is not retried, and the next queued TX proceeds after reconnect.

```text
accepted checkpoint: dev@441fc99d3f123e9133253c820f59f54e37d23f88
GitHub Actions:      34907924472 SUCCESS
compile:             PASS
static/Ruff:         PASS
complexity:          PASS
pytest:              PASS
hardware:            NOT RUN
```

## Closure

`CLOSED`: timed-out BLE write ownership is represented explicitly as unknown when required, unsafe automatic duplicate retry is avoided, and ordinary definite-failure retry semantics remain intact.
