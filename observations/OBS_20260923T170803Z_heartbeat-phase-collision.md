# Node observation

Observed: 2026-09-23T17:08:03Z
Task: TODO_008_HEARTBEAT_PHASE_COLLISION canonical two-node heartbeat collision investigation
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@0db99efb5155ca0068d6dd3ecf6ed0f272537a10
Firmware: dreamworkerln/lora-sack-protocol@8b62d6c4d50577da6a8927e52f123645d63f24a5, clean, image validation OK

## Finding

At SF12/BW125 and 2 dBm, both nodes repeatedly started heartbeat PINGs within 2.241–132.772 ms of one another; PING ToA was measured as 1156 ms, so every same-request paired start was airtime-overlap compatible. Eleven same-request paired cycles produced NRP on both nodes. The next paired deltas remained below PING ToA for several cycles, but successful peer PING/PONG exchanges at requests 25, 33 and 36 interrupted the sequence and provided observed decorrelation. Therefore the run does not prove persistent phase re-lock as root cause.

Run bundle: runs/RUN_20260923T170803Z_heartbeat-phase-collision/
