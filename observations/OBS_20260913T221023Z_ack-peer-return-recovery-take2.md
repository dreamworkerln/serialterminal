# Node observation

Observed: 2026-09-13T22:10:23Z
Task: focused reliable USER peer-return recovery take2
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup

- Sender `LoRa-Chatter-1B44`; peer `LoRa-Chatter-72E0` was physically powered off before the only USER injection.
- Both nodes used `/both`; ECHO was off.

## Evidence

- `PEER_RETURN_TAKE2_20260914T1020Z` entered `WAIT_ACK` as logical identity `EC14/13`.
- Attempt 1 timed out before peer return; retries 2/5 through 5/5 retained `seq=13` and the same payload.
- After peer return, peer observed `RX USER ... disposition=0` (NEW), displayed the payload once, sent ACK for `EC14/13`, and sender completed `DELIVERY ACK ... attempts=5/5 queue=0`.
- No delivery failure occurred; post-ACK observation showed no pending retry.

## Anomalies / conflicts

- Human power-on request/confirmation timestamps are not represented in SerialTerminal logs; their order relative to the first timeout is recorded in REPORT.md.

## Final state

- Both nodes `/chat`, ECHO off, `queued_tx=0`; sessions closed and agent ended via EOF.

Run bundle: runs/RUN_20260913T221023Z_ack-peer-return-recovery-take2/
