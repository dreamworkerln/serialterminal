# TODO_006 — LINK QUALITY / HEARTBEAT DIAGNOSTIC

Result: INCONCLUSIVE  
Observed: 2026-09-21T03:42:43Z  
Primary measured transport: BLE

## Scope and provenance

This is a new run identity. The historical `RUN_20260921T031341Z_todo-006-hardware-validation` was not modified.

Firmware expected checkpoint:

`dreamworkerln/lora-sack-protocol@6c08084891f4940dcbe804c0c4ef26feea9b4eb5`, `state=clean`, protocol wire v3.

SerialTerminal was `dreamworkerln/serialterminal@1c8b42830780d65b0f5daefd4d23275ac7c56ac7`.

Both BLE `/version` gates matched the expected firmware SHA and clean state. Both exposed the full provenance block: `FIRMWARE`, `FIRMWARE IMAGE ... status=OK`, and `BUILD META`.

Host Bluetooth/audio preflight found no connected Bluetooth audio endpoint or active Bluetooth audio stream. Discovery was capability-based; no device key, MAC, or USB path was hard-coded.

## Nodes and transport

- Node A: `LoRa-Chatter-1B44`, BLE session `s1`, device key discovered as `ble-address:44:1b:f6:8d:b7:a9`.
- Node B: `LoRa-Chatter-72E0`, BLE session `s2`, device key discovered as `ble-address:e0:72:a1:d5:4c:15`.
- Both sessions used `profile: chatter`; BLE chat and telemetry streams remained independent.
- USB was not used for measured interactions.

## Validation matrix

| Gate | Result | Evidence summary |
|---|---|---|
| Provenance A/B | PASS | Both report `git=6c080848... state=clean`; image status OK and build metadata present. |
| BLE identity A/B | PASS | `/id` returned `LoRa-Chatter-1B44` and `LoRa-Chatter-72E0`. |
| BLE USER A→B / B→A | PASS | Both final USER messages were received and ACKed; both used retry attempt 2 after a first ACK timeout. |
| Transaction-Q | PASS | Physical attempts were evidenced separately: timeout/retry and later matching ACK; no retry was counted as a new logical USER sample. |
| Heartbeat PING/PONG | PASS | Correlated request/session/sequence pairs observed in BLE telemetry. |
| Directional RSSI/SNR/Q | PASS | PONG telemetry exposed local RX and peer TX metrics plus RQ/TQ; BLE `[LNK OK]` lines were also received. |
| No response loop | PASS | No PONG-triggered PONG loop observed. |
| No heartbeat retransmission | PASS | Natural NRP timeouts advanced to new sequence values; no same-sequence heartbeat retransmission observed. |
| USER/heartbeat coexistence | PASS | Reliable USER remained active while heartbeat activity occurred; ACK completed after retry. |
| Diagnostic heartbeat restore OFF | PASS | `/heartbeat off` → `/diag on` produced effective `heartbeat=ON`, then `/diag off` restored `heartbeat=OFF`, `diag=OFF`. |
| Diagnostic heartbeat restore ON | PASS | Controlled retry after a BUSY boundary established `/heartbeat on` + `/diag on` → `/diag off`; final config retained `heartbeat=ON` during that lifecycle. |
| Diagnostic sizes 16B / 32B / 64B / 200B | PASS | BLE telemetry confirmed actual PING/PONG RF frame sizes at each requested size. |
| Diagnostic size 255B | NOT OBSERVED | Optional size was not tested. |
| Diagnostic non-persistence | PASS | After `200B`, `/diag off` → `/diag on` returned `frame=16B` on both nodes; no reboot/reconnect was needed. |
| LNK presentation over BLE | PASS | `[LNK OK]` and `[LNK NRP]` lines had fixed RX/TX columns and `---/---` unavailable metrics; frame size was not repeated in each LNK row. |
| 30-second summary over BLE | PASS | Multiple `[DIAG] ... [30S] ... RQ=... TQ=...` summaries observed. |
| Commands during BLE diagnostic stream | PASS | `/config`, `/diag`, and size commands were accepted while BLE chat/telemetry output streamed. A rapid burst also produced allowed `DIAG BUSY` and input-queue-full evidence; isolated commands continued to work. |
| CRC/HDR/NRP state | INCONCLUSIVE | NRP was observed and correlated with heartbeat timeouts; CRC and HDR error classes were not observed. |
| Edge-of-link behavior | NOT OBSERVED | No physical movement or shielding was performed. |
| Legacy ECHO smoke | PASS | `/echo` enabled legacy mode; an ECHO request/reply with matching sequence and payload was observed; `/echo` then returned both nodes to OFF. |
| Final BLE USER smoke | PASS | Both directions delivered CHAT USER output and matching ACKs; `/cancel` returned `nothing pending`; `/config` and `/chat` worked. |
| Duplicate suppression | NOT OBSERVED | No separate duplicate-injection scenario was performed. |

## Notes and final state

The run is `INCONCLUSIVE` because optional 255B, physical edge-of-link, CRC/HDR degradation, controlled PING-loss retransmission, and duplicate-injection gates were not observed. This is not a source-development or firmware-fix report.

Final BLE commands set both nodes to human CHAT mode with `heartbeat=OFF`, `diag=OFF`, retry still enabled with five attempts, and no pending delivery. Sessions were closed cleanly. Exact JSONL forensic and companion console logs are stored in this bundle.
