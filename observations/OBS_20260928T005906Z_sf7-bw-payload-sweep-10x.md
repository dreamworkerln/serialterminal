# Node observation

Observed: 2026-09-28T00:59:06Z
Task: SF7 PHY / payload sweep with 10 repetitions
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@7cf0459c4e00a81592d447e0592e83a1142e18d9
Firmware: dreamworkerln/lora-sack-protocol@unknown

Run bundle: runs/RUN_20260928T005906Z_sf7-bw-payload-sweep-10x/

## Setup

BLE Chatter sessions: `s1` = LoRa-Chatter-1B44 and `s2` = LoRa-Chatter-72E0. Both pre-run `/config` responses established 470 MHz, SF7, BW500 kHz and 2 dBm.

## Actions

One deterministic `chatter.reliable_user` generic sweep used BW 125/250/500 kHz, payloads 1/8/16/32/64/96/128/160/180/200 bytes, both `s1>s2` and `s2>s1`, and exactly 10 repetitions per coordinate. `sweep_id=sw1` completed 600/600 samples and was closed through the API.

## Evidence

The recorded result covers execution and the requested measurement matrix. Per operator instruction, anomaly/RF-quality analysis was not performed; RF-quality result is INCONCLUSIVE.

## Anomalies / conflicts

Not analyzed by operator instruction. No anomaly classification is asserted in this observation.

## Final state

The sweep adapter ran bounded cleanup; both sessions were closed and the SerialTerminal process was terminated.
