# SF7 PHY / payload sweep

Result: PASS

## Task and setup

Executed the requested LoRa-Chatter sweep on two connected BLE nodes using one long-lived SerialTerminal agent process. The maintained `chatter.reliable_user` generic sweep API performed the measured work. No measured USER was sent by a manual per-sample `send_line` loop.

Before the sweep, `/config` on both nodes reported the same baseline: frequency 470 MHz (470000000 Hz), SF7, BW500 kHz, power 2 dBm. Both sessions were opened with `profile:"chatter"`:

- `s1`: LoRa-Chatter-1B44 (`44:1B:F6:8D:B7:A9`)
- `s2`: LoRa-Chatter-72E0 (`E0:72:A1:D5:4C:15`)
- `s1>s2`: 1B44 to 72E0; `s2>s1`: 72E0 to 1B44

SerialTerminal revision: `dreamworkerln/serialterminal@7cf0459c4e00a81592d447e0592e83a1142e18d9`. Firmware revision was not provided or established; no firmware source was inspected.

## Execution

Main deterministic plan:

- Constants: `sf=7`, `frequency_hz=470000000`, `power_dbm=2`
- BW axis: `125000, 250000, 500000`
- Payload axis: `1, 8, 16, 32, 64, 96, 128, 160, 180, 200` user bytes
- Direction axis: `s1>s2, s2>s1`
- Repetitions: exactly 3 per `BW × payload × direction`
- Main `sweep_id`: `sw1`; API returned `total_samples=180`
- Main terminal state: `completed`, `completed_samples=180/180`; terminal event sequence 302
- Cursor was advanced using returned `sweep_observe` cursors (initial cursor 0; terminal head/cursor 302). The retained job was closed with `sweep_close`.

The job completed all 30 BW/payload pairs in both directions. Its axis grid and repetitions were not modified after start.

## RF / protocol evidence

The finalized forensic log was reviewed for ACK timeout, retry, CRC and header-error evidence. `sample_completed` was treated as mechanical job progress, not an RF PASS.

Two measurement points contained a delivery timeout/retry and were extended under separate focused jobs. Both additional jobs completed 14/14 samples with no further ACK timeout, retry, CRC or header-error evidence in their windows:

| Point | Main-job evidence | Focused extension | Final logical requests |
|---|---|---|---|
| SF7 / BW125 kHz / 200 B | `s2>s1`: one DELIVERY ACK timeout followed by a retry; sample settled | `sw2`, 7 repetitions per direction, completed | 10 each direction |
| SF7 / BW250 kHz / 180 B | `s1>s2`: RX CRC error telemetry and one DELIVERY ACK timeout followed by a retry; sample settled | `sw2`, 7 repetitions per direction, completed | 10 each direction |
| SF7 / BW500 kHz / 1 B | RX HEADER ERROR telemetry at the point transition, on both directional windows; header telemetry has no trusted USER sequence | `sw3`, 7 repetitions per direction, completed | 10 each direction |

`sw2` plan constants were `sf=7`, `frequency_hz=470000000`, `power_dbm=2`, `bandwidth_hz=250000`, `payload_bytes=180`, with direction axis `s1>s2, s2>s1` and 7 repetitions; terminal state `completed`, 14/14. `sw3` used the same plan shape for BW500 kHz and payload 1 B; terminal state `completed`, 14/14. Both jobs were closed with `sweep_close`.

The timeout/retry points are degraded-but-delivered evidence, not clean points. CRC/header records are preserved as contextual RF evidence and are not assigned a protocol USER sequence. No final delivery failure or contaminated/overlapping measured USER transaction was found. All other requested main-grid points had no observed retry, CRC or header-error event in their measurement windows. No separate PHY re-apply control was performed.

## Final state and limitations

After extension, both nodes reported the original baseline configuration: 470 MHz, SF7, BW500 kHz, 2 dBm; heartbeat OFF and diagnostic mode OFF. The sweep adapter performed bounded cancellation cleanup. Both sessions were closed and the exact SerialTerminal process PID was confirmed gone; the forensic and companion console logs were finalized.

An RX HEADER ERROR was also logged after the main job's terminal event, outside its measurement window. It was not attributed to a sweep point. The executor cannot identify unrelated third-party RF from the available firmware telemetry.

## Evidence files

- `serialterminal.log` — exact forensic log from the sole SerialTerminal process
- `serialterminal.console.log` — exact companion console log from that process
- Matching observation: `observations/OBS_20260928T003520Z_sf7-bw-payload-sweep.md`
