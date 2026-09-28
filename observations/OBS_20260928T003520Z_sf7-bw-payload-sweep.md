# Node observation

Observed: 2026-09-28T00:35:20Z
Task: SF7 PHY / payload sweep at 2 dBm
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@7cf0459c4e00a81592d447e0592e83a1142e18d9
Firmware: dreamworkerln/lora-sack-protocol@unknown

Run bundle: runs/RUN_20260928T003520Z_sf7-bw-payload-sweep/

## Setup

Two BLE Chatter sessions: `s1` = LoRa-Chatter-1B44 and `s2` = LoRa-Chatter-72E0. Both `/config` responses established the shared 470 MHz baseline, SF7, BW500 kHz and 2 dBm.

## Actions

The main deterministic `chatter.reliable_user` sweep used `sweep_start` / `sweep_observe` / `sweep_close`, with `sweep_id=sw1`, BW 125/250/500 kHz, payloads 1/8/16/32/64/96/128/160/180/200 bytes, both `s1>s2` and `s2>s1`, and exactly 3 repetitions. It completed 180/180 samples. No measured sample was orchestrated through manual per-sample `send_line` calls.

Focused sweep `sw2` added 7 requests per direction for SF7/BW250 kHz/180 B. Focused sweep `sw3` added 7 requests per direction for SF7/BW500 kHz/1 B. Each extension completed 14/14, bringing each affected point to 10 total requests per direction including the original main-job samples.

## Evidence

The forensic log records an ACK timeout/retry at SF7/BW125 kHz/200 B in `s2>s1`, and RX CRC telemetry plus an ACK timeout/retry at SF7/BW250 kHz/180 B in `s1>s2`. RX HEADER ERROR telemetry was observed in the SF7/BW500 kHz/1 B measurement windows on both directions; it has no trusted USER sequence. The focused extensions had no further retry, CRC or header-error events. Other main-grid measurement windows had no observed retry, CRC or header-error event. No final delivery failure or measured USER overlap was found.

## Anomalies / conflicts

The two delivery timeout/retry points are degraded-but-delivered. CRC/header telemetry remains contextual RF evidence; it is not assigned a protocol sequence. A separate RX HEADER ERROR appeared after `sw1` completed and was outside the main measurement window. Firmware source identity was not established, and no firmware source was inspected.

## Final state

Both nodes returned to the verified 470 MHz / SF7 / BW500 kHz / 2 dBm configuration with heartbeat and diagnostic mode OFF. Sessions were closed and the SerialTerminal process was terminated.
