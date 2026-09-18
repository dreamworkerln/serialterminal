# Node observation

Observed: 2026-09-18T10:11:18Z
Task: focused two-node Chatter cancel semantics validation
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@d0758d054c2519c97587ee2f6da02d087f1c145a
Firmware: unknown

## Setup
- Two dynamically discovered Chatter nodes were identity-matched across USB and BLE.
- Host Bluetooth audio preflight was clear; echo was OFF; A used `/both` during measurement.

## Actions
- Scenario 9 used one long USER and immediate BLE `/cancel`.
- Scenario 11 used one long current USER and two queued USERs; `/cancel all` was not repeated after the timing window passed.
- Scenario 10 was not forced with timing races.

## Evidence
- Scenario 9 PASS: `DELIVERY CANCEL user=909C/0 attempts=1 status=unknown queue_removed=0`; no later retry.
- Scenario 11 established `waiting=2/8 in_flight=1`, but current ACKed before cancellation; queued messages transmitted.
- Scenario 10 had no direct `not_transmitted=1` queue-only evidence.

## Anomalies / conflicts
- No measured BLE reconnect, forensic gap, or send outcome unknown.
- Physical firmware provenance was not independently verified.

## Final state
- Both nodes `/chat`, echo OFF, reliable flow empty, sessions closed.

Run bundle: runs/RUN_20260918T101118Z_two-node-cancel-semantics/
