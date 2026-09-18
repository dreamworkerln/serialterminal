# Concurrent BLE `/help` burst — two LoRa-Chatter nodes

Result: PASS
Observed: 2026-09-18T08:27:46Z

## Scope and provenance

The requested operator-stated firmware target was `lora-sack-protocol` checkpoint `00f590dbe3d9a42c971f5f35d883c86f0f1e9c68`. The physical nodes did not provide an independently verifiable firmware SHA, so firmware provenance is recorded as unknown.

SerialTerminal process: one process, one forensic log, four simultaneous long-lived sessions.

Canonical transport correlation:

- Node A `LoRa-Chatter-1B44`: USB session `s2`, BLE session `s3`.
- Node B `LoRa-Chatter-72E0`: USB session `s1`, BLE session `s4`.

Before measurement both nodes reported `current=CHAT echo=OFF`; `/cancel all` reported `pending=none queue_removed=0`.

## Measured rounds

Each round sent exactly one `/help` to BLE A and immediately one `/help` to BLE B. No `/help` was sent through USB.

| round | node identity | BLE result | attempts | min_sendable | sendable_zero | gatt_errors | gatt_retries | congest_events | decongest_events | wait_timeouts | queue_rejects | disconnect_aborts | terminal_errors | last_gatt_error |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | LoRa-Chatter-1B44 | COMPLETE | 93 | 0 | 110 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0x00000000 |
| 1 | LoRa-Chatter-72E0 | COMPLETE | 93 | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0x00000000 |
| 2 | LoRa-Chatter-1B44 | COMPLETE | 93 | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0x00000000 |
| 2 | LoRa-Chatter-72E0 | COMPLETE | 93 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0x00000000 |
| 3 | LoRa-Chatter-1B44 | COMPLETE | 93 | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0x00000000 |
| 3 | LoRa-Chatter-72E0 | COMPLETE | 93 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0x00000000 |

Every BLE response contained one coherent help block with the required headings, its own canonical node identity, and the final status line `[SYS] BLE CLIENT: machine telemetry 0004 subscribed in background`. Matching USB-only `[BLE-TX-DIAG]` lines were observed in the same process for all six cases.

## Summary

- formal congestion event path observed: no (`congest_events=0` in all cases); formal `ESP_GATTS_CONGEST_EVT` path was not observed in this run;
- capacity-zero path observed: yes;
- ERROR_GATT retry path observed: no (`gatt_errors=0` in all cases);
- unexpected reconnect: no;
- forensic gap: no;
- cursor expired: no;
- send outcome unknown: no.

The capacity-zero observations did not produce wait timeouts or terminal errors. No formal congestion-event or ERROR_GATT retry conclusion is claimed.

## Final state

After measurement both nodes were returned to `CHAT`, `echo=OFF`, with no pending reliable USER flow (`pending=none queue_removed=0`). All four sessions were closed and the single SerialTerminal agent process was terminated after log flush.

The exact forensic and companion console logs are stored beside this report in the RUN bundle.
