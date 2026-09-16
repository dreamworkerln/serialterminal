# BLE concurrent `/help` completeness run

Observed: 2026-09-16T03:44:42Z
Topic: ble-concurrent-help-completeness-take6
Result: PASS
Firmware: unknown

## Scope

Short hardware check of BLE human-console output completeness while long `/help` output was active concurrently on exact physical nodes LoRa-Chatter-1B44 and LoRa-Chatter-72E0.

SerialTerminal checkout was `dev` at `4f562062afd64750679a4d5562a29a022025a967` and was clean before the run. One long-lived `python3 serialterminal.py agent` process and explicit `chatter` profiles were used.

## Discovery and setup

BLE discovery factually returned both required targets. Each session reached `connected`; `/chat` returned `OUTPUT CHAT`, and `/help` output showed `current=CHAT echo=OFF`. Telemetry notifications remained a separate stream and were not used for completeness classification.

## Results

| Phase | Node | Complete | Malformed | Inconclusive | Chat raw ranges |
|---|---|---:|---:|---:|---|
| A1 solo | 1B44 | 2/2 | 0/2 | 0/2 | 38-130; 133-225 |
| A2 solo | 72E0 | 2/2 | 0/2 | 0/2 | 38-130; 158-250 |
| B concurrent | 1B44 | 3/3 | 0/3 | 0/3 | 38-130; 158-250; 253-345 |
| B concurrent | 72E0 | 3/3 | 0/3 | 0/3 | 13-105; 133-225; 253-345 |
| C1 recovery | 1B44 | 2/2 | 0/2 | 0/2 | 373-465; 493-585 |
| C2 recovery | 72E0 | 2/2 | 0/2 | 0/2 | 13-105; 133-225 |

The first solo 1B44 response used TX events 36-37 and chat RX 38-130; its second used TX 131-132 and chat RX 133-225. The first solo 72E0 response used TX 36-37 and chat RX 38-130; its second used TX 156-157 and chat RX 158-250.

Concurrent iteration TX pairs were 1B44/72E0: `36-37`/`11-12`, `156-157`/`131-132`, and `251-252`/`251-252`; each node had only one outstanding test command until its response completed. Recovery TX pairs were 1B44 `371-372`, `491-492`, and 72E0 `11-12`, `131-132`.

Classification used raw `chat` events and their `data_b64` chunks, with logical lines as secondary readable evidence. Every measured response matched the complete same-node baseline output.

## Confounders and lifecycle

- `forensic_gap`: no.
- Unexpected reconnect affecting comparison: no. Each session initially reported `reconnecting` during normal profile connection preamble, then reached `connected`; no measured response was crossed by a reconnect.
- Same-node command overlap: no.
- No malformed evidence and no root cause is assigned.

## Final state

Both nodes were left powered on by the prepared physical setup, with human output remaining CHAT and echo OFF. All sessions were closed normally; `list_sessions` returned an empty list. The agent process exited cleanly with code 0. No reboot, flash, source inspection, or repository source change was performed.

Exact evidence is in `serialterminal.log` and `serialterminal.console.log` in this bundle.
