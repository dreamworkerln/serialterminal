# Node observation

Observed: 2026-09-16T01:39:52Z
Task: focused BLE multi-connection diagnostic, symmetric take5
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@4f562062afd64750679a4d5562a29a022025a967
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup
- Capability discovery found LoRa-Chatter-1B44 (`44:1B:F6:8D:B7:A9`) and LoRa-Chatter-72E0 (`E0:72:A1:D5:4C:15`).
- One long-lived Chatter-profile agent process held target/peer BLE sessions; chat and telemetry remained separate.

## Actions
- Executed symmetric target-alone, idle-peer, concurrent-peer-output, and peer-closed phases with `/help` stimuli.

## Evidence
- Solo and post-peer-close help outputs were complete for both targets.
- Concurrent target raw chat segments were malformed in both directions: Pass 1 first target segment `s1` seq `634–698`; Pass 2 first target segment `s3` seq `702–764`.
- No SerialTerminal `forensic_gap` was recorded; exact raw events and `data_b64` are in the run log.

## Anomalies / conflicts
- Pass 1 Phase B contains only 2/3 target iterations; the next send became the first concurrent stimulus. This prevents a clean discriminator claim.
- No root cause assigned.

## Final state
- Nodes powered ON, CHAT, echo OFF, `queued_tx=0`; sessions closed normally; agent exited cleanly.

Run bundle: runs/RUN_20260916T013952Z_ble-multiconn-symmetric-take5/
