# CANONICAL RUN — MAIN MATRIX / BW500

**Outcome: PASS**

## Scope and orchestration

- MAIN MATRIX shard; BW=500 kHz; SF traversal 7→8→9→10→11→12; payload order 1, 8, 16, 32, 64, 96, 128, 160, 180, 200 bytes.
- Nodes: A=LoRa-Chatter-1B44; B=LoRa-Chatter-72E0. Controller transport BLE. Frequency=470 MHz and TX power=2 dBm on both. Heartbeat OFF, diagnostic OFF, echo-loop stopped; coding/sync defaults unchanged.
- One long-lived interactive SerialTerminal agent process. Each measured USER was submitted alone; sender session/sequence was read from telemetry, receiver USER evidence was observed, and only the exact matching DELIVERY ACK with queue=0 (or bounded terminal result) allowed the next USER. Opposite direction began only after settlement.
- Deterministic single-byte ASCII USER payloads. At lengths ≥8 the marker identifies SF/direction/size/request and deterministic `.` padding fills the exact length; one-byte payloads use deterministic printable ASCII because one byte cannot contain the full marker.
- Normal depth was 3 A→B then 3 B→A. Real anomaly points were extended to 10+10. Actual request counts are listed below.

## Overall results

- Coverage: 60/60 points; CLEAN=54, DEGRADED=6, FAILED=0, INVALID=0, UNMEASURED=0.
- Logical USER requests=478; matching-ACK deliveries=478; physical USER attempts=485; retries=7; ACK timeouts=7; final delivery failures=0; CRC=5; HDR=0.
- No cross-node USER overlap, correlation loss, mismatched PHY, queue anomaly or forensic gap was observed. No point was contaminated or invalidated; all points have at least three settled requests in each direction.

## Exact configuration

Initial `/config` on both nodes:

```text
CFG schema=2 storage=NVS freq_oob=OFF
CFG RADIO power=2 dBm freq=470 MHz sf=12 bw=62.5 kHz
CFG LINK heartbeat=OFF retry=ON attempts=5 diag=OFF
```

Startup `/echo-loop stop` reported already stopped. Before SF7 both nodes were set to SF7/BW500 and verified. Before each following SF, `/sf` was applied to A then B and `/config` verified both at the same target SF/BW500, power=2 dBm, frequency=470 MHz. No reboot, PHY away-and-back, or corrective BW reapply experiment occurred.

Final `/config` on both nodes:

```text
CFG schema=2 storage=NVS freq_oob=OFF
CFG RADIO power=2 dBm freq=470 MHz sf=12 bw=500 kHz
CFG LINK heartbeat=OFF retry=ON attempts=5 diag=OFF
```

Final cleanup: `/cancel all` returned `pending=none queue_removed=0` on both nodes; heartbeat OFF, diag already OFF, echo-loop already stopped; `/power 2` and `/freq 470` saved. Both BLE sessions were closed and agent stdin was closed to terminate process ownership. No post-close transcript replay was requested.

## Per-point results

Directional cells are `logical/matching ACK; physical attempts/retries; ACK timeouts/final failures`. RSSI/SNR ranges cover observed receiver USER frames and received matching ACK frames; `n` is observed RF-frame count.

