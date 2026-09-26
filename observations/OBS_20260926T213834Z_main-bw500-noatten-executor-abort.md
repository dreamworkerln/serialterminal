# Node observation

Observed: 2026-09-26T21:38:34Z
Task: MAIN matrix, BW500 kHz no-attenuator shard retry attempt
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@08c1b8d919cfb04c32068c9b9d63fdb1443139c9
Firmware: dreamworkerln/lora-sack-protocol@unknown

Run bundle: runs/RUN_20260926T213834Z_main-bw500-noatten-executor-abort/

## Setup

470 MHz, 2 dBm, BW500 kHz, BLE control, attenuators NONE. Node A was `LoRa-Chatter-1B44`; node B was `LoRa-Chatter-72E0`. Both were opened by the same fresh SerialTerminal process. The operator's RF topology was left unchanged.

## Actions

Both nodes were confirmed at SF7/BW500, 470 MHz, 2 dBm, heartbeat OFF, diagnostic OFF; echo-loop was stopped and `/cancel all` found no pending work. Three one-byte USER requests `A` were sent A→B. Each had a matching peer receive and sender ACK. The run stopped before B→A and before completing the required 10+10 anomaly extension.

## Evidence

The finalized log records two unsequenced header-error events and one unsequenced CRC event during the active SF7 / 1-byte point. It also records the matching ACK for all three A→B requests and no actual ACK timeout. The point is incomplete and INVALID; no RF conclusion is drawn. All other shard points are unmeasured.

## Anomalies / conflicts

The executor's broad event parser mistook periodic `hdr=4` SESSION counter text for a new HDR event and aborted. The real CRC/header observations remain part of this historical attempt. They were not reclassified as executor errors or discarded.

## Final state

Both queues were confirmed quiet, final configurations matched the required settings, both sessions were closed, and exact SerialTerminal PID 22133 was verified gone. This attempt is preserved as INCONCLUSIVE for audit. One fresh full-shard automatic retry is permitted; no samples from this attempt may be reused in it.
