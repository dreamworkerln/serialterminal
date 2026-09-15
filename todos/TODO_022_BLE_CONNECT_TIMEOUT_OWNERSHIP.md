# TODO_022 — Own and retire timed-out BLE connect attempts

Status: OPEN

## Purpose

Ensure a synchronous BLE connect timeout cannot leave an older asynchronous connection coroutine running concurrently with later reconnect attempts.

## Finding checkpoint

```text
dev@159f7a1ab52fb8f615af33b175545f13e04dd989
```

`BleNusTransport.connect()` submits `_connect_async()` to the BLE loop and waits with a wrapper timeout. On `FutureTimeoutError` it returns `False` without cancelling/awaiting or otherwise retiring that submitted coroutine.

`ManagedSession` may then try to connect again while the older coroutine is still progressing through scan/connect/notification setup. Connection-generation checks reduce stale-publication risk, but they do not by themselves establish single ownership of backend tasks/clients or prove that overlapping connect cleanup is race-free.

This is a static lifecycle risk; no physical overlapping-connect failure is claimed.

## Target behavior

- Every timed-out connect attempt has deterministic ownership after the wrapper returns.
- Timeout either cancels and awaits/retire-cleans the attempt, or another explicit mechanism guarantees later connect attempts cannot overlap it.
- Cleanup must not tear down a newer successful generation.
- Existing stale callback/generation protections remain intact.
- Reconnect loop remains responsive when a backend stalls.

## Validation

- [ ] fake backend delays `connect()` beyond wrapper timeout, then releases late;
- [ ] fake backend delays `start_notify()` beyond wrapper timeout;
- [ ] immediate retry cannot create two active clients/notification sets;
- [ ] stale attempt cleanup cannot clear a newer connection;
- [ ] close/shutdown leaves no BLE connect task running;
- [ ] full repository CI PASS.