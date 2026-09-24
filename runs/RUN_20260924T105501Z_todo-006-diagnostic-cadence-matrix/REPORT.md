# TODO_006 diagnostic size and cadence validation

Observed: 2026-09-24T10:55:01Z  
Result: PASS

## Scope and identity

Focused canonical physical two-node run for diagnostic frame sizes and local
PING-start cadence. `s1` (LoRa-Chatter-1B44) initiated diagnostics; `s2`
(LoRa-Chatter-72E0) remained heartbeat OFF and diagnostic OFF as the responder.

Both nodes reported firmware
`3b386dfa3eae68be057ab9aeec37a89367773839`, `state=clean`, and image
validation `status=OK`. Runtime SHA: `04756c38a41dae8ebac063fed584a066187071b6`.
The observation workspace was `node_observations@e838ab156e9cd443b7df73d88c391530c905da25`;
the required `61444ef1efc95138b3efe48874c362acf210092d` base is its ancestor.

## Fast matrix

PHY: 470 MHz, SF7, BW500 kHz, power 2 dBm. Counts use unique local A PING
sequence numbers from finalized telemetry. Each row has at least six consecutive
same-size starts; cadence deltas do not cross a size change or a diagnostic
restart. `OK/NRP/CRC/HDR` reflects correlated transaction outcomes.

| Size | PING | OK/NRP/CRC/HDR | TX ms min/avg/max | Start delta us min/avg/max | `<1,000,000` | Size match |
|---:|---:|---:|---:|---:|---:|:---:|
| 16B | 55 | 55/0/0/0 | 14/14/14 | 1,001,954/1,003,452.27/1,005,026 | 0 | yes |
| 32B | 36 | 36/0/0/0 | 19/19/19 | 1,001,859/1,003,424.34/1,005,060 | 0 | yes |
| 64B | 93 | 92/1/0/0 | 31/31/31 | 1,001,895/1,003,802.67/1,023,040 | 0 | yes |
| 200B | 24 | 24/0/0/0 | 81/81.21/82 | 1,001,830/1,004,382.13/1,006,016 | 0 | yes |
| 225B | 63 | 63/0/0/0 | 90/90.95/91 | 1,001,838/1,003,658.35/1,005,035 | 0 | yes |
| 255B | 18 | 18/0/0/0 | 101/101.94/102 | 1,001,955/1,003,224.18/1,005,015 | 0 | yes |

All fast cadence values are computed from wrap-safe uint32 deltas of firmware
`start_us`; no host or BLE timestamp was used for cadence acceptance. There were
zero deltas below 1,000,000 us. A single NRP occurred at 64B sequence 129; its
next interval was 1,023,040 us and remained above the floor. No fatal radio
state was reported.

## Slow point

PHY: 470 MHz, SF12, BW62.5 kHz, power 2 dBm; diagnostic frame 16B. Twelve local
PING starts produced eleven same-size deltas:

- Outcomes: 12 OK/PONG, 0 NRP, 0 CRC, 0 HDR.
- TX `time`: 2639/2639/2639 ms min/avg/max.
- `start_us` delta: 5,791,986/5,926,809.27/6,114,038 us min/avg/max.
- Deltas below 5,276,000 us: 0.
- Correlated 16B PONG: yes.

The comparison floor is the supplied 5,276,000 us contract. `time=<ms>` is
retained as additional node evidence only; all cadence decisions use `start_us`.

## Correlated examples

255B fast exchange, sequence 271:

```text
A TX HEARTBEAT PING seq=271 frame=255B start_us=1288981026 time=102 ms
B RX HEARTBEAT PING session=4176 seq=271 frame=255B
B TX HEARTBEAT PONG frame=255B request=4176/271 OK time=101 ms
A RX HEARTBEAT PONG request=4176/271 frame=255B
```

Slow 16B exchange, sequence 289:

```text
A TX HEARTBEAT PING seq=289 frame=16B start_us=1383839356 time=2639 ms
B RX HEARTBEAT PING session=4176 seq=289 frame=16B
B TX HEARTBEAT PONG frame=16B request=4176/289 OK time=2640 ms
A RX HEARTBEAT PONG request=4176/289 frame=16B
```

## State changes, cleanup, and evidence

`/diag size 200` and the first `/diag size 255` attempt each returned
`DIAG SIZE BUSY: heartbeat transaction active`. The affected state was reset
with confirmed `/diag off` then `/diag on`; each size was subsequently accepted
and confirmed before its measured row. No `INPUT QUEUE FULL` or fatal radio
state was observed. All six requested sizes, including 255B, produced
size-matched PONGs.

Final `/config` on both nodes confirmed 470 MHz, SF12, BW62.5 kHz, power 2 dBm,
heartbeat OFF, and diag OFF. Both `cancel all` responses showed `pending=none`;
echo-loop was stopped. Both sessions were closed. The exact forensic log and
companion console log from the single agent process are included here.

Cadence source: only node `start_us` telemetry. The host-timestamped console log
is included for command/state transitions and session correlation, not cadence
acceptance.
