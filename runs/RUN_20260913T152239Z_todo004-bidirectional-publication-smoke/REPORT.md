# TODO_004 node run report

## Task

Physical validation of reliable USER delivery in both directions between two dynamically discovered LoRa-Chatter nodes, followed by immutable RUN + OBS publication.

## Revisions

- SerialTerminal: `dreamworkerln/serialterminal@c9c6d4099c3532494bac8bfecb9fead37e27fe1e` (branch `dev`).
- Firmware: `unknown`; the exact SHA physically flashed on either node was not independently established.

## Hardware/session context

- Discovery in one agent process found two BLE paths; sessions were `s1` and `s2`.
- Canonical `/id` identities: `s1` = `LoRa-Chatter-1B44`; `s2` = `LoRa-Chatter-72E0`.
- Both sessions exposed `chat` and `telemetry`; `/both` was confirmed on both nodes.

## Scenario verdicts

### A → B: PASS

Payload: `T004_AB_20260913T1830Z` (22 UTF-8 bytes).

- Sender `s1` telemetry: `TX USER seq=0 frame=34B user=22B attempt=1/5 OK`.
- Sender `s1` human console: `> T004_AB_20260913T1830Z` and `DELIVERY WAIT_ACK user=EC14/0`.
- Peer `s2` human console: `< [-30/+9 Q100] T004_AB_20260913T1830Z`.
- Peer `s2` telemetry: `RX USER session=EC14 seq=0 ... disposition=0`.
- Sender `s1` matching telemetry: `RX ACK ... ack_to=EC14/0` and `DELIVERY ACK user=EC14/0 attempts=1/5 ... queue=0`.

### B → A: INCONCLUSIVE

Payload: `T004_BA_20260913T1835Z` (22 UTF-8 bytes).

- Sender `s2` reached `TX USER seq=1 ... attempt=1/5 OK` and `DELIVERY WAIT_ACK user=85BC/1`.
- The two BLE sessions repeatedly disconnected/reconnected while the sender was waiting. No matching A-side peer USER presentation or `DELIVERY ACK user=85BC/1` was observed before the requested stop.
- The last observed node telemetry showed `s2` counters `TX ok=2 user=1`, `RX ok=2 user=1`, with no second delivery completion.

## Attempts, retries, and queue state

Both completed USER deliveries used one physical attempt; no reliable retry was observed. A→B queue reached `waiting=1/8`, then `queue=0` on matching ACK. B→A reached `waiting=1/8`; host session status before close reported `queued_tx=0`, but firmware reliable state was not confirmed complete. No fault injection was used.

## Observation views

All receive evidence came through canonical `observe`: completed protocol lines were taken from `result.lines`, and raw BLE chunks/state/TX records from `result.events`. Returned cursors were advanced throughout the run. The exact raw events and `data_b64` are retained in `serialterminal.log`; the companion console log is retained unchanged.

## Anomalies and limitations

Repeated natural BLE disconnect/reconnect cycles affected both sessions, especially `s1`, and prevented completion of B→A acceptance criteria. Firmware SHA could not be independently established. No reboot or firmware reflash was performed.

## Final state

Both nodes were commanded back to `/chat`; `/chat` was confirmed on both. Both SerialTerminal sessions were closed and the single agent process was terminated. Hardware delivery state for the interrupted B→A message remains unknown.

## Artifacts

- `runs/RUN_20260913T152239Z_todo004-bidirectional-publication-smoke/serialterminal.log`
- `runs/RUN_20260913T152239Z_todo004-bidirectional-publication-smoke/serialterminal.console.log`
- `runs/RUN_20260913T152239Z_todo004-bidirectional-publication-smoke/REPORT.md`
- `observations/OBS_20260913T152239Z_todo004-bidirectional-publication-smoke.md`
