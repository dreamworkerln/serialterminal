# TODO_008 — BLE write-timeout completion ambiguity

Status: OPEN

## Purpose

Define and enforce safe ownership of a BLE GATT write when the synchronous transport call times out while the submitted asyncio write coroutine may still be running.

## Finding checkpoint

Static source review:

```text
dev@1490078c85bde05ce54ded0c96752ff24d0ca7c1
```

Observed facts at that checkpoint:

- `BleNusTransport.write()` submits `_write_async()` to the BLE event loop and waits with `future.result(timeout=self.write_timeout)`;
- on any exception/timeout it clears the local connected flag and raises `TransportError`;
- the timeout path does not establish in code that the submitted future/coroutine can no longer complete the GATT write;
- `ManagedSession.tx_loop()` treats a transport write failure as reconnect/retry of the same queued item.

Risk: if the timed-out BLE write completes late after the caller has already classified it as failed, the reconnect-safe retry path can potentially write the same queued item again. This is a static-analysis risk; no physical duplicate write is claimed by this finding.

## Scope

- BLE GATT write timeout/cancellation/completion ownership;
- interaction with reconnect-safe TX retry semantics;
- generic transport/session documentation if the achievable guarantee is at-least-once rather than exactly-once-at-write-boundary.

## Non-goals

- no protocol-level deduplication in SerialTerminal;
- no Chatter-specific retry logic in generic transport/session code;
- no claim that transport `written` proves firmware acceptance or peer delivery.

## Implementation

- [ ] Establish the exact Bleak/asyncio behavior for cancellation and late completion of `write_gatt_char()` futures.
- [ ] Choose a transport/session behavior that cannot silently classify an in-progress write as definitely failed and then retry it without accounting for ambiguity.
- [ ] Preserve reconnect-safe ordering for ordinary definite failures.
- [ ] If an exactly-once transport-write guarantee is impossible, document and expose the ambiguity accurately instead of overstating failure certainty.
- [ ] Review `AGENT_API.md` and generic agent skill if TX/write semantics change.

## Validation

- [ ] Deterministic fake-BLE regression test blocks a GATT write past `write_timeout` and then releases it late.
- [ ] Test covers reconnect/retry behavior after that timeout.
- [ ] Test proves the selected contract: either the late write is prevented before retry, or the ambiguity is explicitly represented and unsafe duplicate retry is avoided/controlled according to the documented design.
- [ ] Existing BLE reconnect and TX ordering tests remain PASS.
- [ ] Relevant pytest suite PASS.
- [ ] GitHub Actions PASS on the implementation checkpoint.

## Closure criteria

`CLOSED` requires a documented, tested completion-ownership rule for timed-out BLE writes that is consistent with reconnect-safe TX ordering and does not silently turn an ambiguous write outcome into an unqualified retry assumption.
