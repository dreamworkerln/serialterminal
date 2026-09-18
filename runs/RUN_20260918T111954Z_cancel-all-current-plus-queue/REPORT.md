# Scenario 11: `/cancel all` current plus queue

Observed: 2026-09-18T11:19:54Z
Result: PASS

## Request and provenance

- The operator manually ran `scripts/run-chatter-scenario cancel-all-current-plus-queue` once outside the sandbox and reported `result=PASS`.
- SerialTerminal: `dreamworkerln/serialterminal@ab36ca2405f6cf8dd1a4ce572e96c8de918a754f`.
- Firmware provenance: `unknown`.
- Exact source logs are copied byte-for-byte from `/tmp/serialterminal-cancel11.log` and `/tmp/serialterminal-cancel11.console.log`.
- The forensic logfile is append-only and contains three RUN segments. The authoritative PASS evidence is the third RUN segment beginning at `2026-09-18T14:19:54.687+03:00`; the preceding `unknown_device` segment and sandbox `Operation not permitted` segment are earlier recorded attempts and are not reconstructed or deleted.

## Hardware context

- NODE A: `LoRa-Chatter-72E0`.
- NODE B: `LoRa-Chatter-1B44`.
- The measured sender flow used current reliable USER `909C/4` with two queued USER messages.
- Firmware provenance remains unknown; no firmware revision is inferred from this run.

## Measured evidence

- `DELIVERY WAIT_ACK user=909C/4 attempt=1/5 timeout=1856ms queue=0`.
- `DELIVERY QUEUED source=2 bytes=32 waiting=2/8 in_flight=1`.
- `/cancel all` was requested 0.594 ms after the trigger: `trigger_to_cancel_request_ms=0.594`.
- `DELIVERY CANCEL user=909C/4 attempts=1 status=unknown queue_removed=2`.
- `postcheck.current_retry_observed=false`.
- `postcheck.queue1_transmitted_or_presented=false`.
- `postcheck.queue2_transmitted_or_presented=false`.
- `measured_disconnect=false`.
- `send_outcome_unknown=false`.

The current USER had already reached physical attempt 1, so cancellation status was correctly `unknown`; the PASS criterion is that the current retry and both queued messages were stopped/removed after the cancellation request. The later ACK was reported as unmatched with no pending delivery.

## Final state

- The helper's final cleanup returned both nodes to `/chat`.
- Sessions `s1` through `s4` were closed and the agent process stopped normally at `2026-09-18T14:21:01.786+03:00`.
- Scenario 11 must not be rerun based on this result.

