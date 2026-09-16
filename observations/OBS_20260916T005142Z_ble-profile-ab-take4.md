# Node observation

Observed: 2026-09-16T00:51:42Z
Task: focused BLE Generic/Chatter profile A/B diagnostic
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@4f562062afd64750679a4d5562a29a022025a967
Firmware: unknown

## Setup

- Same BLE target in three sequential sessions: Generic A, Chatter, Generic B.
- Canonical identity and address: LoRa-Chatter-1B44, `44:1B:F6:8D:B7:A9`.

## Evidence

- Generic A: 5/5 burst iterations byte-complete; streams `main`.
- Chatter: 5/5 burst iterations byte-complete; streams `chat` and `telemetry`, kept separate.
- Generic B: 5/5 burst iterations byte-complete; streams `main`.
- No forensic gap and no disconnect/reconnect affected a comparison iteration.

## Finding

The previously observed corruption did not reproduce in this single-node A/B run. Profile selection did not isolate a trigger; this run assigns no root cause to SerialTerminal or firmware.

## Final state

- Node remained powered on in CHAT with echo OFF and queued TX 0. All sessions closed normally.

Run bundle: runs/RUN_20260916T005142Z_ble-profile-ab-take4/
