# Production BLE smoke

Observed: 2026-09-18T09:15:33Z
Result: INCONCLUSIVE

## Task and provenance

- Executed the requested two-node production smoke with one long-lived SerialTerminal agent process.
- Operator-stated firmware checkpoint was not independently verified; firmware provenance is therefore `unknown`.
- SerialTerminal source revision: `dreamworkerln/serialterminal@4f562062afd64750679a4d5562a29a022025a967`.

## Hardware/session mapping

- Node A: `LoRa-Chatter-1B44`; USB session `s2`; BLE session `s3`.
- Node B: `LoRa-Chatter-72E0`; USB session `s1`; BLE session `s4`.
- All four sessions used explicit `profile: chatter`.
- Host Bluetooth audio preflight was CLEAR: paired `WH-1000XM5` was `Connected: no`; PipeWire/PulseAudio exposed no BlueZ audio endpoint.

## Measured rounds

- Exactly three measured rounds were executed, once each.
- Each round sent `/help` by BLE to Node A and immediately by BLE to Node B; no USB `/help` was sent.
- Node A: `COMPLETE 3/3`.
- Node B: `COMPLETE 3/3`.
- `observe.result.lines` contained the coherent logical help output, including all requested anchors and the `BLE CLIENT: machine telemetry 0004 subscribed in background` final line.
- USB SYSTEM output remained visible, and BLE human SYSTEM output remained on the `chat`/0003 path.

## Production and routing checks

- `[BLE-TX-DIAG]`: absent from the exact forensic log.
- 0003 human SYSTEM routing: PASS; SYSTEM help/output lines were observed on USB and BLE `chat` streams.
- 0004 machine telemetry routing: PASS; BLE sessions exposed independent `telemetry` stream lines and help confirmed the background 0004 subscription; SYSTEM lines remained on the human path.
- No `cursor_expired`, `send-outcome-unknown`, or `forensic_gap` evidence was found.

## Anomaly and verdict limitation

- Before measured round 1, BLE session `s3` (`LoRa-Chatter-1B44`) emitted a disconnect followed by reconnect. It was not repeated during the three measured rounds, but it is an unexpected reconnect in the run evidence.
- Because the requested PASS criteria exclude unexpected disconnect/reconnect, the overall result is `INCONCLUSIVE`, not PASS. This evidence does not establish firmware-side root cause.

## Final state and artifacts

- All four sessions were closed and the SerialTerminal agent process exited cleanly.
- Nodes were left in CHAT with echo OFF and no intentionally pending reliable USER flow.
- Exact forensic and companion console logs are stored beside this report.
