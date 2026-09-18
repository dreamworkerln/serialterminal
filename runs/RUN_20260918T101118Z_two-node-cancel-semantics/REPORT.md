# Focused two-node hardware validation: cancel semantics

Observed 2026-09-18T10:11:18Z. Operator-stated firmware target was `dreamworkerln/lora-sack-protocol@c4adef768a6e07b62a60b878d6c10fd273fc3409`, but physical provenance was not independently verified; canonical firmware provenance is `unknown`.

## Hardware context

- NODE A: `LoRa-Chatter-72E0`; USB serial `5B8F021956`, BLE `E0:72:A1:D5:4C:15`.
- NODE B: `LoRa-Chatter-1B44`; USB serial `5B8F072180`, BLE `44:1B:F6:8D:B7:A9`.
- Four sessions were opened simultaneously with `profile=chatter` using dynamic discovery.
- Host Bluetooth audio preflight was CLEAR: only built-in audio was present; no Bluetooth audio endpoint/profile/stream was observed.
- No firmware change, flashing, reboot, RF fault injection, host Bluetooth change, or node power change was performed.

## Results

### Scenario 9 — `/cancel` on in-flight USER: PASS

Unique payload `CANCEL9_CURRENT_20260918_001_...` produced direct A-side evidence:

- `DELIVERY WAIT_ACK user=909C/0 attempt=1/5 ... queue=0`.
- `DELIVERY CANCEL user=909C/0 attempts=1 status=unknown queue_removed=0`.
- `[SYS] DELIVERY CANCELLED: status unknown`.
- No retry or `DELIVERY FAILED` for `909C/0` appeared during the 30-second observation.
- B displayed the payload once. The later ACK was reported as `ACK UNMATCHED ... pending=none`, consistent with cancellation after physical attempt.

### Scenario 11 — `/cancel all` with current plus queued USERs: INCONCLUSIVE

The run established `waiting=2/8 in_flight=1` for the two queued messages while current `909C/1` was in `WAIT_ACK`. Before a cancellaton command could be applied, current received a matching ACK; `QUEUE1` and then `QUEUE2` were subsequently transmitted and ACKed. Per task rules, no timing rerun was attempted, and the required current-cancel-plus-queue-clear result was not claimed.

Cleanup `/cancel all` was issued separately after the remaining flow had already completed and returned `pending=none queue_removed=0`.

### Scenario 10 — `/cancel` on unsent queued USER: INCONCLUSIVE

No deterministic queue-only state with direct `not_transmitted=1` evidence was externally established. No repeated timing race or command flooding was attempted.

## Final state

Both nodes were returned to `/chat`; echo remained OFF; no intentionally pending or queued reliable USER remained. All four sessions were closed and the SerialTerminal process exited normally. The exact forensic and companion logs in this bundle are the canonical evidence.

