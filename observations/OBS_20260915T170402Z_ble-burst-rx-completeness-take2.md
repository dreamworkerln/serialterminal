# Node observation

Observed: 2026-09-15T17:04:02Z
Task: focused BLE RX completeness diagnostic, isolated and burst `/help`
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@276aeee2ca90e6ee964120153bf72e5dbafcf307
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup

- LoRa-Chatter-1B44 (`s1`) and LoRa-Chatter-72E0 (`s2`) opened over BLE with profile `chatter`.
- Both sessions connected; no disconnect/reconnect occurred during affected intervals.

## Evidence

- LoRa-Chatter-1B44 isolated `/help` was byte-complete through the late help sections.
- LoRa-Chatter-72E0 isolated `/help` was already malformed at raw chat seq 70–71 and 96–97.
- Concurrent `/help`: 5/5 iterations completed, with malformed/baseline-inconclusive session-cases in both sessions.
- Burst `/help` + `/id`: 5/5 iterations completed, with malformed/interleaved session-cases in both sessions.
- No `forensic_gap` was recorded. Exact raw `data_b64`, text, seq ranges, and completed lines are in the matching run bundle.

Finding boundary: malformed or missing expected BLE `chat` content was observed before ManagedSession logical-line completion; ownership below the recorded callback/event boundary remains unresolved.

## Final state

- Output `CHAT`, echo OFF, no queued TX; sessions closed normally; agent exited cleanly.

Run bundle: runs/RUN_20260915T170402Z_ble-burst-rx-completeness-take2/
