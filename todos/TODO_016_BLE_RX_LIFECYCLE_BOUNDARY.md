# TODO_016 — Scope queued BLE RX data to a connection lifecycle

Status: OPEN

## Purpose

Prevent bytes already queued by an old BLE connection from being delivered as if they belonged to a later connection lifecycle.

## Finding checkpoint

```text
dev@159f7a1ab52fb8f615af33b175545f13e04dd989
```

`BleNusTransport` correctly uses a generation guard to reject callbacks from stale Bleak clients after disconnect/reconnect. However, accepted callback data is stored in `_rx_queue` and `_rx_pending` without generation metadata and those buffers are not cleared or otherwise bounded at connection transitions.

`read_chunk()` consumes `_rx_pending`/`_rx_queue` before it checks disconnected state. Bytes queued just before a disconnect can therefore be returned after the connection state boundary, and can survive long enough to be consumed after a later reconnect.

`ManagedSession` promises lifecycle separation for logical lines; transport-level buffered bytes must not defeat that boundary by reappearing under a newer connection.

This is a static lifecycle risk; no physical cross-generation corruption is claimed by this finding.

## Target behavior

- Every accepted BLE RX chunk is unambiguously attributable to the connection generation that produced it.
- Old-generation buffered data must either be deterministically delivered before the disconnect boundary or explicitly discarded/marked at that boundary; it must never be silently attributed to a new connection.
- `_rx_pending` must follow the same lifecycle rule as the main RX queue.
- Preserve stale-callback protection and notification ordering.
- If discarding already-received bytes is chosen, make the evidence/contract explicit enough that forensic users know the boundary behavior.

## Validation

- [ ] queue data, disconnect before read, reconnect, prove old bytes cannot appear as new-generation RX;
- [ ] same case with an oversized chunk leaving `_rx_pending`;
- [ ] remote-disconnect stale callbacks remain ignored;
- [ ] fresh reconnect data remains ordered and complete;
- [ ] ManagedSession incomplete-line lifecycle test still passes;
- [ ] full repository CI PASS.