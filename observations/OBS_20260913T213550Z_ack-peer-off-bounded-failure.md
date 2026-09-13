# Node observation

Observed: 2026-09-13T21:35:50Z
Task: reliable USER with powered-off peer and bounded retries
Result: FAIL
SerialTerminal: dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21
Firmware: unknown

## Setup

- Sender `LoRa-Chatter-1B44`; physically powered-off peer `LoRa-Chatter-72E0`.
- One unique USER payload: `PEER_OFF_FAIL_20260914T0001`.

## Actions

- Sent one USER after explicit physical power-off confirmation.
- Restored the peer only after final failure and post-failure observation; no recovery delivery was tested.

## Evidence

- One logical identity `EC14/11`, same `seq=11` and payload across exactly attempts 1/5 through 5/5.
- Each attempt reached `WAIT_ACK` and ACK timeout; bounded backoffs preceded attempts 2–5.
- Exact final outcome: `[SYS] DELIVERY FAILED: no ACK`; queue was 0.
- More than 30 seconds after final failure contained no sixth attempt or pending retry.
- `>` payload presentation occurred once.

## Anomalies / conflicts

- Reliability internals also appeared in sender `chat` lines, violating telemetry-only presentation. Physical failure contract otherwise completed.

## Final state

- Peer restored and reconnected; both nodes `/chat`, echo not enabled, `queued_tx=0`; sessions closed and agent ended via EOF.

Run bundle: runs/RUN_20260913T213550Z_ack-peer-off-bounded-failure/
