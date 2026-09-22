# Node observation

Observed: 2026-09-22T06:27:42Z
Task: reliable USER retransmission under ACK loss
Result: BLOCKED
SerialTerminal: dreamworkerln/serialterminal@fedfa29d5c8b07613e49e9425bbc2bbc5b74c165
Firmware: dreamworkerln/lora-sack-protocol@608f1cd26d76a1b02d3401cbd17a9b4c9ab44716

## Setup

- BLE Chatter sessions: A `LoRa-Chatter-1B44` (sender), B `LoRa-Chatter-72E0` (receiver/ACK sender).
- Both physical nodes self-reported the exact firmware SHA with `state=clean`.
- Bluetooth audio preflight had no connected Bluetooth audio endpoint or active Bluetooth audio path.
- Both nodes were verified at 2 dBm, 470 MHz, SF12, BW125; heartbeat/diag/echo-loop were off/stopped.

## Evidence

- Bidirectional 2 dBm baseline delivered and ACKed A USER `80AB/0` and B USER `3723/1` on first attempts.
- Baseline USER receive levels were approximately -28/-27 dBm, showing a strong two-way link.
- No ACK-loss payload was sent: a safe, reproducible physical asymmetric A->B/B->A RF condition was unavailable through the session interface.

## Anomalies / conflicts

- The exact fixed forensic log path contained two earlier RUN segments before the current executor segment; no forensic_gap record was present. The immutable RUN retains the exact unmodified log and documents this boundary.

## Final state

- Both nodes were returned and confirmed at 2 dBm; heartbeat OFF, diag OFF, echo-loop stopped.
- Both BLE sessions closed.

Run bundle: runs/RUN_20260922T062742Z_reliable-user-ack-loss-retry/