| SF | Payload B | Class | A→B L/ACK; phys/retry; TO/fail | A→B USER RX RSSI/SNR | A→B ACK RX RSSI/SNR | B→A L/ACK; phys/retry; TO/fail | B→A USER RX RSSI/SNR | B→A ACK RX RSSI/SNR | CRC/HDR |
|---:|---:|---|---|---|---|---|---|---|---:|
| 7 | 1 | DEGRADED | 10/10; 10/0; 0/0 | -75..-72 dBm / 6..6 dB (n=10) | -76..-73 dBm / 6..6 dB (n=10) | 10/10; 10/0; 0/0 | -76..-73 dBm / 5..6 dB (n=10) | -74..-73 dBm / 5..6 dB (n=10) | 1/0 |
| 7 | 8 | CLEAN | 10/10; 10/0; 0/0 | -76..-74 dBm / 5..6 dB (n=10) | -78..-76 dBm / 6..6 dB (n=10) | 10/10; 10/0; 0/0 | -76..-73 dBm / 5..6 dB (n=10) | -74..-73 dBm / 5..6 dB (n=10) | 0/0 |
| 7 | 16 | CLEAN | 10/10; 10/0; 0/0 | -73..-72 dBm / 6..6 dB (n=10) | -75..-74 dBm / 5..6 dB (n=10) | 10/10; 10/0; 0/0 | -74..-73 dBm / 6..6 dB (n=10) | -74..-73 dBm / 5..6 dB (n=10) | 0/0 |
| 7 | 32 | CLEAN | 9/9; 9/0; 0/0 | -73..-72 dBm / 6..6 dB (n=9) | -75..-74 dBm / 6..7 dB (n=9) | 3/3; 3/0; 0/0 | -73..-72 dBm / 6..6 dB (n=3) | -73..-73 dBm / 6..6 dB (n=3) | 0/0 |
| 7 | 64 | DEGRADED | 10/10; 10/0; 0/0 | -73..-71 dBm / 6..6 dB (n=10) | -73..-72 dBm / 6..7 dB (n=10) | 10/10; 10/0; 0/0 | -73..-72 dBm / 5..6 dB (n=10) | -73..-72 dBm / 6..6 dB (n=10) | 1/0 |
| 7 | 96 | CLEAN | 3/3; 3/0; 0/0 | -72..-71 dBm / 6..6 dB (n=3) | -74..-73 dBm / 6..6 dB (n=3) | 3/3; 3/0; 0/0 | -73..-72 dBm / 6..6 dB (n=3) | -73..-72 dBm / 6..6 dB (n=3) | 0/0 |
| 7 | 128 | CLEAN | 3/3; 3/0; 0/0 | -72..-72 dBm / 6..6 dB (n=3) | -73..-72 dBm / 6..6 dB (n=3) | 3/3; 3/0; 0/0 | -73..-71 dBm / 6..6 dB (n=3) | -73..-72 dBm / 6..6 dB (n=3) | 0/0 |
| 7 | 160 | CLEAN | 3/3; 3/0; 0/0 | -73..-72 dBm / 6..6 dB (n=3) | -74..-73 dBm / 6..6 dB (n=3) | 3/3; 3/0; 0/0 | -73..-73 dBm / 6..6 dB (n=3) | -74..-73 dBm / 6..6 dB (n=3) | 0/0 |
| 7 | 180 | CLEAN | 3/3; 3/0; 0/0 | -72..-72 dBm / 6..6 dB (n=3) | -74..-74 dBm / 6..6 dB (n=3) | 3/3; 3/0; 0/0 | -73..-72 dBm / 6..6 dB (n=3) | -73..-73 dBm / 6..6 dB (n=3) | 0/0 |
| 7 | 200 | CLEAN | 3/3; 3/0; 0/0 | -73..-72 dBm / 6..6 dB (n=3) | -74..-73 dBm / 6..6 dB (n=3) | 3/3; 3/0; 0/0 | -74..-73 dBm / 6..6 dB (n=3) | -73..-73 dBm / 5..6 dB (n=3) | 0/0 |
| 8 | 1 | CLEAN | 3/3; 3/0; 0/0 | -77..-76 dBm / 7..8 dB (n=3) | -76..-75 dBm / 7..8 dB (n=3) | 3/3; 3/0; 0/0 | -77..-77 dBm / 7..8 dB (n=3) | -77..-76 dBm / 7..8 dB (n=3) | 0/0 |
| 8 | 8 | CLEAN | 3/3; 3/0; 0/0 | -76..-75 dBm / 7..8 dB (n=3) | -77..-76 dBm / 7..7 dB (n=3) | 3/3; 3/0; 0/0 | -77..-76 dBm / 7..7 dB (n=3) | -77..-77 dBm / 8..8 dB (n=3) | 0/0 |
| 8 | 16 | CLEAN | 3/3; 3/0; 0/0 | -76..-75 dBm / 7..8 dB (n=3) | -77..-77 dBm / 7..7 dB (n=3) | 3/3; 3/0; 0/0 | -76..-75 dBm / 7..8 dB (n=3) | -77..-77 dBm / 7..8 dB (n=3) | 0/0 |
| 8 | 32 | CLEAN | 3/3; 3/0; 0/0 | -75..-74 dBm / 7..8 dB (n=3) | -78..-77 dBm / 7..8 dB (n=3) | 3/3; 3/0; 0/0 | -77..-75 dBm / 7..7 dB (n=3) | -78..-77 dBm / 7..8 dB (n=3) | 0/0 |
| 8 | 64 | DEGRADED | 10/10; 11/1; 1/0 | -76..-74 dBm / 7..8 dB (n=10) | -78..-77 dBm / 6..7 dB (n=10) | 10/10; 10/0; 0/0 | -77..-76 dBm / 6..7 dB (n=10) | -78..-78 dBm / 7..8 dB (n=10) | 1/0 |
| 8 | 96 | CLEAN | 3/3; 3/0; 0/0 | -75..-74 dBm / 7..8 dB (n=3) | -78..-77 dBm / 6..7 dB (n=3) | 3/3; 3/0; 0/0 | -76..-75 dBm / 8..8 dB (n=3) | -77..-76 dBm / 8..8 dB (n=3) | 0/0 |
| 8 | 128 | CLEAN | 3/3; 3/0; 0/0 | -75..-75 dBm / 7..7 dB (n=3) | -77..-77 dBm / 7..8 dB (n=3) | 3/3; 3/0; 0/0 | -76..-76 dBm / 7..7 dB (n=3) | -77..-77 dBm / 7..8 dB (n=3) | 0/0 |
| 8 | 160 | CLEAN | 3/3; 3/0; 0/0 | -75..-74 dBm / 7..8 dB (n=3) | -77..-76 dBm / 7..7 dB (n=3) | 3/3; 3/0; 0/0 | -77..-75 dBm / 6..7 dB (n=3) | -78..-77 dBm / 7..8 dB (n=3) | 0/0 |
| 8 | 180 | CLEAN | 3/3; 3/0; 0/0 | -76..-75 dBm / 7..7 dB (n=3) | -78..-78 dBm / 7..7 dB (n=3) | 3/3; 3/0; 0/0 | -77..-76 dBm / 6..7 dB (n=3) | -78..-78 dBm / 7..8 dB (n=3) | 0/0 |
| 8 | 200 | CLEAN | 3/3; 3/0; 0/0 | -76..-75 dBm / 7..8 dB (n=3) | -78..-78 dBm / 7..7 dB (n=3) | 3/3; 3/0; 0/0 | -77..-76 dBm / 6..7 dB (n=3) | -78..-78 dBm / 7..8 dB (n=3) | 0/0 |
| 9 | 1 | DEGRADED | 10/10; 11/1; 1/0 | -79..-77 dBm / 7..8 dB (n=10) | -79..-78 dBm / 7..8 dB (n=10) | 10/10; 10/0; 0/0 | -80..-78 dBm / 6..8 dB (n=10) | -78..-77 dBm / 7..8 dB (n=10) | 0/0 |
| 9 | 8 | CLEAN | 3/3; 3/0; 0/0 | -76..-76 dBm / 8..8 dB (n=3) | -79..-78 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -78..-77 dBm / 7..8 dB (n=3) | -78..-77 dBm / 8..8 dB (n=3) | 0/0 |
| 9 | 16 | CLEAN | 3/3; 3/0; 0/0 | -75..-75 dBm / 8..9 dB (n=3) | -78..-77 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -76..-75 dBm / 8..8 dB (n=3) | -76..-76 dBm / 8..8 dB (n=3) | 0/0 |
| 9 | 32 | CLEAN | 3/3; 3/0; 0/0 | -75..-75 dBm / 8..8 dB (n=3) | -78..-78 dBm / 7..8 dB (n=3) | 3/3; 3/0; 0/0 | -77..-76 dBm / 7..8 dB (n=3) | -78..-77 dBm / 7..8 dB (n=3) | 0/0 |
| 9 | 64 | CLEAN | 3/3; 3/0; 0/0 | -77..-76 dBm / 6..8 dB (n=3) | -80..-78 dBm / 7..8 dB (n=3) | 3/3; 3/0; 0/0 | -77..-76 dBm / 6..7 dB (n=3) | -78..-77 dBm / 8..8 dB (n=3) | 0/0 |
| 9 | 96 | CLEAN | 3/3; 3/0; 0/0 | -76..-75 dBm / 8..8 dB (n=3) | -80..-79 dBm / 5..6 dB (n=3) | 3/3; 3/0; 0/0 | -78..-78 dBm / 6..6 dB (n=3) | -77..-76 dBm / 8..8 dB (n=3) | 0/0 |
| 9 | 128 | CLEAN | 3/3; 3/0; 0/0 | -75..-74 dBm / 8..8 dB (n=3) | -79..-78 dBm / 7..7 dB (n=3) | 3/3; 3/0; 0/0 | -78..-78 dBm / 6..7 dB (n=3) | -76..-76 dBm / 8..8 dB (n=3) | 0/0 |
| 9 | 160 | CLEAN | 3/3; 3/0; 0/0 | -76..-76 dBm / 8..8 dB (n=3) | -78..-77 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -77..-76 dBm / 8..8 dB (n=3) | -79..-78 dBm / 7..8 dB (n=3) | 0/0 |
| 9 | 180 | CLEAN | 3/3; 3/0; 0/0 | -76..-76 dBm / 8..8 dB (n=3) | -79..-77 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -76..-76 dBm / 8..8 dB (n=3) | -79..-78 dBm / 8..8 dB (n=3) | 0/0 |
| 9 | 200 | CLEAN | 3/3; 3/0; 0/0 | -77..-75 dBm / 6..8 dB (n=3) | -78..-78 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -76..-75 dBm / 8..8 dB (n=3) | -79..-78 dBm / 8..8 dB (n=3) | 0/0 |
| 10 | 1 | CLEAN | 3/3; 3/0; 0/0 | -80..-78 dBm / 8..8 dB (n=3) | -81..-80 dBm / 6..7 dB (n=3) | 3/3; 3/0; 0/0 | -82..-81 dBm / 6..7 dB (n=3) | -81..-79 dBm / 8..8 dB (n=3) | 0/0 |
| 10 | 8 | CLEAN | 3/3; 3/0; 0/0 | -75..-74 dBm / 8..8 dB (n=3) | -82..-81 dBm / 7..8 dB (n=3) | 3/3; 3/0; 0/0 | -78..-78 dBm / 8..8 dB (n=3) | -80..-80 dBm / 8..8 dB (n=3) | 0/0 |
| 10 | 16 | CLEAN | 3/3; 3/0; 0/0 | -75..-74 dBm / 8..8 dB (n=3) | -81..-78 dBm / 6..8 dB (n=3) | 3/3; 3/0; 0/0 | -76..-75 dBm / 8..8 dB (n=3) | -78..-78 dBm / 8..8 dB (n=3) | 0/0 |
| 10 | 32 | DEGRADED | 10/10; 12/2; 2/0 | -74..-73 dBm / 8..9 dB (n=10) | -79..-78 dBm / 8..8 dB (n=10) | 10/10; 10/0; 0/0 | -75..-74 dBm / 7..8 dB (n=10) | -79..-78 dBm / 8..9 dB (n=10) | 1/0 |
| 10 | 64 | CLEAN | 3/3; 3/0; 0/0 | -74..-73 dBm / 8..8 dB (n=3) | -79..-78 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -75..-75 dBm / 8..8 dB (n=3) | -79..-78 dBm / 8..8 dB (n=3) | 0/0 |
| 10 | 96 | CLEAN | 3/3; 3/0; 0/0 | -74..-73 dBm / 8..9 dB (n=3) | -79..-79 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -75..-75 dBm / 7..8 dB (n=3) | -79..-78 dBm / 8..8 dB (n=3) | 0/0 |
| 10 | 128 | CLEAN | 3/3; 3/0; 0/0 | -74..-74 dBm / 8..8 dB (n=3) | -79..-79 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -74..-73 dBm / 8..8 dB (n=3) | -80..-79 dBm / 7..8 dB (n=3) | 0/0 |
| 10 | 160 | CLEAN | 3/3; 3/0; 0/0 | -76..-74 dBm / 8..8 dB (n=3) | -78..-77 dBm / 8..9 dB (n=3) | 3/3; 3/0; 0/0 | -74..-74 dBm / 8..8 dB (n=3) | -80..-79 dBm / 7..8 dB (n=3) | 0/0 |
| 10 | 180 | CLEAN | 3/3; 3/0; 0/0 | -75..-74 dBm / 8..8 dB (n=3) | -78..-77 dBm / 8..9 dB (n=3) | 3/3; 3/0; 0/0 | -74..-73 dBm / 8..8 dB (n=3) | -79..-79 dBm / 8..8 dB (n=3) | 0/0 |
| 10 | 200 | CLEAN | 3/3; 3/0; 0/0 | -75..-75 dBm / 8..8 dB (n=3) | -78..-77 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -74..-74 dBm / 8..8 dB (n=3) | -80..-79 dBm / 8..8 dB (n=3) | 0/0 |
| 11 | 1 | CLEAN | 3/3; 3/0; 0/0 | -79..-79 dBm / 8..8 dB (n=3) | -80..-79 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -79..-77 dBm / 8..8 dB (n=3) | -80..-80 dBm / 8..8 dB (n=3) | 0/0 |
| 11 | 8 | CLEAN | 3/3; 3/0; 0/0 | -77..-76 dBm / 8..8 dB (n=3) | -79..-79 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -76..-75 dBm / 8..8 dB (n=3) | -80..-79 dBm / 8..8 dB (n=3) | 0/0 |
| 11 | 16 | DEGRADED | 10/10; 13/3; 3/0 | -76..-75 dBm / 8..8 dB (n=12) | -80..-79 dBm / 8..8 dB (n=10) | 10/10; 10/0; 0/0 | -75..-73 dBm / 8..8 dB (n=10) | -80..-79 dBm / 8..8 dB (n=10) | 1/0 |
| 11 | 32 | CLEAN | 3/3; 3/0; 0/0 | -74..-74 dBm / 8..9 dB (n=3) | -79..-79 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -73..-73 dBm / 8..8 dB (n=3) | -79..-79 dBm / 8..8 dB (n=3) | 0/0 |
| 11 | 64 | CLEAN | 3/3; 3/0; 0/0 | -74..-73 dBm / 8..9 dB (n=3) | -79..-79 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -73..-72 dBm / 8..8 dB (n=3) | -79..-79 dBm / 8..8 dB (n=3) | 0/0 |
| 11 | 96 | CLEAN | 3/3; 3/0; 0/0 | -74..-74 dBm / 8..8 dB (n=3) | -79..-79 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -73..-73 dBm / 8..8 dB (n=3) | -80..-79 dBm / 8..8 dB (n=3) | 0/0 |
| 11 | 128 | CLEAN | 3/3; 3/0; 0/0 | -75..-75 dBm / 8..8 dB (n=3) | -79..-78 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -74..-73 dBm / 8..8 dB (n=3) | -80..-78 dBm / 8..8 dB (n=3) | 0/0 |
| 11 | 160 | CLEAN | 3/3; 3/0; 0/0 | -75..-73 dBm / 8..8 dB (n=3) | -78..-78 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -75..-73 dBm / 8..8 dB (n=3) | -78..-78 dBm / 8..8 dB (n=3) | 0/0 |
| 11 | 180 | CLEAN | 3/3; 3/0; 0/0 | -73..-73 dBm / 8..9 dB (n=3) | -79..-79 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -74..-73 dBm / 8..8 dB (n=3) | -78..-78 dBm / 8..8 dB (n=3) | 0/0 |
| 11 | 200 | CLEAN | 3/3; 3/0; 0/0 | -73..-73 dBm / 8..8 dB (n=3) | -80..-79 dBm / 7..8 dB (n=3) | 3/3; 3/0; 0/0 | -74..-74 dBm / 8..8 dB (n=3) | -78..-78 dBm / 8..8 dB (n=3) | 0/0 |
| 12 | 1 | CLEAN | 3/3; 3/0; 0/0 | -79..-77 dBm / 8..8 dB (n=3) | -78..-77 dBm / 7..8 dB (n=3) | 3/3; 3/0; 0/0 | -79..-78 dBm / 7..8 dB (n=3) | -78..-77 dBm / 8..8 dB (n=3) | 0/0 |
| 12 | 8 | CLEAN | 3/3; 3/0; 0/0 | -75..-75 dBm / 8..8 dB (n=3) | -77..-77 dBm / 7..8 dB (n=3) | 3/3; 3/0; 0/0 | -77..-76 dBm / 8..8 dB (n=3) | -77..-77 dBm / 8..8 dB (n=3) | 0/0 |
| 12 | 16 | CLEAN | 3/3; 3/0; 0/0 | -75..-75 dBm / 8..8 dB (n=3) | -78..-77 dBm / 7..8 dB (n=3) | 3/3; 3/0; 0/0 | -76..-75 dBm / 8..8 dB (n=3) | -77..-77 dBm / 8..8 dB (n=3) | 0/0 |
| 12 | 32 | CLEAN | 3/3; 3/0; 0/0 | -74..-73 dBm / 8..8 dB (n=3) | -78..-77 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -74..-74 dBm / 7..8 dB (n=3) | -78..-77 dBm / 8..8 dB (n=3) | 0/0 |
| 12 | 64 | CLEAN | 3/3; 3/0; 0/0 | -74..-74 dBm / 8..8 dB (n=3) | -78..-77 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -74..-74 dBm / 8..8 dB (n=3) | -78..-77 dBm / 8..8 dB (n=3) | 0/0 |
| 12 | 96 | CLEAN | 3/3; 3/0; 0/0 | -73..-73 dBm / 8..8 dB (n=3) | -78..-76 dBm / 7..8 dB (n=3) | 3/3; 3/0; 0/0 | -73..-72 dBm / 8..8 dB (n=3) | -78..-77 dBm / 8..8 dB (n=3) | 0/0 |
| 12 | 128 | CLEAN | 3/3; 3/0; 0/0 | -74..-74 dBm / 8..8 dB (n=3) | -77..-76 dBm / 7..8 dB (n=3) | 3/3; 3/0; 0/0 | -74..-73 dBm / 8..8 dB (n=3) | -77..-77 dBm / 8..8 dB (n=3) | 0/0 |
| 12 | 160 | CLEAN | 3/3; 3/0; 0/0 | -73..-73 dBm / 8..8 dB (n=3) | -77..-76 dBm / 8..8 dB (n=3) | 3/3; 3/0; 0/0 | -72..-72 dBm / 7..7 dB (n=3) | -77..-77 dBm / 8..8 dB (n=3) | 0/0 |
| 12 | 180 | CLEAN | 3/3; 3/0; 0/0 | -73..-72 dBm / 7..8 dB (n=3) | -77..-75 dBm / 6..7 dB (n=3) | 3/3; 3/0; 0/0 | -72..-72 dBm / 6..7 dB (n=3) | -79..-76 dBm / 8..8 dB (n=3) | 0/0 |
| 12 | 200 | CLEAN | 3/3; 3/0; 0/0 | -73..-72 dBm / 6..8 dB (n=3) | -76..-75 dBm / 5..6 dB (n=3) | 3/3; 3/0; 0/0 | -72..-71 dBm / 5..6 dB (n=3) | -77..-76 dBm / 8..8 dB (n=3) | 0/0 |

