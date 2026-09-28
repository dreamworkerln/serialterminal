# SF7 PHY / payload sweep, 10 repetitions

Result: INCONCLUSIVE for RF quality; execution completed.

## Task and setup

Repeated the requested LoRa-Chatter measurement grid using one long-lived SerialTerminal agent process and the maintained `chatter.reliable_user` generic sweep API. The operator requested that anomaly analysis be omitted and the measured execution be published as recorded.

Before starting, both nodes reported the same `/config` baseline: 470 MHz (470000000 Hz), SF7, BW500 kHz, power 2 dBm. Both were connected over BLE and opened with `profile:"chatter"`:

- `s1`: LoRa-Chatter-1B44 (`44:1B:F6:8D:B7:A9`)
- `s2`: LoRa-Chatter-72E0 (`E0:72:A1:D5:4C:15`)
- Directions: `s1>s2` and `s2>s1`

SerialTerminal revision: `dreamworkerln/serialterminal@7cf0459c4e00a81592d447e0592e83a1142e18d9`. Firmware revision was not provided or established; no firmware source was inspected.

## Measured plan and execution

One deterministic main plan was started with:

- Constants: `sf=7`, `frequency_hz=470000000`, `power_dbm=2`
- BW axis: `125000, 250000, 500000`
- Payload axis: `1, 8, 16, 32, 64, 96, 128, 160, 180, 200` user bytes
- Direction axis: `s1>s2, s2>s1`
- Repetitions: exactly 10 per `BW × payload × direction`
- `sweep_id`: `sw1`
- API-reported total: 600 samples
- Terminal state: `completed`; progress `600/600`; terminal/head cursor 722

The full requested matrix ran: 3 bandwidths × 10 payload sizes × 2 directions. This report records the measured plan and mechanical completion only. Per operator instruction, RF/protocol anomaly evidence was not analyzed or classified. Therefore this run does not claim RF-quality PASS or FAIL; the RF-quality result is INCONCLUSIVE. No focused extension job was started.

No measured USER was sent through a manual per-sample `send_line` loop. The main job was executed and observed using `sweep_start` and `sweep_observe`, then closed with `sweep_close`.

## Final state and evidence

The sweep adapter performed its bounded cancellation cleanup. The sessions were closed and the exact SerialTerminal process was terminated; both logs were finalized.

- `serialterminal.log` — exact forensic log from the sole SerialTerminal process
- `serialterminal.console.log` — exact companion console log from that process
- Matching observation: `observations/OBS_20260928T005906Z_sf7-bw-payload-sweep-10x.md`
