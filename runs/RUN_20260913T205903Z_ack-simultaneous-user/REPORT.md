# Focused reliable USER: simultaneous USER from both nodes

Observed: 2026-09-13T20:59:03Z  
Task: ack-simultaneous-user  
Result: PASS  
Firmware: unknown

## Setup

- SerialTerminal main repository was on `dev` at `5b98a61716b28d2b127370be94708890e59b5d21`.
- Dynamic discovery found BLE paths for `LoRa-Chatter-1B44` and `LoRa-Chatter-72E0`.
- One agent process opened s1 = `LoRa-Chatter-1B44` and s2 = `LoRa-Chatter-72E0`; both were connected and `/id` confirmed their canonical identities.
- Both nodes were set to `/both`. Before sending, `queued_tx=0` on both and telemetry showed idle state with no pending USER/retry.
- `send_line` for both USER payloads was issued in one consecutive JSONL batch; no artificial delay or RF interference was introduced.

## A_TO_B_SIM

- Payload: `A_TO_B_SIM_20260914_001`.
- Sender s1 logical USER identity: `EC14/9`; initial physical `TX USER seq=9 frame=35B user=23B attempt=1/5 OK`, followed by `WAIT_ACK user=EC14/9 attempt=1/5 queue=0`.
- Collision/recovery: sender reported `DELIVERY ACK TIMEOUT user=EC14/9 attempt=1/5`, then `DELIVERY RETRY user=EC14/9 next_attempt=2/5`; retry physical TX remained `seq=9`, frame/payload unchanged, and completed `attempt=2/5`.
- Peer s2 reported `RX USER session=EC14 seq=9 frame=35B user=23B ... disposition=0` (NEW), and CHAT showed `< [-34/+7 Q100] A_TO_B_SIM_20260914_001` exactly once.
- Peer sent matching ACK `ack_to=EC14/9`; sender reported `DELIVERY ACK user=EC14/9 attempts=2/5 elapsed=6495ms queue=0`.

## B_TO_A_SIM

- Payload: `B_TO_A_SIM_20260914_001`.
- Sender s2 logical USER identity: `85BC/10`; initial physical `TX USER seq=10 frame=35B user=23B attempt=1/5 OK`, followed by `WAIT_ACK user=85BC/10 attempt=1/5 queue=0`.
- Collision/recovery: sender reported `DELIVERY ACK TIMEOUT user=85BC/10 attempt=1/5`, `DELIVERY RETRY user=85BC/10 next_attempt=2/5`, and bounded `DELIVERY RETRY DEFER ... peer_rx=active`; retry physical TX remained `seq=10`, frame/payload unchanged, and completed `attempt=2/5`.
- Peer s1 reported `RX USER session=85BC seq=10 frame=35B user=23B ... disposition=0` (NEW), and CHAT showed `< [-33/+8 Q92] B_TO_A_SIM_20260914_001` exactly once.
- Peer sent matching ACK `ack_to=85BC/10`; sender reported `DELIVERY ACK user=85BC/10 attempts=2/5 elapsed=10191ms queue=0`.

## Acceptance and stability

- Both logical transactions delivered successfully within the configured five-attempt bound; no final failure, hang, unmatched ACK, or pending queue occurred.
- Retry recovery was observed for both transactions and preserved each logical identity and payload. No duplicate USER was received; duplicate suppression was therefore not exercised.
- Each sender printed one `>`; each peer printed one `< ...payload`; ACK/reliability internals were visible in telemetry and did not create a separate ACK CHAT message.
- No spontaneous BLE disconnect/reconnect occurred after sessions became connected. Only initial `reconnecting → connected` lifecycle transitions were present.

## Final state

- Both nodes were returned to `/chat`; echo was not toggled and remained OFF.
- Final status: both sessions `connected`, `queued_tx=0`; no WAIT_ACK/retry pending.
- Sessions were closed and the single agent process terminated normally via EOF.

Exact forensic and console logs are included. This run has a required matching observation because it validates the separate simultaneous reliable-delivery scenario.
