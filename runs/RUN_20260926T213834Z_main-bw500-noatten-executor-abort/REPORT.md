# Hardware characterization report

## Task and scope

- Task class: `CANONICAL_RUN`
- Campaign: `MAIN MATRIX`
- Requested shard: 470 MHz, 2 dBm, BW500 kHz, SF7–12, USER payloads 1, 8, 16, 32, 64, 96, 128, 160, 180 and 200 bytes, both directions.
- Physical setup: attenuators NONE, supplied by the operator. Nodes, antennas and RF topology were not moved or changed.
- Requested normal depth: 3 logical USER requests per direction per point; extend any anomalous point to 10 total per direction.
- Result: `INCONCLUSIVE`. The executor stopped at SF7 / 1 byte, after the A→B block and before B→A or the required anomaly extension.
- Executor workspace HEAD: `74270ae276382581fb1ad90bcd7733a251a60414` (`hardware-skill: harden BLE ownership and executor retry`).
- SerialTerminal: `dreamworkerln/serialterminal@08c1b8d919cfb04c32068c9b9d63fdb1443139c9`.
- Firmware: unknown exact source provenance. Both `/version` responses reported Git base `b76ffa04ab47a3f344b8270159ab274256f6ff62` with `state=dirty`; the image validation digest was `5b197539057946356cb9b379aafaaaef9487b501452d5c50c6adc9abc6aeea88`, status `OK`, slot 0. The dirty base and image digest do not establish an exact firmware source SHA.

## Nodes and preflight

- Transport: BLE.
- Node A: `LoRa-Chatter-1B44`, address `44:1B:F6:8D:B7:A9`, session `s1`.
- Node B: `LoRa-Chatter-72E0`, address `E0:72:A1:D5:4C:15`, session `s2`.
- No pre-existing SerialTerminal agent process was present at the ownership gate. The fresh process discovered both nodes and opened both in that same process before measured traffic.
- `/heartbeat off`, `/diag off`, `/echo-loop stop` and `/cancel all` were issued/confirmed. Both cancel responses reported `pending=none queue_removed=0`. `/help` confirmed ordinary text input is a local USER transmission.
- Initial and final `/config` snapshots on both nodes reported power 2 dBm, frequency 470 MHz, SF7, BW500 kHz, heartbeat OFF, retry ON with 5 attempts, and diagnostic OFF. No PHY transition was needed before the first requested SF7 point.
- Startup telemetry showed historical aggregate error counters and one unsequenced CRC event on B before measured USER traffic; these are excluded from the measured point.

## Traversal and evidence

Requested traversal was SF ascending, payload ascending, complete A→B block then B→A block. The only point entered was SF7 / 1 byte:

| Direction | Logical requests | Matching ACKs | Sender physical USER attempts | Point status |
|---|---:|---:|---:|---|
| A→B | 3 | 3 | 3, all attempt 1/5 | INVALID / incomplete |
| B→A | 0 | 0 | 0 | UNMEASURED |

The three A→B USERs were the one-byte payload `A`, sender session `s1`, USER sequences 44, 45 and 46. For each, B (`s2`) logged a USER receive with the same peer session/sequence, presented `A`, and A logged the matching DELIVERY ACK. No retry or final delivery failure was observed. No actual `DELIVERY ACK TIMEOUT` event was observed; configured `WAIT_ACK timeout=712ms` output is not an observed timeout.

During this still-active point window the finalized forensic log records two unsequenced `RX HEADER ERROR` events and one unsequenced `RX CRC ERROR` on B (`len=14`), the CRC arriving after the matching ACK for USER sequence 46. These errors have no trustworthy USER sequence. The point therefore required extension to 10 total requests in both directions, but the executor stopped before beginning that extension. No conclusion about SF7 / 1 byte is claimed from this incomplete point.

All remaining payload points, directions and SF7–12 blocks are `UNMEASURED` in this attempt.

## Stop and recovery

The local orchestration code used an overly broad HDR detector and interpreted the periodic summary text `SESSION ... hdr=4` as a new HDR event. It raised an executor error while processing the SF7 / 1 byte A→B point and submitted no further measured USER. This was an executor-caused procedural error; the CRC/header events above are preserved as RF evidence and were not treated as the cause for a cleaner-statistics rerun.

After stopping, `/cancel all` again reported `pending=none queue_removed=0` on both nodes. Final `/config` reconfirmed the required settings. Both BLE sessions were closed. The log records SerialTerminal PID 22133 stopping; an OS-level check for that exact PID returned no process. The exact forensic and companion console logs were finalized and copied byte-for-byte from `/tmp/chatter-main-bw500-20260926T212713Z.log` and its `.console.log` companion.

No explicit stdout/history replay was requested. No automatic collapsed completion transcript appeared.

An automatic full-shard retry is permitted once for this understood executor-caused procedural failure. It must use a new RUN identity, fresh logs and a fresh SerialTerminal process, and restart BW500 from SF7 / 1 byte. No measurement from this attempt is to be spliced into that retry.

## Evidence files

- `serialterminal.log`: exact finalized forensic log; authoritative for event timestamps/order.
- `serialterminal.console.log`: exact finalized companion console log.
