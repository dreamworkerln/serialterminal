# Node observation

Observed: 2026-09-21T03:42:43Z  
Task: TODO_006 link-quality / heartbeat diagnostic hardware validation  
Result: INCONCLUSIVE  
Primary measured transport: BLE  
SerialTerminal: dreamworkerln/serialterminal@1c8b42830780d65b0f5daefd4d23275ac7c56ac7  
Firmware: dreamworkerln/lora-sack-protocol@6c08084891f4940dcbe804c0c4ef26feea9b4eb5

## Setup

- Host Bluetooth/audio preflight passed: no connected Bluetooth audio endpoint or active Bluetooth audio stream.
- Capability-based BLE discovery found `LoRa-Chatter-1B44` and `LoRa-Chatter-72E0`.
- BLE sessions used `profile: chatter`; USB was not used for measured interactions.
- Both `/version` provenance gates matched `git=6c08084891f4940dcbe804c0c4ef26feea9b4eb5 state=clean`.

## Evidence

- Both directions of reliable USER traffic completed with matching ACKs; retry attempts and ACK timeouts were recorded as separate transaction-Q samples.
- Correlated BLE telemetry showed heartbeat PING/PONG sequence matching, directional RSSI/SNR/Q (`RX`, peer `TX`, `RQ`, `TQ`), and no response loop.
- NRP timeouts occurred naturally during concurrent activity; subsequent heartbeat sequence numbers advanced without same-sequence retransmission.
- BLE diagnostic RF frame sizes 16B, 32B, 64B, and 200B were confirmed in PING/PONG telemetry. Diagnostic mode returned to 16B after the 200B test, demonstrating non-persistence.
- BLE human output included `[LNK OK]`, `[LNK NRP]`, and multiple `[DIAG] ... [30S] ... RQ=... TQ=...` summaries. Commands remained usable during active output.
- Legacy ECHO request/reply smoke passed. Final CHAT USER smoke passed in both directions; `/cancel` reported no pending delivery.

## Not observed

255B diagnostic frame, physical edge-of-link movement/shielding, CRC/HDR degradation classes, controlled PING-loss retransmission, and separate duplicate-injection suppression were not observed. The run therefore remains `INCONCLUSIVE`; TODO_006 is not closed.

## Final state

Both nodes were left in `CHAT` with `heartbeat=OFF`, `diag=OFF`, and no pending delivery. Sessions were closed normally.

Run bundle: runs/RUN_20260921T034243Z_todo-006-ble-hardware-validation/
