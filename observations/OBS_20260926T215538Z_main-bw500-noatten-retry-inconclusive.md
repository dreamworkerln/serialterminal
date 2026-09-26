# Node observation

Observed: 2026-09-26T21:55:38Z
Task: MAIN matrix BW500 no-attenuator automatic retry
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@08c1b8d919cfb04c32068c9b9d63fdb1443139c9
Firmware: dreamworkerln/lora-sack-protocol@unknown

Run bundle: runs/RUN_20260926T215538Z_main-bw500-noatten-retry-inconclusive/

## Setup

470 MHz, 2 dBm, BW500 kHz, BLE control, attenuators NONE. Node A was `LoRa-Chatter-1B44`; node B was `LoRa-Chatter-72E0`. A fresh process discovered and opened both nodes. RF topology was unchanged.

## Actions

The retry started at SF7 / 1 byte and completed all ten SF7 points. The 1-byte point had one CRC event and was extended to 10 total logical USER requests per direction. The executor then applied SF8 on both nodes and stopped at its configuration confirmation step; no SF8 measured USER was submitted.

## Evidence

The completed SF7 / 1-byte point was DEGRADED by one unsequenced CRC event; all 20 USER requests received matching ACKs on their first physical attempt. The other nine completed SF7 points were CLEAN at 3 requests per direction. SF8–12 remain unmeasured.

## Anomalies / conflicts

The executor waited for `/config` output without issuing `/config` after `/sf 8`; the setter had returned `SF 8 SAVED` on both nodes. Cleanup `/config` confirmed both at SF8. This was the one allowed automatic retry, so no further retry was made.

## Final state

Both queues were quiet, both sessions were closed, and exact SerialTerminal PID 23593 was verified gone. Final config was 2 dBm, 470 MHz, SF8/BW500, heartbeat OFF, diagnostic OFF. The complete SF7 evidence remains in this RUN; it is not combined with the previous failed RUN.
