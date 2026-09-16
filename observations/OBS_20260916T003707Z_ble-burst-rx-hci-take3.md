# Node observation

Observed: 2026-09-16T00:37:07Z
Task: BLE burst RX completeness diagnostic with operator-owned HCI correlation
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@4f562062afd64750679a4d5562a29a022025a967
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup

- Two Chatter BLE sessions were opened: LoRa-Chatter-1B44 (`s1`) and LoRa-Chatter-72E0 (`s2`).
- The operator supplied `/tmp/ble-burst-rx-hci-take3.btsnoop` and `/tmp/ble-burst-rx-hci-take3.btmon.log`; the executor did not manage btmon.

## Evidence

- Isolated `/help` completed its late help markers on both nodes.
- Five concurrent `/help` iterations reproduced malformed/incomplete output on `s1`; five `/help` + `/id` burst iterations reproduced malformed/interleaved output, especially on `s1`.
- HCI-to-SerialTerminal comparison was exact for chat and telemetry, including notification order and bytes: 819/13,878 and 1,021/17,178 chat notifications, plus 54/976 and 54/968 telemetry notifications.
- No `forensic_gap` occurred. No affected-interval disconnect/reconnect occurred.
- The malformed content was already present in the HCI notification payload sequence, so host-side callback/event loss was not observed. A deeper owner remains unresolved.

## Anomalies / conflicts

- The run remains `INCONCLUSIVE` because HCI correlation isolates the host boundary but cannot identify the lower-level source of the malformed notification content.

## Final state

- Both nodes were left in `CHAT`, with zero queued TX; sessions closed normally and the agent exited cleanly.

Run bundle: runs/RUN_20260916T003707Z_ble-burst-rx-hci-take3/
