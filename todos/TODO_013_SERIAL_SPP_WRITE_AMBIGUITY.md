# TODO_013 — Serial/SPP ambiguous write outcomes

Status: OPEN

## Purpose

Extend explicit send-side-effect ownership beyond BLE so reconnect-safe retry never blindly repeats a Serial or RFCOMM write whose transport side effect may already have partially occurred.

## Finding checkpoint

```text
dev@159f7a1ab52fb8f615af33b175545f13e04dd989
```

`ManagedSession` retries an item after ordinary `TransportError`; only `TransportWriteOutcomeUnknown` makes that item terminal and prevents automatic resend.

Current non-BLE transports can report a plain `TransportError` after an ambiguous side effect:

- `SerialTransport.write()` calls `ser.write(data)` followed by `ser.flush()`, ignores the returned byte count, and maps Serial/OSError failures to plain `TransportError`. A short/partial write or an error after bytes reached the driver is not necessarily safe to repeat in full.
- `BluetoothSppTransport.write()` uses `socket.sendall(data)` and maps timeout/OSError to plain `TransportError`. `sendall()` can fail after transmitting a prefix, so repeating the complete payload may duplicate bytes.

This is a static semantic risk; no physical duplicate write is claimed by this finding.

## Target behavior

- Define transport-independent criteria for `definitely not written / safe to retry` versus `side effect may have occurred / outcome unknown`.
- Serial and SPP must raise `TransportWriteOutcomeUnknown` whenever completion cannot be proven safe to repeat.
- Detect and classify short Serial writes instead of ignoring the returned count.
- Preserve reconnect-safe retry only for failures that are demonstrably safe to repeat.
- Keep `tx_state="unknown"` terminal for the affected queued item and preserve later queue ordering according to the documented session contract.
- Update `AGENT_API.md` and the generic agent skill if the set of transports producing `unknown` expands.

## Validation

- [ ] deterministic partial Serial write test;
- [ ] Serial write/flush exception after possible side effect test;
- [ ] SPP `sendall` timeout/error after modeled prefix transmission test;
- [ ] known-safe pre-write failure still retries in order;
- [ ] ambiguous item is not automatically resent;
- [ ] later queued item behavior remains documented and tested;
- [ ] full repository CI PASS.