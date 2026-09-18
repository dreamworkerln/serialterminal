# Node observation

Observed: 2026-09-18T09:15:33Z
Task: two-node production BLE help smoke
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@4f562062afd64750679a4d5562a29a022025a967
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup

- `LoRa-Chatter-1B44` paired as USB `s2` / BLE `s3`; `LoRa-Chatter-72E0` paired as USB `s1` / BLE `s4`.
- Host Bluetooth audio preflight was clear; `WH-1000XM5` was not connected and no BlueZ audio endpoint was present.

## Actions

- Ran exactly three rounds: BLE A `/help`, immediately BLE B `/help`; USB `/help` was never sent.
- Restored CHAT/echo OFF state, closed all sessions, and terminated the agent.

## Evidence

- Node A and Node B each returned coherent `COMPLETE` help in all 3/3 rounds through `observe.result.lines`.
- `[BLE-TX-DIAG]` was absent. 0003 human SYSTEM routing and 0004 background telemetry routing were observed as separate paths.
- One BLE disconnect/reconnect occurred on `s3` before measured round 1; no repeated disconnect was observed during measured rounds.

## Anomalies / conflicts

- Unexpected pre-measurement BLE reconnect prevents the overall PASS claim; root cause is not established.
- Operator-stated firmware SHAs were not independently verified.

## Final state

- Both nodes CHAT, echo OFF, no intentional reliable USER flow; all sessions closed.

Run bundle: runs/RUN_20260918T091533Z_ble-production-smoke/
