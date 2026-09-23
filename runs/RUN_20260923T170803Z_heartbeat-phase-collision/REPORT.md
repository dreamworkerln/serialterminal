# TODO_008 heartbeat phase collision

Observed: 2026-09-23T17:08:03Z
Task: CANONICAL_RUN physical investigation on two LoRa-Chatter nodes.
Result: INCONCLUSIVE

## Provenance and setup

- SerialTerminal runtime: `dreamworkerln/serialterminal@0db99efb5155ca0068d6dd3ecf6ed0f272537a10`, branch `dev`.
- Observation workspace: `node_observations@0a7092d7d873e839635c734d0dc09e57acfa5f5e`.
- Both nodes reported firmware `8b62d6c4d50577da6a8927e52f123645d63f24a5`, `state=clean`.
- Both nodes reported image validation SHA `e4496cf74cd55ff0b06b9a3f82c613d6c64173b6f7ff12db0c954aee2ec46162`, `status=OK`, `slot=0`.
- `s1`: `LoRa-Chatter-1B44`; `s2`: `LoRa-Chatter-72E0`.
- Both sessions used BLE and `profile:"chatter"` in one long-lived process.
- The expected firmware source path was not mounted in this environment; timing is therefore checked against the measured firmware telemetry ToA and the SF12/BW125 LoRa airtime derivation.

## Measured interval

The independent `/heartbeat on` sends were timestamped by the host at `20:10:22.936` and `20:10:22.937 +03:00`. `/heartbeat off` was sent at `20:12:48.794` and `20:12:48.796 +03:00`: 145.858 s from the first on request to the first off request. The first measured PING starts were `20:10:34.160719` (`s2`) and `20:10:34.252216` (`s1`); the last PING before cleanup was `20:12:44.317593` (`s2`). The PING-start observation span was 130.157 s.

Safety state before measurement and after cleanup was `power=2 dBm`, `freq=470 MHz`, `SF12`, `BW125`, heartbeat OFF, diagnostic mode OFF, echo-loop stopped, and no pending delivery.

## Local heartbeat counts

| session | local PING | matching PONG | NRP | CRC | HDR |
|---|---:|---:|---:|---:|---:|
| s1 | 12 | 1 | 11 | 0 | 0 |
| s2 | 13 | 2 | 11 | 0 | 0 |

There were also three PONG transmissions by `s1` in response to peer PINGs and one by `s2`; these are separate from each node's local PING outcome count.

## Paired PING evidence

Pairs below use the nearest same-request local PING starts where both nodes emitted that request identity. All paired outcomes shown are NRP on both nodes. `next delta` is the next paired local-PING delta after that paired NRP, when another paired request was observed.

| request | s1 PING start (+03:00) | s2 PING start (+03:00) | delta_ms | s1 outcome | s2 outcome | next delta_ms |
|---:|---|---|---:|---|---|---:|
| 23 | 20:10:34.252216 | 20:10:34.160719 | 91.496 | NRP | NRP | 92.649 |
| 24 | 20:10:44.245199 | 20:10:44.152550 | 92.649 | NRP | NRP | 2.241 |
| 26 | 20:11:04.091082 | 20:11:04.088840 | 2.241 | NRP | NRP | 41.884 |
| 27 | 20:11:14.038390 | 20:11:14.080274 | 41.884 | NRP | NRP | 47.667 |
| 28 | 20:11:24.209144 | 20:11:24.161477 | 47.667 | NRP | NRP | 45.477 |
| 29 | 20:11:34.109205 | 20:11:34.063728 | 45.477 | NRP | NRP | 132.772 |
| 30 | 20:11:44.056561 | 20:11:44.189333 | 132.772 | NRP | NRP | 86.442 |
| 31 | 20:11:54.183713 | 20:11:54.270155 | 86.442 | NRP | NRP | 86.695 |
| 32 | 20:12:04.174675 | 20:12:04.261370 | 86.695 | NRP | NRP | 46.734 |
| 34 | 20:12:24.336080 | 20:12:24.289346 | 46.734 | NRP | NRP | 92.359 |
| 35 | 20:12:34.463205 | 20:12:34.370846 | 92.359 | NRP | NRP | — |

The missing same-request pairs are themselves evidence of recovery/decorrelation: `s2` PING 25 at `20:10:54.142680` was received by `s1`, which sent PONG and received the matching PONG outcome; later `s1` PING 33 at `20:12:14.210321` was received by `s2`, which sent PONG and `s1` received it. `s2` PING 36 at `20:12:44.317593` likewise received a PONG from `s1`. These successful peer exchanges interrupt the same-sequence paired-NRP pattern.

## Timing comparison

- Symbol time: `2^12 / 125000 = 32.768 ms`.
- Configured contention window: `8 symbols = 262.144 ms`.
- PING: measured telemetry `1156 ms`; LoRa derivation for 12-byte SF12/BW125 payload is approximately `1155.072 ms`.
- PONG: measured telemetry `1320 ms`; LoRa derivation for 16-byte SF12/BW125 payload is approximately `1318.912 ms`.
- Reported heartbeat response deadline: `<=2019 ms`.

Every paired delta in the table is below the 1156 ms PING airtime, so those starts are compatible with physical overlap; every paired delta is also below the 262.144 ms contention window. However, the sequence is not an uninterrupted phase re-lock: successful peer PING/PONG exchanges at requests 25, 33 and 36 produce scheduling separation, and the next paired delta after request 29 is 132.772 ms after the preceding paired-NRP chain. Courtesy telemetry was present around the cycles, but reported `yielding=0` and `expired=0`; no measured courtesy release/expiry explains the observed recovery.

## Verdict

INCONCLUSIVE for the specific root-cause claim. The evidence supports repeated near-simultaneous PINGs, physically overlapping airtime-compatible starts, and repeated paired NRP. It does not prove the required persistent chain “paired loss -> insufficient next phase separation -> recurrent overlap” because the system also self-decorrelates through successful peer PING/PONG receptions. The observed behavior is consistent with a recurrent collision-prone phase relationship, but phase re-lock as the root cause is not proven by this run.

## Final state and recording

Both nodes were returned to the safe final state and both sessions were closed. The forensic log is the raw authority; the companion console log is retained separately. No explicit stdout/history replay or post-close transcript fetch was requested. The terminal UI did not produce an automatic collapsed completion transcript after close.

Run bundle: `runs/RUN_20260923T170803Z_heartbeat-phase-collision/`
