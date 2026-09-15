# TODO_011 — Chatter presentation outcome correlation

Status: OPEN

## Purpose

Make human `chatter` presentation resolve the correct submitted payloads when one firmware outcome refers to a specific rejected item or to several cancelled reliability items.

## Finding checkpoint

Second static review:

```text
dev@159f7a1ab52fb8f615af33b175545f13e04dd989
```

The earlier TODO_005 correctly added `/cancel`, `/cancel all`, queue-full and cancellation recognition, but the current resolver still treats every failure-like SYSTEM line as a one-item FIFO resolution.

Current `ChatterPresentation.consume_firmware_line()` removes the first `sent` pending item for any recognized failure prefix. That is not sufficient for the current Chatter outcomes:

- queue-full rejects the newly processed USER while older accepted reliability items may still be pending, so resolving the oldest presentation can associate the rejection with the wrong payload;
- `/cancel all` may clear one current in-flight USER plus multiple queued USER messages while firmware emits one aggregate SYSTEM outcome, so removing only one presentation entry can leave cancelled submissions stale;
- no-in-flight `/cancel all` can similarly remove several queued messages with one aggregate outcome.

The corresponding ACK-capable firmware source checkpoint confirms that queue-full rejects the current event and that `/cancel all` clears the reliability queue before emitting one aggregate cancellation line.

## Target behavior

- Outcome handling must express whether firmware resolved one specific/current submission, the oldest eligible submission, or all affected submissions.
- Queue-full presentation must reveal/clear the rejected payload without consuming an unrelated earlier accepted payload.
- `/cancel all` presentation must clear every host presentation entry covered by the aggregate firmware cancellation outcome.
- Duplicate payload text must not make correlation ambiguous or resolve the wrong occurrence.
- Chatter-specific outcome knowledge stays in the Chatter profile/presentation layer; generic `ManagedSession`, transports and JSONL API remain controller-agnostic.

## Validation

- [ ] deterministic tests with multiple simultaneously pending presentation entries;
- [ ] queue-full test proving the rejected/latest input is resolved while earlier pending items remain correct;
- [ ] `/cancel` tests for in-flight and queued single-item outcomes;
- [ ] `/cancel all` tests for current + multiple queued items and queued-only items;
- [ ] duplicate-text payload regression coverage;
- [ ] existing Chatter presentation tests remain green;
- [ ] full repository CI PASS.

Hardware is not required to prove the host state-machine fix, but any later physical presentation run must preserve exact firmware output rather than inventing host suffixes.