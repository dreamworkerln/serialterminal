# Node observation

Observed: 2026-09-26T21:00:56Z
Task: MAIN MATRIX BW500 no-attenuator shard, SF7–12
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@08c1b8d919cfb04c32068c9b9d63fdb1443139c9
Firmware: dreamworkerln/lora-sack-protocol@unknown (both nodes reported a dirty source state)

Run bundle: runs/RUN_20260926T210056Z_main-bw500-noatten/

## Setup

470 MHz, BW500 kHz, 2 dBm, no inline RF attenuators. A was LoRa-Chatter-1B44; B was LoRa-Chatter-72E0. BLE transport.

## Actions

SF7/1-byte requests completed 10 per direction; all 20 had matching first-attempt delivery ACKs. SF7/8-byte traffic was extended to 10 requests per direction after CRC/HDR evidence; one receiver USER lacked matching sender TX/ACK telemetry. A partial SF7/16-byte point followed before a clean-state recovery.

## Evidence

SF7/1B had three unsequenced header errors and one unsequenced CRC error during its point window. SF7/8B had two header errors, one CRC error, and a one-record sender/receiver count mismatch. No retries, actual ACK timeouts, or final delivery failures were observed. The 8B discrepancy is ambiguous; no physical-node fault is localized.

## Anomalies / conflicts

The task-local observation loop failed to associate receiver evidence that appeared before sender identity in an observation response. Traffic already submitted continued after the stop request. SF7/8B and subsequent SF7/16B are invalid; all later requested points are unmeasured. Pre-launch existence verification of the unique log pair was also omitted.

## Final state

Both nodes reported 2 dBm, 470 MHz, SF7/BW500, heartbeat OFF, diagnostic OFF, retry ON with 5 attempts; echo loop stopped, no pending reliable work, sessions closed.
