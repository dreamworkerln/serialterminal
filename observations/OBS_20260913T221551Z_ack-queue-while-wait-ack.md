# Node observation

Observed: 2026-09-13T22:15:51Z
Task: additional USER while WAIT_ACK — queued and later delivered
Result: FAIL
SerialTerminal: dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup

- Sender `LoRa-Chatter-1B44`; powered-off/returned peer `LoRa-Chatter-72E0`.
- Peer was physically off during FIRST retry lifecycle; it returned after the queue was confirmed.

## Actions

- FIRST `QUEUE_WAIT_FIRST_20260914T143200Z` became `EC14/14`, entered `WAIT_ACK`, and retried through attempt `5/5`.
- SECOND `QUEUE_WAIT_SECOND_20260914T143200Z` was accepted while FIRST was pending with exact telemetry `waiting=1/8 in_flight=1`.

## Evidence

- No SECOND physical TX occurred before FIRST completed.
- FIRST ended `DELIVERY FAILED ... attempts=5/5 queue=1` before peer reconnect.
- SECOND then became `EC14/15`, was received once by the peer, ACKed, and completed with `DELIVERY ACK ... attempts=4/5 queue=0`.

## Anomalies / conflicts

- The requested contract requires peer return before FIRST final failure and SECOND transmission after FIRST successful ACK. Both conditions were false in this run.

## Final state

- Both nodes `/chat`, connected, host `queued_tx=0`; 12-second post-delivery observation had no new events. Sessions closed; agent exited through EOF.

Run bundle: runs/RUN_20260913T221551Z_ack-queue-while-wait-ack/

