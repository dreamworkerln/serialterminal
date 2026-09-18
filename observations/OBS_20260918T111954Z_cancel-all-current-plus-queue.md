# Node observation

Observed: 2026-09-18T11:19:54Z
Task: scenario 11 — `/cancel all` current reliable USER plus queue
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@ab36ca2405f6cf8dd1a4ce572e96c8de918a754f
Firmware: unknown

## Setup

- NODE A: `LoRa-Chatter-72E0`; NODE B: `LoRa-Chatter-1B44`.
- The operator ran the helper once outside the sandbox; no repeat is authorized.

## Actions

- Established current USER `909C/4` in `WAIT_ACK` and queued two additional USER messages.
- Issued `/cancel all` after the queue reached `waiting=2/8 in_flight=1`.

## Evidence

- `DELIVERY WAIT_ACK user=909C/4 attempt=1/5 timeout=1856ms queue=0`.
- `DELIVERY QUEUED source=2 bytes=32 waiting=2/8 in_flight=1`.
- `trigger_to_cancel_request_ms=0.594`.
- `DELIVERY CANCEL user=909C/4 attempts=1 status=unknown queue_removed=2`.
- `postcheck.current_retry_observed=false`.
- `postcheck.queue1_transmitted_or_presented=false`.
- `postcheck.queue2_transmitted_or_presented=false`.
- `measured_disconnect=false`; `send_outcome_unknown=false`.

## Anomalies / conflicts

- The exact append-only forensic log also contains two earlier attempts: `unknown_device` and sandbox `Operation not permitted`. Authoritative PASS evidence is only the third RUN segment beginning `2026-09-18T14:19:54.687+03:00`.
- Firmware provenance is unknown.

## Final state

- Both nodes were returned to `/chat`; sessions were closed normally.

Run bundle: runs/RUN_20260918T111954Z_cancel-all-current-plus-queue/
