# Node observation

Observed: 2026-09-13T22:03:23Z
Task: focused reliable USER peer-return recovery
Result: FAIL
SerialTerminal: dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup

- Sender `LoRa-Chatter-1B44`; peer `LoRa-Chatter-72E0` was physically powered off before injection.
- Both sessions used `/both`; only one USER was sent: `PEER_RETURN_20260914T0945Z`.

## Evidence

- Logical USER identity `EC14/12` survived retries with unchanged `seq=12` and payload.
- Attempts 1/5 through 5/5 each completed physically; attempt 1 entered `WAIT_ACK`, timed out, and scheduled retry.
- Peer transport later progressed `disconnected` -> `reconnecting` -> connected, but only after sender emitted `DELIVERY FAILED ... attempts=5/5` and `[SYS] DELIVERY FAILED: no ACK`.
- No peer RX USER or ACK was observable; no sender matching ACK or DELIVERY ACK occurred.

## Anomalies / conflicts

- Peer return was too late for this bounded retry window. Human request/confirmation timestamps are not present in the SerialTerminal agent logs.

## Final state

- Both nodes were set to `/chat`; final statuses were connected with `queued_tx=0`; sessions closed; agent ended via EOF.

Run bundle: runs/RUN_20260913T220323Z_ack-peer-return-recovery/
