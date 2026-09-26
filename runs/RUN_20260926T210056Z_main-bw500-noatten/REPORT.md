# Hardware characterization report

## Task and scope

- Task class: `CANONICAL_RUN`
- Campaign: `MAIN MATRIX`, new no-attenuator RF/topology campaign
- Requested shard: 470 MHz, TX power 2 dBm on both nodes, BW 500 kHz, SF 7–12, USER payloads 1, 8, 16, 32, 64, 96, 128, 160, 180 and 200 bytes, both directions
- Requested normal depth: 3 logical USER requests per direction per point; extend an anomalous point to 10 per direction
- Outcome: `INCONCLUSIVE`. Only SF7 payloads 1, 8 and part of 16 bytes were submitted. SF7/8 lost exact sender/receiver evidence consistency; later traffic continued without the required clean-state recovery. No RF conclusions are drawn from those affected samples.
- SerialTerminal: `dreamworkerln/serialterminal@08c1b8d919cfb04c32068c9b9d63fdb1443139c9`
- Firmware: unknown exact source provenance. Both `/version` results reported base Git `b76ffa04ab47a3f344b8270159ab274256f6ff62` with `state=dirty`; policy does not accept that as the deployed source SHA. Both reported image validation SHA `5b197539057946356cb9b379aafaaaef9487b501452d5c50c6adc9abc6aeea88`, `status=OK`, slot 0. This image digest is not firmware source provenance.

## Node identity and physical setup

- Transport: BLE, one SerialTerminal agent process for discovery, both opens, preflight, measurements, cleanup and closes.
- Node A: `LoRa-Chatter-1B44`, device address `44:1B:F6:8D:B7:A9`, SerialTerminal session `s1`.
- Node B: `LoRa-Chatter-72E0`, device address `E0:72:A1:D5:4C:15`, SerialTerminal session `s2`.
- Physical RF setup supplied by operator: `attenuators = NONE` (no inline RF attenuators on either node).
- No distance, antenna orientation or room topology was supplied or established. Nodes/antennas/topology were not intentionally changed.
- This run is not directly equivalent to the historical BW500 attenuated run; historical evidence is untouched.

## Preflight and initial state

Both nodes were discovered and identified using `/id`; both `/version` and `/config` were queried before measurement. Initial `/config` on A and B reported 2 dBm, 470 MHz, SF12, BW500 kHz, heartbeat OFF, retry ON with 5 configured attempts, and diagnostic OFF. Echo loop was explicitly stopped on each node. `/cancel all` reported `pending=none queue_removed=0` on each node before measurement. `/power 2` and `/freq 470` were explicitly applied and acknowledged on both nodes.

Before the first measurement, A was set to SF7 and confirmed; then B was set to SF7 and confirmed. Both `/config` results then showed matching 2 dBm, 470 MHz, SF7, BW500 kHz, heartbeat OFF, retry ON with 5 attempts, and diagnostic OFF. One unsequenced `RX CRC ERROR ... len=179` was observed on A during preflight/configuration, before measured USER traffic; it is setup-context evidence and is excluded from point counts.

Executor deviation: the unique timestamped log path was used, but the required existence check for the `.log` and companion `.console.log` was omitted before process launch. The files were observed after launch. This pre-launch condition cannot be verified retrospectively and is recorded as an evidence limitation.

## Traversal and per-point results

Requested order was SF ascending 7→12, payload ascending 1→200, complete A→B block then B→A block. Actual traversal stopped in SF7 after payload 16 bytes. No SF8–12 configuration block was entered. Deterministic ASCII payloads were used: one-byte payloads were `A`/`B`; longer payloads began with compact SF/direction/size/request markers and were padded with `X` to the exact requested byte count.

| SF | USER bytes | A→B submitted / matched ACK / sender TX | B→A submitted / matched ACK / sender TX | CRC / HDR in point window | Class |
|---:|---:|---:|---:|---:|---|
| 7 | 1 | 10 / 10 / 10 | 10 / 10 / 10 | 1 / 3 | DEGRADED |
| 7 | 8 | 10 / 10 / 10 | 10 / 9 / 9 | 1 / 2 | INVALID |
| 7 | 16 | 3 / 3 / 3 | 1 / 1 / 1 | 0 / 0 | INVALID |
| 7 | 32, 64, 96, 128, 160, 180, 200 | 0 / 0 / 0 each | 0 / 0 / 0 each | 0 / 0 | UNMEASURED |
| 8, 9, 10, 11, 12 | 1, 8, 16, 32, 64, 96, 128, 160, 180, 200 | 0 / 0 / 0 each | 0 / 0 / 0 each | 0 / 0 | UNMEASURED |

