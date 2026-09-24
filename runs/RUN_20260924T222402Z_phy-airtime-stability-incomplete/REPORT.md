# Two-node LoRa PHY / payload screening — INCONCLUSIVE

## Result and scope

**INCONCLUSIVE.** This run began a sparse bidirectional screen, but did not complete the requested matrix. Nine main-matrix PHY configurations were fully screened at the requested ten payload lengths; SF10/BW125 was cleanly measured only through 160 user bytes. At SF10/BW125 and 180 user bytes, two node USER transmissions overlapped. Subsequent samples at that PHY are contaminated and excluded. Configuration changes after that point returned `CFG BUSY`, so no further PHY series was started. Narrow-band screening, dense sweeps, controls, and PHY re-apply A/B were not performed.

The overlap was caused by an orchestration error in this run: completion polling accepted a delivery ACK without matching it to the current USER sequence. This allowed a new request to be queued while another was still in flight. The overlap is not evidence of a radio defect. The raw log is retained so the affected samples can be audited; they are not used for PHY reliability conclusions.

## Provenance

Participating BLE nodes:

| Role | Identity | SerialTerminal session |
|---|---|---|
| A | `LoRa-Chatter-1B44` | `s1` |
| B | `LoRa-Chatter-72E0` | `s2` |

Both `/version` responses reported firmware SHA `b76ffa04ab47a3f344b8270159ab274256f6ff62`, `state=clean`, environment `esp32-s3-n16r8`; both images reported validation SHA256 `c4e8407581882b7ca53680197748d4e8dabdf2cf9a389ad62bf271d6ef9307b6`, `status=OK`, `slot=0`. Build metadata reported toolchain SHA256 `cbb867e635dd96b27372354196469534b17a4276405a02a3ea1c58d8fc3f0d19`, PlatformIO `6.2.0`.

SerialTerminal runtime provenance: repository commit `04756c38a41dae8ebac063fed584a066187071b6`; worktree clean at capture. BLE was the only transport. A first agent process received `Operation not permitted` on discovery before opening hardware; after the required permission request, a single elevated long-lived agent process performed discovery, both opens, all hardware interaction, cleanup, and close. No firmware source was inspected and no firmware was flashed.

Initial and final `/config` on both nodes: power `2 dBm`, frequency `470 MHz`, SF12, BW62.5 kHz, heartbeat OFF, diagnostic OFF; retry ON, attempts 5. Coding rate, preamble, and CRC were not changed.

## Matrix coverage

`A→B` is session `s1` transmitting to `s2`; `B→A` is `s2` transmitting to `s1`. Payload was ASCII `Q` repeated to the requested user byte length. In the clean screen, all nine listed PHY configurations used lengths `1, 8, 16, 32, 64, 96, 128, 160, 180, 200` in both directions, with three initial requests per direction and length. Extra requests were added at anomaly points. Request counts below are exact log counts; every ACK count is matched by sender session and USER sequence.

| SF | BW (kHz) | USER requests A→B / B→A | Matched ACKs A→B / B→A | Physical USER TX A / B | Retry TX A / B | CRC observations |
|---:|---:|---:|---:|---:|---:|---|
| 7 | 125 | 30 / 30 | 30 / 30 | 30 / 30 | 0 / 0 | 0 |
| 7 | 250 | 44 / 44 | 44 / 44 | 48 / 44 | 4 / 0 | 4 at B, RF frames 28 B and 44 B |
| 7 | 500 | 30 / 30 | 30 / 30 | 30 / 30 | 0 / 0 | 0 |
| 8 | 125 | 30 / 30 | 30 / 30 | 30 / 30 | 0 / 0 | 0 |
| 8 | 250 | 30 / 30 | 30 / 30 | 30 / 30 | 0 / 0 | 0 |
| 8 | 500 | 30 / 30 | 30 / 30 | 30 / 30 | 0 / 0 | 0 |
| 9 | 125 | 30 / 30 | 30 / 30 | 30 / 30 | 0 / 0 | 0 |
| 9 | 250 | 44 / 44 | 44 / 44 | 47 / 45 | 3 / 1 | 1 at A, RF frame 172 B |
| 9 | 500 | 37 / 37 | 37 / 37 | 37 / 38 | 0 / 1 | 0 |
| 10 | 125 | 44 / 44 submitted | 38 / 42 observed | 57 / 55 | 18 / 13 | Contaminated from the 180 B payload point onward; exclude |

For SF7/BW250, the 16 B and 32 B payload points were each extended to ten requests in each direction. For SF9/BW250, the 160 B and 200 B points were extended to ten in each direction. SF9/BW500's 160 B point was extended to ten in each direction. These extension counts are reflected in the table.