## CRC/HDR and retry evidence

CRC/HDR has no trusted protocol USER sequence. Receiver-local telemetry cursor, RF frame length, RSSI/SNR and event ordering are contextual only; raw events remain authoritative in `serialterminal.log`.

| Point | Direction/context | Receiver | Cursor | RF frame | RSSI/SNR | Ordering |
|---|---|---|---:|---:|---|---|
| SF7/BW500/1B | A->B | LoRa-Chatter-1B44 | 350–352 | 244B | -125/-12 dBm/dB | after ACK 10C0/0, before next A→B USER TX; no USER sequence assigned |
| SF7/BW500/64B | A->B | LoRa-Chatter-1B44 | 1960–1962 | 8B | -126/-12 dBm/dB | before A→B first TX 10C0/72; no USER sequence assigned |
| SF8/BW500/64B | A->B | LoRa-Chatter-72E0 | 3608–3609 | 76B | -75/3 dBm/dB | after first attempt 10C0/146, before its ACK timeout/retry context; no USER sequence assigned |
| SF10/BW500/32B | A->B | LoRa-Chatter-72E0 | 6951–6952 | 44B | -74/3 dBm/dB | near first-attempt telemetry 10C0/289 in the serialized A→B window; no USER sequence assigned |
| SF11/BW500/16B | A->B | LoRa-Chatter-72E0 | 8501–8502 | 28B | -75/2 dBm/dB | inside serialized A→B 16B window before later ACK/retry events; no USER sequence assigned |

