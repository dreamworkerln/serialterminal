# Node observation

Observed: 2026-09-13T15:22:39Z
Task: TODO_004 bidirectional reliable USER publication smoke
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@c9c6d4099c3532494bac8bfecb9fead37e27fe1e
Firmware: unknown

## Setup

- Two dynamically discovered BLE nodes were opened in one agent process and identified as `LoRa-Chatter-1B44` and `LoRa-Chatter-72E0`.

## Evidence

- A→B `T004_AB_20260913T1830Z` passed with peer `<` presentation, peer `RX USER`, matching `RX ACK`, and sender `DELIVERY ACK`, all on one attempt.
- B→A `T004_BA_20260913T1835Z` reached sender `TX USER` and `WAIT_ACK`, but repeated natural BLE reconnects prevented observing peer presentation and matching delivery ACK before stop.

## Anomalies / conflicts

- Repeated BLE disconnect/reconnect cycles; no fault injection. Exact flashed firmware SHA was not independently known.

## Final state

- Both nodes returned to `/chat`; sessions closed; agent process terminated.

Run bundle: runs/RUN_20260913T152239Z_todo004-bidirectional-publication-smoke/
