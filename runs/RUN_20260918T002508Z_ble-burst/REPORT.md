# BLE burst test report

Result: PASS

Observed: 2026-09-18T00:25:08Z
Firmware: unknown
SerialTerminal: dreamworkerln/serialterminal@4f562062afd64750679a4d5562a29a022025a967

## Scope

Diagnostic BLE burst test of the current physical Chatter nodes `LoRa-Chatter-1B44` and `LoRa-Chatter-72E0`. No firmware flash, reboot, or power-cycle was performed.

## Sessions

- One long-lived `python3 serialterminal.py agent` process was used.
- BLE sessions were opened concurrently with explicit `profile:"chatter"`.
- `s1`: `LoRa-Chatter-1B44`, BLE `44:1B:F6:8D:B7:A9`, final pre-close status `connected`, `queued_tx:0`.
- `s2`: `LoRa-Chatter-72E0`, BLE `E0:72:A1:D5:4C:15`, final pre-close status `connected`, `queued_tx:0`.
- Chatter connect preamble `/id` confirmed both canonical identities.
- `/chat` was sent to both nodes and each produced `OUTPUT MODE ... state=CHAT` plus `[SYS] OUTPUT CHAT`.

## Burst rounds

Each round used one `/help` per node. A new help was sent only after the prior help for that node had completed in the observed event stream.

| Round | order | LoRa-Chatter-1B44 | LoRa-Chatter-72E0 |
|---|---|---|---|
| 1 | 1B44, then 72E0 | COMPLETE; raw seq 36–130 | COMPLETE; raw seq 36–130 |
| 2 | 72E0, then 1B44 | COMPLETE; raw seq 131–250 | COMPLETE; raw seq 156–250 |
| 3 | batch, near-simultaneous | COMPLETE; raw seq 251–345 | COMPLETE; raw seq 251–370 |

For every help, the observed isolated shape included `[SYS] CHATTER HELP`, the node identity, the complete help sections through `BLE CLIENT: machine telemetry 0004 subscribed in background`, and the terminating logical lines. Raw BLE events are preserved separately in `artifacts/raw-ble-events-s1.jsonl` and `artifacts/raw-ble-events-s2.jsonl`.

## Run-wide observations

- Forensic gap: no. No `forensic_gap` record was present in the exact forensic log.
- Disconnect/reconnect during burst: no. Initial open transitions briefly reported `reconnecting` before `connected`; no later disconnect/reconnect was observed.
- Cursor expiry: no `cursor_expired` response.
- Transport send outcome unknown: no. All six `/help` sends had `queued` acceptance followed by `tx_state:"written"`.
- Other agent/transport errors: none observed in the exact run log.
- Same-node command overlap: no. Per-node command sequencing was serialized by waiting for completion before the next `/help`.
- Final session state before close: both `connected`; both closed successfully through the agent API.

## Final state and limitations

Both sessions were closed through the SerialTerminal agent API. The nodes were not rebooted or power-cycled. This report records observations only and does not assign a cause to any data loss or corruption.

## Persistent evidence

This report and the exact logs are in this run bundle. The companion observation is the matching `OBS_20260918T002508Z_ble-burst.md`.