HDR events: none.

ACK timeout/retry events (each transaction eventually received its matching ACK):

- SF8/BW500/64B A->B: 1 ACK timeout(s): seq 146 attempt 1; row reports physical retries.
- SF9/BW500/1B A->B: 1 ACK timeout(s): seq 197 attempt 1; row reports physical retries.
- SF10/BW500/32B A->B: 2 ACK timeout(s): seq 289 attempt 1, seq 296 attempt 1; row reports physical retries.
- SF11/BW500/16B A->B: 3 ACK timeout(s): seq 356 attempt 1, seq 357 attempt 1, seq 359 attempt 1; row reports physical retries.

Final delivery failures: 0. Queue/correlation anomalies: 0.

## Extensions and execution notes

- Real anomaly points extended to 10+10: SF7/1B, SF7/64B, SF8/64B, SF9/1B, SF10/32B, SF11/16B. The 10+10 totals include the initial requests.
- SF7/8B and SF7/16B were overmeasured at 10+10 because the initial local anomaly predicate misread the normal configured `timeout=...` field in `DELIVERY WAIT_ACK` as an observed timeout. The forensic log shows no CRC/HDR, ACK timeout or retry at these points; every delivery matched ACK on physical attempt one, so both remain CLEAN. The predicate was corrected before later SF rows.
- SF7/32B has 9 settled A→B and 3 settled B→A requests. The same false-positive extension began and stopped at a settled boundary after the ninth A→B request. No RF anomaly occurred; the required 3+3 coverage is complete.
- SF10/8B marker construction rejected an overlong marker before any USER transmission. The marker was shortened before sending; resulting exact-length 3+3 data is valid.
- No contaminated point needed a from-scratch repeat. No unmeasured points remain; scanning continued through 200B after anomalies.

## Provenance and files

`/version` on both nodes:

```text
FIRMWARE Chatter git=b76ffa04ab47a3f344b8270159ab274256f6ff62 state=clean env=esp32-s3-n16r8
FIRMWARE IMAGE validation_sha256=c4e8407581882b7ca53680197748d4e8dabdf2cf9a389ad62bf271d6ef9307b6 status=OK slot=0
BUILD META toolchain_sha256=cbb867e635dd96b27372354196469534b17a4276405a02a3ea1c58d8fc3f0d19 pio=6.2.0
```

Run identity `RUN_20260925T105411Z_main_bw500`; matching OBS `OBS_20260925T105411Z_main_bw500.md`.
Forensic interval: 2026-09-25 13:54:14–14:37:01 Europe/Moscow (10:54:14–11:37:01 UTC).
Evidence files are exact finalized `serialterminal.log` and `serialterminal.console.log`.
