# TODO_024 — Isolate BLE burst RX completeness loss

Status: PARTIAL

## Purpose

Determine where bytes are lost during high-rate BLE human-console output before treating malformed logical lines as a line-assembly bug or accepting BLE as complete hardware-validation evidence under burst load.

## Live finding checkpoint

Published hardware evidence:

```text
node_observations@649352f2a53329c4dbed933b586822e306d0916a
runs/RUN_20260914T235131Z_radio-interface-smoke/
SerialTerminal dev@159f7a1ab52fb8f615af33b175545f13e04dd989
Result: INCONCLUSIVE
```

Two BLE LoRa-Chatter sessions were open concurrently with `profile:"chatter"`. A near-simultaneous `/help` + `/id` burst completed normally on one session but produced corrupted/incomplete output on the other.

The durable forensic finding is stronger than the console symptom: the missing bytes are already absent from `serialterminal.log` raw `RX chat` events and their `data_b64` payloads.

Examples from affected session `s1`:

```text
seq 69: "[SYS]   CHAT       c"
seq 70: "show this help\n"
```

The complete peer output shows that the expected continuation after `c` is:

```text
hat + SYSTEM\n
```

so the missing range is not created by `ManagedSession` logical-line concatenation.

Another discontinuity is visible directly in raw events:

```text
seq 85: "[SYS]   /cancel all "
seq 86: "RMINAL MACROS:\n"
```

which skips the rest of the `/cancel all` help line, the `/reboot` line, the `RAW CONTROLS` heading and the beginning of `ANDROID BLE TERMINAL MACROS:`.

Finally, raw chat stops at:

```text
seq 95..97: "[SYS]   Nordic UART human console=0003; machine telemetry=00"
```

without the terminating `04 optional\n`. Much later the next USER confirmation is appended to that still-open logical line, yielding the observed malformed line.

Therefore the current evidence places the fault **before canonical logical-line completion**. It does not yet distinguish among firmware BLE notification production/queueing, controller/BlueZ BLE delivery, Bleak/backend behavior, or SerialTerminal's notification callback path before the event is recorded.

## Host-side isolation checkpoint

A deterministic regression test now injects 1001 BLE notification callbacks containing 10005 bytes into the actual `BleNusTransport` callback path, lets a real `ManagedSession` consume them, and asserts both exact raw-event byte/order preservation and the final completed logical line.

```text
implementation checkpoint: dev@a8b6c1974242df0bb267fa7156c704f8aeb0f6c0
validated tree:           dev@bb48db1709ab66df3f4492f25a51b997fe23c357
GitHub Actions:           34992221772 SUCCESS
```

This narrows the live anomaly: bytes that are actually delivered to the current SerialTerminal Bleak notification callback are preserved by `_queue_notify` -> `read_chunk` -> `ManagedSession` under the deterministic burst load covered by the test. It does **not** prove that a real BlueZ/Bleak backend will invoke every callback under concurrent physical load, nor that firmware emitted every notification.

No SerialTerminal runtime behavior was changed at this checkpoint; only regression/isolation coverage was added.

## Relation to other TODOs

- `TODO_014_TERMINAL_CANONICAL_LINE_ASSEMBLY.md` remains valid as an architecture/consistency cleanup, but this live anomaly is not evidence that its duplicate parser caused the loss.
- `TODO_016_BLE_RX_LIFECYCLE_BOUNDARY.md` concerns stale bytes crossing reconnect generations; this run had no corresponding reconnect boundary and does not establish that mechanism.
- If isolation proves the loss is entirely firmware-side, open/cross-link the appropriate firmware TODO and mark the SerialTerminal portion here accordingly rather than forcing a host-side fix.

## Target behavior

- A deterministic burst test distinguishes bytes emitted by the controller from bytes delivered to the SerialTerminal BLE notification callback and bytes persisted as raw events.
- SerialTerminal must not silently drop, reorder or overwrite callback-delivered notification bytes under sustained burst output.
- If bytes are already absent before the host callback, evidence must localize that boundary without blaming line assembly.
- Malformed/incomplete raw BLE output must not be treated as complete protocol evidence for the affected interval.

## Validation plan

- [x] add/verify a host-side stress test that injects many BLE notification callbacks quickly and proves exact byte/order preservation through `_queue_notify` -> `read_chunk` -> `ManagedSession` raw events;
- [ ] reproduce a long-output command sequentially on one BLE session and under concurrent two-session load;
- [ ] compare exact `data_b64` byte stream, not only console/logical lines;
- [ ] if practical, observe the same controller output through an independent path or controller-side emission evidence to separate firmware BLE production from host reception;
- [ ] verify no `forensic_gap` occurred during the affected interval;
- [ ] record the first proven loss boundary and only then choose the owning fix/repository;
- [ ] repeat the physical burst scenario after the fix and require byte-complete raw output;
- [x] full relevant repository CI PASS for the host-side isolation test checkpoint.

## Hardware-validation impact

Until this is isolated, ordinary low-rate BLE radio scenarios may still be useful when their required evidence is complete, but high-rate/burst human-console output should not be assumed lossless solely because the BLE session remains connected.
