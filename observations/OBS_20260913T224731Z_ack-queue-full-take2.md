# Node observation

Observed: 2026-09-13T22:47:31Z
Task: focused reliable USER queue-full rejection, take 2
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup

- Sender `LoRa-Chatter-1B44`; peer `LoRa-Chatter-72E0` was powered off after setup.
- `/both`, echo `OFF`, initial `queued_tx=0`.

## Evidence

- In-flight USER reached `DELIVERY WAIT_ACK user=EC14/19 attempt=1/5 ... queue=0`.
- Before waiting injections were firmware-accepted, the first USER reached `DELIVERY FAILED ... attempts=5/5`.
- Late injections produced only `waiting=4/8 in_flight=1` and `INPUT QUEUE FULL dropped=3`; `waiting=8/8` was not reached.
- No overflow payload was sent and no queue-full rejection was observed.

## Anomalies / conflicts

- Timing/orchestration did not preserve the first USER in-flight long enough; this is INCONCLUSIVE, not firmware FAIL.

## Final state

- Sender `/chat`, `queued_tx=0`; `/cancel all` cleared remaining accepted queue entries.
- Sessions closed normally; peer remained powered off.

Run bundle: runs/RUN_20260913T224731Z_ack-queue-full-take2/
