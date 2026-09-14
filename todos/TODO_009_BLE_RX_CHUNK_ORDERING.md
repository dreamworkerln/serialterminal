# TODO_009 — BLE oversized RX chunk ordering

Status: CLOSED

## Purpose

Preserve byte/notification order when `BleNusTransport.read_chunk(size)` must split a received BLE chunk that is larger than the caller's requested read size.

## Finding checkpoint

```text
dev@1490078c85bde05ce54ded0c96752ff24d0ca7c1
```

At that checkpoint an oversized notification returned its head and appended the unread tail back to the normal FIFO, allowing a later notification to overtake that tail.

## Implemented

- `BleNusTransport` keeps one unread split tail in `_rx_pending` ahead of the normal notification queue.
- Repeated small reads continue consuming the same notification until its tail is exhausted before any later notification is returned.
- Every fragment keeps the original stream tag.
- Chunks that already fit within `size` retain the previous behavior.
- Transport chunking remains separate from `ManagedSession` logical-line assembly and controller profiles.

## Validation

Host-side tests cover A-head/A-tail/B ordering, a notification requiring more than two fragments, and stream-tag preservation.

```text
accepted checkpoint: dev@69cc1e4157471f69718dbb9fbb46ef5b8d945ab7
GitHub Actions:      34908096672 SUCCESS
compile:             PASS
static/Ruff:         PASS
complexity:          PASS
pytest:              PASS
hardware:            NOT RUN
```

## Closure

`CLOSED`: splitting an oversized BLE receive chunk no longer reorders its unread tail behind later notifications.
