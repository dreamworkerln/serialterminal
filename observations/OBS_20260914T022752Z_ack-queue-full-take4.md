# Node observation

Observed: 2026-09-14T02:32:53Z
Task: focused hardware scenario queue full -> explicit rejection, take4
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup

- Sender `LoRa-Chatter-1B44`; peer `LoRa-Chatter-72E0` powered off during probe.
- Both sessions used `profile: "chatter"`; no firmware change or reboot.

## Actions

- Established `QFULL4_INFLIGHT_20260914T` as `WAIT_ACK`.
- Submitted four waiting payloads without artificial sleeps.
- Restored peer and allowed accepted queue to drain naturally.

## Evidence

- `DELIVERY QUEUED` progression reached only `1/8`, `2/8`, `3/8`, each with `in_flight=1`.
- Initial USER `EC14/26` reached terminal `DELIVERY FAILED` before `waiting=8/8`.
- No `INPUT QUEUE FULL` occurred in this run; no overflow probe or exact `SEND QUEUE FULL` result was produced.
- After peer return, accepted queue drained to `queue=0`; both nodes ended connected in `/chat` with echo `OFF` and host `queued_tx=0`.

## Anomalies / conflicts

- Observation latency allowed the initial USER to progress through retries before the first waiting batch was processed; per task rules this is orchestration/timing `INCONCLUSIVE`, not a firmware queue verdict.

## Final state

- Peer restored, sessions closed, agent exited normally.

Run bundle: runs/RUN_20260914T022752Z_ack-queue-full-take4/
