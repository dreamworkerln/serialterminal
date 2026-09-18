# Final correlated BLE diagnostic burst

Result: PASS

Observed run identity: `2026-09-18T00:50:40Z_ble-correlated-help-burst`.
SerialTerminal: `dreamworkerln/serialterminal@4f562062afd64750679a4d5562a29a022025a967`.
Firmware: `unknown`.

## Setup

- One SerialTerminal agent process was started with the exact forensic log `/tmp/serialterminal-ble-correlated-20260918T005040Z.log`; its exact companion was `/tmp/serialterminal-ble-correlated-20260918T005040Z.console.log`.
- `s1` was `LoRa-Chatter-1B44`, BLE address `44:1B:F6:8D:B7:A9`; `s2` was `LoRa-Chatter-72E0`, BLE address `E0:72:A1:D5:4C:15`.
- Both sessions used `profile: "chatter"`, reached stable `connected`, and were set to CHAT. Baseline cursors before the burst were `s1=35`, `s2=10`.
- No reboot or power-cycle was performed.

## Correlated rounds

All timestamps below are copied from raw event evidence. UTC logger timestamps are shown where available; raw numeric timestamps are retained exactly in the logs.

| Round | Order | Request ID | Session / node | Send UTC | Help raw seq begin/end | Completion UTC | Classification |
|---|---|---:|---|---|---|---|---|
| 1 | 1 | 9 | s1 / LoRa-Chatter-1B44 | 2026-09-18T00:52:11.223+00:00 (`1789692731.223954`) | 38–130 | 2026-09-18T00:52:12.139+00:00 (`1789692732.1394846`) | COMPLETE |
| 1 | 2 | 10 | s2 / LoRa-Chatter-72E0 | 2026-09-18T00:52:11.224+00:00 (`1789692731.224514`) | 38–130 | 2026-09-18T00:52:11.616+00:00 (`1789692731.6163921`) | COMPLETE |
| 2 | 1 | 12 | s2 / LoRa-Chatter-72E0 | 2026-09-18T00:52:40.289+00:00 (`1789692760.2893353`) | 133–225 | 2026-09-18T00:52:40.588+00:00 (`1789692760.587821`) | COMPLETE |
| 2 | 2 | 13 | s1 / LoRa-Chatter-1B44 | 2026-09-18T00:52:40.289+00:00 (`1789692760.2899477`) | 158–250 | 2026-09-18T00:52:41.570+00:00 (`1789692761.5692976`) | COMPLETE |
| 3 | 1 | 15 | s1 / LoRa-Chatter-1B44 | 2026-09-18T00:53:10.523+00:00 (`1789692790.523813`) | 253–345 | 2026-09-18T00:53:11.855+00:00 (`1789692791.8548205`) | COMPLETE |
| 3 | 2 | 16 | s2 / LoRa-Chatter-72E0 | 2026-09-18T00:53:10.524+00:00 (`1789692790.5244398`) | 253–345 | 2026-09-18T00:53:10.827+00:00 (`1789692790.8256347`) | COMPLETE |

Each response had the isolated `[SYS] CHATTER HELP` header, the matching node identity, the expected CHAT/TELEMETRY/HUMAN CONSOLE/RAW CONTROLS/ANDROID BLE TERMINAL sections, and the final `[SYS] BLE CLIENT: machine telemetry 0004 subscribed in background` line. No missing, truncated, mixed, or incomplete help shape was observed.

## Transport and session observations

- Six `/help` send outcomes: request IDs 9, 10, 12, 13, 15, and 16 all returned `queued` and their corresponding raw TX events were `tx_state: "written"`; no `unknown` outcome occurred.
- Forensic gap: no.
- Cursor expiry: no.
- Disconnect/reconnect during burst: no. The only `reconnecting` states were initial connection states before the stable `connected` states; no later disconnect/reconnect event was recorded.
- Same-node command overlap: no; each node's next `/help` was sent after its preceding response reached its final raw event.
- Final status before close: `s1` and `s2` both `connected`, `queued_tx=0`. Both sessions then closed via agent API and returned `state: "closed"`.

Raw BLE events are preserved separately in `artifacts/ble-events-s1-LoRa-Chatter-1B44.jsonl` and `artifacts/ble-events-s2-LoRa-Chatter-72E0.jsonl`. USB diagnostic counters were not interpreted.
