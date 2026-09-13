# Node observation

Observed: 2026-09-13T20:59:03Z
Task: ack-simultaneous-user
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21
Firmware: unknown

## Setup

- Dynamic discovery found `LoRa-Chatter-1B44` and `LoRa-Chatter-72E0`.
- One SerialTerminal agent process held connected sessions `s1` and `s2`; both nodes were put in `/both`.
- Before the test both sessions reported `connected`, `queued_tx=0`, and idle telemetry; no pending USER/retry was present.
- The two USER sends were issued consecutively in one JSONL request batch without artificial delay.

## Evidence

- A payload `A_TO_B_SIM_20260914_001` used identity `EC14/9`. Both nodes initially transmitted at `attempt=1/5`; A received `DELIVERY ACK TIMEOUT`, then `DELIVERY RETRY user=EC14/9 next_attempt=2/5`. The retry used the same `seq=9`, identity and payload. B received `RX USER ... disposition=0` (NEW), displayed the payload once in CHAT, sent the matching ACK, and A completed `DELIVERY ACK user=EC14/9 attempts=2/5 queue=0`.
- B payload `B_TO_A_SIM_20260914_001` used identity `85BC/10`. Both nodes initially transmitted at `attempt=1/5`; B received `DELIVERY ACK TIMEOUT`, then `DELIVERY RETRY user=85BC/10 next_attempt=2/5` (with a bounded retry defer while peer RX was active). The retry used the same `seq=10`, identity and payload. A received `RX USER ... disposition=0` (NEW), displayed the payload once in CHAT, sent the matching ACK, and B completed `DELIVERY ACK user=85BC/10 attempts=2/5 queue=0`.
- No duplicate USER was observed, so duplicate suppression was not exercised; both peer receptions were NEW (`disposition=0`).
- Both senders showed one `>` for their original USER; each peer showed one `< ...payload`. Reliability internals were observed through telemetry, with no separate ACK CHAT message.
- No spontaneous BLE disconnect/reconnect occurred after both sessions reached connected. Initial opening lifecycle was `reconnecting → connected` for each target.

## Final state

- Both nodes were returned to `/chat`; echo was not toggled and remained OFF.
- Final status showed both sessions connected with `queued_tx=0`; no WAIT_ACK or retry remained.
- Sessions were closed and the agent process ended normally through EOF.

Run bundle: runs/RUN_20260913T205903Z_ack-simultaneous-user/
