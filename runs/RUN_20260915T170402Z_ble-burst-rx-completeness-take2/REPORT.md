# BLE burst RX completeness diagnostic

Result: INCONCLUSIVE

SerialTerminal exact SHA: 276aeee2ca90e6ee964120153bf72e5dbafcf307
Firmware: unknown

## Nodes and sessions

- LoRa-Chatter-1B44 — `s1` — BLE `44:1B:F6:8D:B7:A9` — profile `chatter` — streams `chat`, `telemetry`
- LoRa-Chatter-72E0 — `s2` — BLE `E0:72:A1:D5:4C:15` — profile `chatter` — streams `chat`, `telemetry`

Both sessions reached `connected`. The only `reconnecting` states were during initial open; no disconnect/reconnect occurred during an affected test interval.

## Phase A — isolated baseline

- LoRa-Chatter-1B44: PASS. `/chat` then isolated `/help` completed through the observed late sections (`COMMANDS`, `RAW CONTROLS`, `ANDROID BLE TERMINAL MACROS`, `Nordic UART`, `BLE CLIENT`). Raw chat was seq 38–130, with no `forensic_gap`.
- LoRa-Chatter-72E0: INCONCLUSIVE. Isolated `/help` itself was malformed relative to the same-node complete baseline shape. Raw chat seq 38–128 included, for example, seq 70 `W1NZU10gICBDSEFUICAgICAgIGM=` (`[SYS]   CHAT       c`) followed by seq 71 `W1NZU10gICBURUxFTUVUUlkgIHQ=` (`[SYS]   TELEMETRY  t`), and seq 96–97 began `/cancel` without the expected continuation. No `forensic_gap` was recorded.

The isolated anomaly was still byte-level interpretable, so the requested matrix continued.

## Phase B — concurrent two-session `/help`

Iterations complete: 5/5. Session-cases: 10; malformed/loss cases: 10/10. Each iteration sent `/help` to both sessions, then observed to completion using only returned per-session cursors.

| Iteration | LoRa-Chatter-1B44 | LoRa-Chatter-72E0 |
|---|---|---|
| 1 | INCONCLUSIVE; late help content did not match isolated byte baseline | INCONCLUSIVE; output remained affected by isolated baseline anomaly |
| 2 | INCONCLUSIVE; late `ANDROID`/Nordic continuation was incomplete | INCONCLUSIVE; output remained affected by isolated baseline anomaly |
| 3 | INCONCLUSIVE; help sections were malformed/shortened | INCONCLUSIVE; help sections were malformed/shortened |
| 4 | INCONCLUSIVE; `ANDROID`/Nordic area was malformed | INCONCLUSIVE; help sections were malformed/shortened |
| 5 | INCONCLUSIVE; late help sections were malformed/shortened | INCONCLUSIVE; help sections were malformed/shortened |

Representative exact raw chunks from the first concurrent iteration for LoRa-Chatter-1B44 were seq 235 `W1NZU10gICBIRVggbWFjcm8sIG4=` (`[SYS]   HEX macro, n`) immediately followed by seq 236 `W1NZU10gQkxFIENMSUVOVDogbWE=` (`[SYS] BLE CLIENT: ma`), with the isolated baseline's intervening continuation absent. The complete raw events and lines for every iteration are in `serialterminal.log`.

## Phase C — original burst shape

Iterations complete: 5/5. Session-cases: 10; malformed/loss cases: 10/10. Each iteration sent `/help` and `/id` without waiting between the pair on each session, with both session pairs issued in one short burst.

| Iteration | LoRa-Chatter-1B44 | LoRa-Chatter-72E0 |
|---|---|---|
| 1 | INCONCLUSIVE; help tail was malformed and `/id` output interleaved | INCONCLUSIVE; help tail was malformed and `/id` output interleaved |
| 2 | INCONCLUSIVE; help and `/id` output had malformed continuation | INCONCLUSIVE; help and `/id` output had malformed continuation |
| 3 | INCONCLUSIVE; raw help tail contained missing/relocated continuation | INCONCLUSIVE; raw help tail contained missing/relocated continuation |
| 4 | INCONCLUSIVE; raw help tail malformed around Nordic/`BLE CLIENT` | INCONCLUSIVE; raw help tail malformed/interleaved |
| 5 | INCONCLUSIVE; raw help tail malformed around Nordic/`BLE CLIENT` | INCONCLUSIVE; raw help tail malformed/interleaved |

Representative exact raw chunks from Phase C iteration 1, LoRa-Chatter-1B44, were seq 665 `W1NZU10gICAxNCAzMT1DSEFUICA=` (`[SYS]   14 31=CHAT  `), seq 666 `MTQgMzI9VEVMRU1FVFJZICAxNCA=` (`14 32=TELEMETRY  14 `), then seq 667 `W1NZU10gICBOb3JkaWMgVUFSVCA=` (`[SYS]   Nordic UART `); the expected isolated continuation between the raw help sections was not present in the corresponding completed output. Exact event records, including all `data_b64`, are persisted in the bundle log.

## Reproduction and boundary

- Phase A: 1/2 nodes byte-complete; 1/2 inconclusive from isolated malformed output.
- Phase B: 10/10 session-cases malformed or baseline-inconclusive.
- Phase C: 10/10 session-cases malformed or baseline-inconclusive.
- `forensic_gap`: no.
- Disconnect/reconnect during affected intervals: no.
- First malformed case: LoRa-Chatter-72E0 / `s2` / Phase A isolated `/help`, raw chat seq 70–71 (also seq 96–97).
- Affected ranges in reproduced cases are documented by the exact `seq_first`/`seq_last`, events, and `data_b64` in `serialterminal.log`; no single deeper owner is assigned.

Finding boundary: malformed or missing expected BLE `chat` byte content was observed at the recorded raw RX event boundary before ManagedSession logical-line completion; ownership below that recorded callback/event boundary remains unresolved.

## Final state

Both nodes reported connected with output mode `CHAT`, `echo=OFF` was observed, and `queued_tx=0` before close. Both sessions were then closed normally and the single SerialTerminal agent exited cleanly. No reboot or flash was performed.

## Persisted artifacts

- Run bundle: `runs/RUN_20260915T170402Z_ble-burst-rx-completeness-take2/`
- Forensic log: `runs/RUN_20260915T170402Z_ble-burst-rx-completeness-take2/serialterminal.log`
- Console log: `runs/RUN_20260915T170402Z_ble-burst-rx-completeness-take2/serialterminal.console.log`
- Observation: `observations/OBS_20260915T170402Z_ble-burst-rx-completeness-take2.md`