There are 60 SF/payload points in the requested shard: 0 CLEAN, 1 DEGRADED, 0 FAILED, 2 INVALID and 57 UNMEASURED. The SF7/1-byte point completed its 10+10 anomaly extension and all 20 logical deliveries had a matching ACK on the first physical attempt. It is DEGRADED because three unsequenced header errors and one unsequenced CRC error occurred in its serialized measurement window.

The SF7/8-byte point completed the 10+10 request count after anomalies during the initial 3+3 sample. Sender telemetry contains 10 A→B USER transmissions and 9 B→A transmissions with corresponding matching DELIVERY ACKs; receiver telemetry contains 10 USER receptions in each direction. The extra receiver USER has no exact matching sender TX/ACK evidence in the log. Its association is ambiguous. The point is INVALID. The SF7/16-byte point has only 3 A→B and 1 B→A submissions; although each has TX/RX/ACK evidence, it followed the unresolved SF7/8 correlation discrepancy without the required clean-state and PHY re-confirmation. It is INVALID and not an RF conclusion.

## Counts and anomaly analysis

- Logical USER requests submitted: 44 total (SF7/1B: 20; SF7/8B: 20; SF7/16B: 4).
- Matching DELIVERY ACKs: 43, each for the logged sender session and USER sequence.
- Sender `TX USER` physical-attempt telemetry: 43; every observed TX line reports attempt `1/5`.
- Receiver `RX USER` telemetry: 44; the one extra receive belongs to the SF7/8B correlation discrepancy above.
- Retries: 0 observed. Actual `DELIVERY ACK TIMEOUT` events: 0. `DELIVERY WAIT_ACK ... timeout=712ms` is configuration/state output, not an observed timeout.
- Final reliable delivery failures: 0.
- Measured-window CRC: 2 (one SF7/1B, one SF7/8B). Measured-window HDR: 5 (three SF7/1B, two SF7/8B). Separate preflight CRC: 1 on A, RF frame length 179 bytes, before measurement.
- The CRC/HDR telemetry has no trusted USER sequence. Events are attributed only to the active serialized point window; no exact USER sequence is assigned to them.
- Maximum consecutive logical transactions requiring retry: 0.
- Maximum consecutive recorded receive-error telemetry events without an intervening logged valid USER reception: 2. These are unsequenced CRC/HDR indications; this does not establish two specific failed USER transmissions.
- Error events were intermittent across the two measured payload windows. The 8-byte directional receive/transmit mismatch makes the apparent directional difference ambiguous; no defective node TX/RX claim is supported.
- RSSI/SNR on SF7/1B valid RX USER frames: A→B RSSI −43…−38 dBm, SNR −0…6; B→A RSSI −43…−35 dBm, SNR −1…6. Across all received measured USER telemetry, including invalid points, RSSI was −64…−35 dBm and SNR −1…6; the invalid-point values are contextual only.
- No monotonic payload ceiling is inferred. No ACK-path versus USER-path loss class is supported for the SF7/8B mismatch; it remains ambiguous because the exact sender transmission identity is absent for one valid receiver USER record.

## Contamination, limitations and final state

The task-local observation loop failed to associate some receiver lines when the receiver evidence appeared earlier in a combined observation response than the sender identity line. It reported an incomplete point summary; I stopped new measurement submission and cancelled both nodes. The finalized raw log shows that more already-submitted requests continued to be processed before cancellation. Since the SF7/8B sender/receiver counts disagree and no clean-state re-establishment occurred before SF7/16B, the 8B and subsequent 16B points are invalid. All later requested points are unmeasured. This is an executor/evidence limitation, not evidence of a firmware defect.

After stopping, `/cancel all` on both nodes reported `pending=none queue_removed=0`. Final `/config` on both nodes confirmed 2 dBm, 470 MHz, SF7, BW500 kHz, heartbeat OFF, retry ON with 5 attempts, diagnostic OFF; echo loop had been confirmed stopped. Both sessions were closed and the agent process was terminated so its logs were finalized.

No physical distance, antenna orientation or room topology is claimed. No attenuator, antenna, node placement, reboot, flash, PHY away-and-back workaround or corrective configuration experiment was performed.

## Evidence pointers

- `serialterminal.log` is the exact finalized forensic log from the one SerialTerminal process and is authoritative for event ordering.
- `serialterminal.console.log` is the exact finalized companion console log.
- Run identity: `20260926T210056Z_main-bw500-noatten`.
- Matching observation records the reusable factual SF7/1B result and the same evidence limitation.
