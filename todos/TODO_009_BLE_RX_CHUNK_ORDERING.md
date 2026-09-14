# TODO_009 — BLE oversized RX chunk ordering

Status: OPEN

## Purpose

Preserve byte/notification order when `BleNusTransport.read_chunk(size)` must split a received BLE chunk that is larger than the caller's requested read size.

## Finding checkpoint

Static source review:

```text
dev@1490078c85bde05ce54ded0c96752ff24d0ca7c1
```

Observed facts at that checkpoint:

- BLE notifications are queued in `_rx_queue` in arrival order;
- when one queued chunk exceeds `size`, `read_chunk()` returns the head and puts the tail back into `_rx_queue` with ordinary FIFO `put()`;
- if a later notification is already queued, that later notification can be returned before the tail of the earlier oversized notification.

Example failure shape:

```text
queue before read:   [A(head+tail), B]
current behavior:    return A(head), queue becomes [B, A(tail)]
required ordering:   A(head), A(tail), B
```

BLE notifications are normally small, so this is an edge-case correctness defect rather than a claim about common hardware behavior.

## Scope

- generic BLE receive buffering/splitting;
- preservation of per-arrival byte order across repeated small reads;
- stream tag preservation for split tails.

## Non-goals

- no change to BLE characteristic/profile mapping;
- no line assembly in the transport layer;
- no controller-specific receive logic.

## Implementation

- [ ] Change oversized-chunk handling so an unread tail is consumed before any later queued notification.
- [ ] Preserve the original stream tag on every returned fragment.
- [ ] Preserve existing behavior when the chunk fits in the requested size.
- [ ] Keep transport-level chunking separate from `ManagedSession` logical-line assembly.

## Validation

- [ ] Regression test queues oversized notification A followed by notification B and reads with a small size; observed order must be A-head, A-tail, B.
- [ ] Regression test covers an item requiring more than two fragments.
- [ ] Regression test verifies stream tags remain correct.
- [ ] Existing BLE notification/reconnect tests remain PASS.
- [ ] Relevant pytest suite PASS.
- [ ] GitHub Actions PASS on the implementation checkpoint.

## Closure criteria

`CLOSED` requires deterministic tests proving `read_chunk(size)` never reorders a split tail behind a later notification while preserving the generic transport contract.
