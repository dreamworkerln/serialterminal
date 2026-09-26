# Hardware characterization report

## Result and scope

Result: **BLOCKED**. This is the requested new no-attenuator RF/topology campaign shard, MAIN MATRIX, BW 500 kHz. The requested matrix was SF 7, 8, 9, 10, 11, 12; USER payloads 1, 8, 16, 32, 64, 96, 128, 160, 180, 200 bytes; directions A->B and B->A. Normal depth was 3 settled logical requests per direction, with extension to 10+10 at an anomalous point.

No node identity or usable BLE target was established. The sole BLE discovery in the one SerialTerminal agent process returned an empty device list. The SerialTerminal machine API exposes `discover` but no capability scanner/prober request. The maintained Bluetooth instructions require that scan before concluding expected nodes are absent. Its documented scanner is an interactive terminal hotkey, incompatible with the required single JSONL agent process owning all hardware interaction. No second process was started, and no inference about node absence was made. Measurement therefore did not start.

Requested traversal was SF ascending 7 -> 8 -> 9 -> 10 -> 11 -> 12; payload ascending within each SF; complete A->B block before B->A. Actual traversal: one BLE discovery request only. No PHY transition or measured USER traffic occurred.

## Runtime and provenance

- SerialTerminal repository: `dreamworkerln/serialterminal`
- Exact SerialTerminal revision: `08c1b8d919cfb04c32068c9b9d63fdb1443139c9`
- Firmware: unknown; no physical node was opened and `/version` was not available.
- Transport requested/used: BLE; discovery only.
- Physical setup supplied by operator: no inline RF attenuators on either node; no physical distance, antenna orientation, or room topology supplied or established.
- `attenuators = NONE`
- A/B mapping: not established; `/id` was not obtained.

## Initial state and preflight

Node `/config` state is unknown. The required `/id`, `/version`, `/config`, heartbeat OFF, diagnostic OFF, echo-loop OFF, no-pending-reliable-work, retry ON with actual attempts, and target power/frequency/BW/SF confirmations could not be established. No commands were sent to either node. Requested power was 2 dBm on both nodes; frequency 470 MHz; BW 500 kHz; SF 7 through 12. No RF configuration was changed.

## Point results and counts

Every requested point is **UNMEASURED**: all six SF values × all ten payload sizes × both directions = 120 SF/payload/direction entries (60 bidirectional points / 120 directional cells). No point was extended because no measurement anomaly was observed; the scan limitation is an executor/API boundary, not an RF anomaly.

| Measure | Count |
|---|---:|
| Requested logical USER requests | 2,160 minimum |
| Logical requests attempted / matching deliveries | 0 / 0 |
| Physical USER attempts / retries | 0 / 0 |
| Actual ACK timeouts / final delivery failures | 0 / 0 |
| CRC / HDR events | 0 / 0 |
| CLEAN / DEGRADED / FAILED / INVALID / UNMEASURED directional cells | 0 / 0 / 0 / 0 / 120 |
| Anomaly extensions | 0 |

The zero anomaly counts mean no measured RF window existed; they do not establish clean RF behavior. RSSI/SNR ranges: none. USER-path, ACK-path, consecutive retry/error, clustering, and directional-asymmetry analyses: not measurable. No monotonic payload ceiling is inferred.

## Logs, limitations, and final state

The raw finalized SerialTerminal log is authoritative for this attempt. It records agent ready, the single `discover` request (`scope=ble`) returning `devices: []`, and agent stop. The exact companion console log produced by the process is empty. Executor limitation: before launch, the forensic `.log` path was checked for nonexistence, but the companion was mistakenly checked using `<log>.log.console.log`; runtime naming replaces `.log` with `.console.log`. Its prelaunch state is therefore unverified. The files copied here are the exact files present after process termination; no log was edited or synthesized.

No sessions were opened, so there were no sessions to close. No measured reliable work was submitted. Node heartbeat, diagnostic, echo-loop, power, frequency and PHY state remain unverified and unchanged by this attempt. Process terminated after discovery. This run is not directly equivalent to the historical BW500 attenuated run, and does not merge or rewrite historical evidence.

Evidence pointers: `serialterminal.log`, `serialterminal.console.log`. No OBS-independent RF conclusion is supported; the matching OBS records the reusable scanner/API execution boundary.
