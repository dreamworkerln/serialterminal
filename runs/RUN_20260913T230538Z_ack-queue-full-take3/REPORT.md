# Queue-full take3 hardware run

Observed: 2026-09-13T23:05:38Z
Task: queue full -> explicit rejection, take3
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21
Firmware: unknown

## Setup

- Dynamic discovery found two BLE Chatter nodes. Sessions were opened with explicit `profile: chatter` and `/id` confirmed `LoRa-Chatter-1B44` and `LoRa-Chatter-72E0`.
- Sender was `LoRa-Chatter-1B44`; peer was `LoRa-Chatter-72E0`.
- Both nodes were put in `/both`; help output confirmed `current=BOTH echo=OFF`.
- Peer was physically powered off before the in-flight stimulus and powered back on before completion.

## Actions and evidence

- In-flight payload: `QFULL3_INFLIGHT_20260914T`. Firmware evidence included `TX USER ... attempt=1/5` and `DELIVERY WAIT_ACK user=EC14/21 attempt=1/5 ... queue=0`.
- Nine requested `send_line` requests were submitted consecutively in one JSONL burst while an asynchronous observe was pending: 8 waiting payloads plus `QFULL3_REJECT_20260914T`.
- All 9 host requests returned `state=queued`; this is host TX acceptance only.
- Firmware accumulated evidence showed `INPUT QUEUE FULL dropped=8`, then only four reliable queue entries: `waiting=1/8`, `2/8`, `3/8`, and `4/8`, each with `in_flight=1`. No `waiting=8/8` was observed.
- No exact `[SYS] SEND QUEUE FULL: message not accepted` line was observed.
- The overflow payload had no observed logical USER identity, firmware `TX USER`, peer RX, or ACK. Its host transport write was recorded, which is not RF evidence.
- After peer restoration, the four accepted entries drained naturally. Final sender telemetry reported `Q=100% drops=8`; status checks after cleanup showed both sessions connected and `queued_tx=0`.

## Classification

INCONCLUSIVE per requested rule: the burst did not reach 8/8 before the first USER completed, and the run must not use `/cancel all` or artificial queue manipulation. This does not establish a firmware contract violation.

## Final state

- Peer restored: yes.
- Both nodes connected at final status check; output mode was returned to `/chat`; echo remained OFF.
- No `/cancel` command was used.
- Both sessions were closed and the single SerialTerminal agent process ended with normal EOF.

Exact forensic and console logs are stored beside this report.
