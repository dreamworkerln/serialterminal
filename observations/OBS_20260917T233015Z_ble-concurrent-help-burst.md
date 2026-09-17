# Node observation

Observed: 2026-09-17T23:33:45Z
Task: Three concurrent BLE `/help` rounds on LoRa-Chatter-1B44 and LoRa-Chatter-72E0.
Result: FAIL
SerialTerminal: dreamworkerln/serialterminal@5354f062afd64750679a4d5562a29a022025a967
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup

- Two simultaneous `profile:"chatter"` BLE sessions: `s1`=1B44 and `s2`=72E0.
- Both were placed in `/chat`; both remained connected after initial open.

## Actions

- Round 1: 1B44 then 72E0.
- Round 2: 72E0 then 1B44.
- Round 3: both `/help` sends in one API batch.

## Evidence

- 1B44: MALFORMED in rounds 1, 2, and 3.
- 72E0: COMPLETE in rounds 1, 2, and 3.
- No persisted `forensic_gap`, disconnect/reconnect during the burst, or same-node command overlap was observed.

## Anomalies / conflicts

- Raw/logical help output for 1B44 contained incomplete and visibly mixed lines during each concurrent round.
- No cause of the observed malformed output is inferred.

## Final state

- Both sessions were closed through the agent API. No reboot or power cycle was performed.

Run bundle: runs/RUN_20260917T233015Z_ble-concurrent-help-burst/

