# Node observation

Observed: 2026-09-18T00:54:43Z
Task: final correlated BLE `/help` burst on two physical Chatter nodes
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@4f562062afd64750679a4d5562a29a022025a967
Firmware: unknown

## Setup

- One agent process; BLE sessions `s1` = LoRa-Chatter-1B44 and `s2` = LoRa-Chatter-72E0; explicit `profile: chatter`.
- Both sessions reached `connected` and CHAT before the burst.

## Actions

- Exactly three rounds of `/help`: round 1 `s1→s2`, round 2 `s2→s1`, round 3 batch `s1+s2`.
- Six sends returned `written`; no reboot or power-cycle.

## Evidence

- All six isolated help responses were COMPLETE and reached the final BLE-client help line.
- Raw ranges: s1 rounds 1/2/3 = `38–130`, `158–250`, `253–345`; s2 rounds 1/2/3 = `38–130`, `133–225`, `253–345`.
- Forensic gap, cursor expiry, disconnect/reconnect during burst, send-outcome-unknown, and same-node overlap were not observed.

## Anomalies / conflicts

- none

## Final state

- Final status for both sessions: `connected`, `queued_tx=0`; both were closed through the agent API.

Run bundle: runs/RUN_20260918T005040Z_ble-correlated-help-burst/