SF10/BW125 had three requests in each direction at every length through 160 B, all with matching ACKs and no CRC/HDR observation in those lengths. Do not treat 180 B or 200 B as valid points. The first overlapping USER transmissions were both 180 B payloads (192 B RF frames), A retry seq661 and B seq662; the raw log estimates 679 ms overlap from TX completion timestamps and reported TX durations. The same exchange showed `DELIVERY QUEUED ... waiting=2/8 in_flight=1` and `RX CRC ERROR ... len=192`. Cancellation cleared A's current USER and three queued USERs with delivery status unknown.

The remaining eight main-matrix PHY combinations (SF10/BW250, SF10/BW500, SF11/BW125/250/500, SF12/BW125/250/500) were not measured: `/config` could not confirm the requested PHY after `CFG BUSY`. No narrow BW=62.5 screen was run; the initial/final SF12/BW62.5 setting is baseline state only.

## Directional anomalies and raw evidence

| PHY | Payload / RF frame | Direction | Receiver telemetry | Interpretation limit |
|---|---:|---|---|---|
| SF7/BW250 | 16 B / 28 B | A→B | B: two `RX CRC ERROR IRQ=0x70`, RSSI/SNR `-24/4`; sender emitted retry telemetry. Both directions were extended to ten requests; all logical USER sequences ultimately had matching ACKs. | Repeated CRC at this point merits controlled follow-up; this run did not do re-apply or airtime controls. |
| SF7/BW250 | 32 B / 44 B | A→B | B: two `RX CRC ERROR IRQ=0x70`, RSSI/SNR `-25/3`; sender emitted retry telemetry. Both directions were extended to ten requests; all logical USER sequences ultimately had matching ACKs. | Same limitation. |
| SF9/BW250 | 160 B / 172 B | B→A | A: one `RX CRC ERROR IRQ=0x70`, RSSI/SNR `-29/8`; delivery later ACKed after retry. | Intermittent point; no Stage 2 dense sweep or controlled follow-up. |
| SF10/BW125 | 180 B / 192 B | Both active | Simultaneous USER TX evidence, queue growth, and CRC errors on both receivers. | Invalid collision-compatible sample; excluded. |

Raw pointers are in `serialterminal.log`: SF7/BW250 CRC observations at lines 4530, 4821, 5360, and 5715 (each response contains the complete telemetry line and surrounding USER/ACK records); SF9/BW250 172 B CRC/retry at line 26904; first SF10/BW125 overlap TX records at lines 35556 and 35582, queue/CRC evidence at line 35683. These log lines include complete AGENT response objects. The companion console log contains human chat/system output; machine telemetry is in `serialterminal.log`.

## Airtime and boundary summary

| PHY | USER payload | RF frame | Direction | Observed USER TX duration |
|---|---:|---:|---|---|
| SF7/BW125 | 1 B | 13 B | A→B | 48–49 ms across three TX |
| SF7/BW125 | 1 B | 13 B | B→A | 48 ms across three TX |
| SF7/BW125 | 1 B ACK | 14 B | both | 48 ms in observed ACK TX |
| SF7/BW250 | 16 B | 28 B | A→B | 35 ms per reported attempt |
| SF10/BW125 | 180 B | 192 B | both | 1765 ms per reported USER attempt; overlapping point invalid |

No first-failure payload boundary was established. The CRC observations are intermittent and specific to the rows above; the SF10/BW125 180 B evidence is invalid for a radio-boundary conclusion because transmissions overlapped. A complete airtime min/average/max matrix was not produced; the exact per-attempt durations remain in the raw telemetry log.

## Required follow-up not performed

| Stage | Status |
|---|---|
| Main 18-PHY screen | Partial: nine combinations complete; SF10/BW125 valid only through 160 B; eight combinations unmeasured |
| BW62.5 safety progression SF7–SF12 | Not run |
| Dense 1–200 byte sweep | Not run |
| Same-payload/different-airtime controls | Not run |
| Similar-airtime/different-PHY controls | Not run |
| Direction reversal for anomalies | Present in sparse screen; SF7/BW250 repeated both directions, CRC observed only A→B |
| PHY_REAPPLY_AB | Not run |

No device-level packet-size limit, airtime threshold, or root cause is concluded. The observations support a repeatable CRC follow-up at SF7/BW250 for 16 B and 32 B USER payloads and an intermittent CRC follow-up at SF9/BW250/160 B. Results cannot distinguish payload length from airtime or node-specific receiver behavior without the planned controls.

## Cleanup

Both nodes reported `/cancel all`; A reported `DELIVERY CANCELLED: status unknown; queue cleared`. The nodes were restored to the original SF12/BW62.5 configuration and verified identical. Heartbeat and diagnostic mode were OFF, echo-loop stopped, power was 2 dBm, frequency 470 MHz. Both BLE sessions were closed and the SerialTerminal agent was terminated.
