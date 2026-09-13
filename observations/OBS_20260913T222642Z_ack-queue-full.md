# Node observation

Observed: 2026-09-13T22:26:42Z
Task: focused reliable USER queue-full scenario
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup

- Sender `LoRa-Chatter-1B44`; powered-off/returned peer `LoRa-Chatter-72E0`.
- Peer was dynamically discovered, physically powered off, then returned and reconnected.

## Evidence

- Initial in-flight `QFULL_INFLIGHT_20260914T` (`EC14/16`) exhausted `5/5` before the requested waiting set was filled.
- Only `QFULL_WAIT_01_20260914T` and `QFULL_WAIT_02_20260914T` received reliable queue evidence; no `8/8` state occurred.
- The overflow probe was not sent, so exact `SEND QUEUE FULL` rejection and rejected-payload RF absence were not tested.

## Anomalies / conflicts

- The required timing window could not be maintained with the peer off; no cancellation or reboot was used to alter the state.

## Final state

- Both nodes connected, `/chat`, `echo=OFF`, host `queued_tx=0`; sessions closed and agent ended with normal EOF.

Run bundle: runs/RUN_20260913T222642Z_ack-queue-full/
