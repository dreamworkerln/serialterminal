# Hardware run report

Task: focused hardware scenario `queue full -> explicit rejection` (take 2).
Result: INCONCLUSIVE.

## Revisions and setup

- SerialTerminal: `dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21`
- Firmware: `unknown`
- Sender: `LoRa-Chatter-1B44` (BLE `44:1B:F6:8D:B7:A9`, session `s1`)
- Powered-off peer: `LoRa-Chatter-72E0` (BLE `E0:72:A1:D5:4C:15`, session `s2`)
- Dynamic discovery found both canonical identities; both connected initially.
- Both nodes were set to `/both`; `/help` reported `current=BOTH echo=OFF`.
- Initial SerialTerminal status reported `queued_tx=0` for both sessions.

## Execution

The first payload was `QFULL_INFLIGHT_20260914T`. Exact sender protocol lines established `TX USER ... attempt=1/5` and `DELIVERY WAIT_ACK user=EC14/19 attempt=1/5 ... queue=0` (forensic log sequences 229–242).

The pending observe returned a telemetry burst and, before the first four waiting injections were transmitted, the sender progressed through retries to exact `DELIVERY FAILED user=EC14/19 attempts=5/5 ... queue=0` (sequences 247–374). The four waiting payloads were then accepted by the host input path too late; firmware later reported `INPUT QUEUE FULL dropped=3`, accepted only four waiting entries, and reached `waiting=4/8 in_flight=1` (sequences 415–442). It never reached `waiting=8/8`.

No overflow probe was sent because the required queue-full state was not proven. No exact `[SYS] SEND QUEUE FULL: message not accepted` outcome was observed.

For safe cleanup, `/cancel all` removed the remaining sender queue and reported `status=unknown queue_removed=4`; `/chat` was restored. Final sender status was connected with `queued_tx=0`. The peer remained powered off and its session was closed while reconnecting. Both sessions were closed and the single agent process exited with normal EOF.

## Verdict

This is an orchestration/timing miss, not firmware FAIL: the bounded first USER completed before firmware accepted the waiting injections. The requested queue-full contract remains untested.

Exact forensic and companion console logs are preserved without reconstruction.

Run bundle: runs/RUN_20260913T224731Z_ack-queue-full-take2/
