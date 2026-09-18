# Node observation

Observed: 2026-09-18T11:17:40Z
Task: Repeat scenario 11, cancel-all-current-plus-queue
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@ab36ca2405f6cf8dd1a4ce572e96c8de918a754f
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup

- Host Bluetooth/audio preflight found WH-1000XM5 paired but not connected; no Bluetooth audio endpoint or stream was present in PipeWire.
- Exact sender/peer USB and BLE keys and expected identities were passed to the helper.

## Actions

- Ran `scripts/run-chatter-scenario cancel-all-current-plus-queue` once.
- The helper started its own SerialTerminal process and issued `discover`.

## Evidence

- Helper result: `INCONCLUSIVE`.
- Exact error: `internal_error: [Errno 1] Operation not permitted`.
- Trigger `waiting>=2 ... in_flight=1` was not reached; `/cancel all` was not sent.
- `measured_disconnect=false`; `send_outcome_unknown=false`.

## Anomalies / conflicts

- Discovery failed before measured scenario execution due to the host permission boundary.
- No firmware or node state changes were performed. The previous immutable INCONCLUSIVE run was not touched.

## Final state

- No measured reconnect, cancellation, or postcheck evidence was produced.

Run bundle: runs/RUN_20260918T111740Z_cancel-all-current-plus-queue/
