# Hardware characterization report

## Task and scope

- Task class: `CANONICAL_RUN`.
- Campaign/shard: MAIN MATRIX, BW500 kHz, 470 MHz, 2 dBm, attenuators NONE.
- Requested SFs: 7–12. Requested payloads: 1, 8, 16, 32, 64, 96, 128, 160, 180 and 200 USER bytes. Requested directions: A→B then B→A.
- Requested point depth: 3 logical USER requests per direction; extend a point with any CRC/HDR/retry/actual ACK-timeout/final-failure anomaly to 10 total per direction.
- Result: `INCONCLUSIVE`. All SF7 points completed, but the executor stopped during the SF8 configuration checkpoint before any SF8 USER traffic.
- This is the single automatic full-shard retry of the earlier executor-aborted RUN `RUN_20260926T213834Z_main-bw500-noatten-executor-abort`. No measurements from that failed RUN were reused.
- Executor workspace included infrastructure commit `74270ae276382581fb1ad90bcd7733a251a60414`; the prior failed RUN publication advanced the branch to `707bfc07ddeaddb1a778bc87ebe90df2e129e8b6` before this retry.
- SerialTerminal: `dreamworkerln/serialterminal@08c1b8d919cfb04c32068c9b9d63fdb1443139c9`.
- Firmware: unknown exact source provenance. Both `/version` responses reported Git base `b76ffa04ab47a3f344b8270159ab274256f6ff62` with `state=dirty`; image validation digest `5b197539057946356cb9b379aafaaaef9487b501452d5c50c6adc9abc6aeea88`, status `OK`, slot 0. These do not establish a clean exact firmware source SHA.

## Nodes and preflight

- Transport: BLE, fresh SerialTerminal PID 23593 for discovery, both opens, measurement, cleanup and close.
- Node A: `LoRa-Chatter-1B44`, address `44:1B:F6:8D:B7:A9`, session `s1`.
- Node B: `LoRa-Chatter-72E0`, address `E0:72:A1:D5:4C:15`, session `s2`.
- The pre-launch ownership check found no competing local SerialTerminal agent. The new process discovered and opened both targets before measurement.
- `/heartbeat off`, `/diag off`, `/echo-loop stop` and `/cancel all` were confirmed on both nodes. Initial `/cancel all` reported `pending=none queue_removed=0` on both.
- `/power 2` and `/freq 470` were applied and acknowledged on both. Post-application `/config` confirmed 2 dBm, 470 MHz, SF7, BW500 kHz, heartbeat OFF, retry ON with 5 attempts and diagnostic OFF.
- One unsequenced `RX HEADER ERROR` appeared on A during preflight at 00:45:26 +03:00, before the first measured USER at 00:47:47 +03:00. It is excluded from point results.

## Traversal and point results

Traversal followed SF ascending and payload ascending. Within each point, all A→B requests preceded B→A. Each request was submitted only after the prior logical USER settled with same-sender-session sequence, matching peer USER identity/payload and matching ACK. Cross-session evidence was correlated by identity and payload; response-array position was not used.

| SF | USER bytes | A→B requests / matching ACKs | B→A requests / matching ACKs | RF evidence | Class |
|---:|---:|---:|---:|---|---|
| 7 | 1 | 10 / 10 | 10 / 10 | One unsequenced B `RX CRC ERROR`, telemetry `len=136`; no retry or final failure | DEGRADED |
| 7 | 8 | 3 / 3 | 3 / 3 | No point-window CRC/HDR/retry/failure | CLEAN |
| 7 | 16 | 3 / 3 | 3 / 3 | No point-window CRC/HDR/retry/failure | CLEAN |
| 7 | 32 | 3 / 3 | 3 / 3 | No point-window CRC/HDR/retry/failure | CLEAN |
| 7 | 64 | 3 / 3 | 3 / 3 | No point-window CRC/HDR/retry/failure | CLEAN |
| 7 | 96 | 3 / 3 | 3 / 3 | No point-window CRC/HDR/retry/failure | CLEAN |
| 7 | 128 | 3 / 3 | 3 / 3 | No point-window CRC/HDR/retry/failure | CLEAN |
| 7 | 160 | 3 / 3 | 3 / 3 | No point-window CRC/HDR/retry/failure | CLEAN |
| 7 | 180 | 3 / 3 | 3 / 3 | No point-window CRC/HDR/retry/failure | CLEAN |
| 7 | 200 | 3 / 3 | 3 / 3 | No point-window CRC/HDR/retry/failure | CLEAN |
| 8–12 | 1, 8, 16, 32, 64, 96, 128, 160, 180, 200 | 0 / 0 | 0 / 0 | Not measured | UNMEASURED |

The SF7 / 1-byte CRC triggered the required extension to 10 logical deliveries in both directions. It had 20 matching ACK deliveries, all physical USER attempt 1/5. The CRC event is unsequenced and is attributed only to the active serialized point; no USER sequence is assigned to it. Across this RUN, 74 logical USER requests completed with matching ACKs, no physical retries, no final delivery failures, and no actual `DELIVERY ACK TIMEOUT` events. The configured `WAIT_ACK timeout=712ms` value is not an observed timeout.

All ten SF7 points are complete and locally classifiable. The other 50 requested SF/payload points (SF8–12) are unmeasured. No payload ceiling or conclusion for SF8–12 is claimed.

## Stop and recovery

After SF7 completion, the executor issued `/sf 8` on both nodes. Both returned `[SYS] SF 8 SAVED`. The orchestration checker incorrectly waited for a `/config`-style `CFG RADIO` line before issuing `/config`; it timed out that confirmation step and stopped. No SF8 measured USER was sent. During cleanup, `/config` on both nodes confirmed 2 dBm, 470 MHz, SF8, BW500 kHz, heartbeat OFF, retry ON with 5 attempts and diagnostic OFF.

This was an understood executor procedural failure. The earlier attempt had already used the one allowed automatic retry, so no further retry was started. `/cancel all` after the stop reported `pending=none queue_removed=0` on both nodes. Both BLE sessions were closed. The finalized log records PID 23593 stopping, and an OS-level check for that exact PID found no process.

The forensic and companion console logs were copied byte-for-byte from `/tmp/chatter-main-bw500-20260926T214232Z.log` and its `.console.log` companion. No explicit stdout/history replay was requested. No automatic collapsed completion transcript appeared.

## Evidence files

- `serialterminal.log`: exact finalized forensic log; authoritative for event timestamps/order.
- `serialterminal.console.log`: exact finalized companion console log.
