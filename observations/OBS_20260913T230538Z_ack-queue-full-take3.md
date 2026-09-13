# Node observation

Observed: 2026-09-13T23:05:38Z
Task: queue full -> explicit rejection, take3
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21
Firmware: unknown

## Setup

- Sender `LoRa-Chatter-1B44`; peer `LoRa-Chatter-72E0`; explicit Chatter profile on both sessions.
- Peer was powered off for the in-flight USER and restored before natural drain.

## Actions

- Submitted the 8 waiting payloads and `QFULL3_REJECT_20260914T` as one fast 9-request JSONL burst while observe was pending.

## Evidence

- In-flight USER reached `TX USER ... attempt=1/5` and `DELIVERY WAIT_ACK ... queue=0`.
- Firmware reported `INPUT QUEUE FULL dropped=8` and accepted only `waiting=1/8` through `waiting=4/8`; `waiting=8/8` was not reached.
- Exact `[SYS] SEND QUEUE FULL: message not accepted` was absent. Overflow had no observed USER identity, RF TX, peer RX, or ACK.
- Accepted queue drained naturally to zero after peer restoration.

## Anomalies / conflicts

- The requested queue-full acceptance point was not reached; classify as orchestration/setup inconclusive, not firmware FAIL.

## Final state

- Both nodes restored, connected, `/chat`, echo OFF, host `queued_tx=0`; no cancellation used.

Run bundle: runs/RUN_20260913T230538Z_ack-queue-full-take3/
