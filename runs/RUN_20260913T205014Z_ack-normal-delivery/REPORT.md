# Focused reliable USER: normal delivery

Observed: 2026-09-13T20:50:14Z  
Task: ack-normal-delivery  
Result: PASS  
Firmware: unknown

## Setup

- SerialTerminal main repository: `dev` at `c9c6d4099c3532494bac8bfecb9fead37e27fe1e`.
- Dynamic discovery found BLE paths for `LoRa-Chatter-1B44` and `LoRa-Chatter-72E0`.
- A single agent process opened two simultaneous sessions: s1 = LoRa-Chatter-1B44, s2 = LoRa-Chatter-72E0.
- No flashing, firmware change, or node reboot was performed.

## A→B

- Payload: `FOCUSED A2B ACK-NORMAL 20260913 003` (35 bytes).
- Sender s1 evidence: `TX USER seq=7 frame=47B user=35B attempt=1/5 OK`; `DELIVERY WAIT_ACK user=EC14/7 attempt=1/5 ... queue=0`; matching `RX ACK ... ack_to=EC14/7`; `DELIVERY ACK user=EC14/7 attempts=1/5 ... queue=0`.
- Peer s2 evidence: `RX USER session=EC14 seq=7 frame=47B user=35B ... disposition=0`; this is the NEW delivery, followed by exactly one peer CHAT `< [-36/+4 Q100] FOCUSED A2B ACK-NORMAL 20260913 003`.
- Physical attempts: `1/5`; retry: none; queue after delivery: `0`.

## B→A

- Payload: `FOCUSED B2A ACK-NORMAL 20260913 004` (35 bytes).
- Sender s2 evidence: `TX USER seq=9 frame=47B user=35B attempt=1/5 OK`; `DELIVERY WAIT_ACK user=85BC/9 attempt=1/5 ... queue=0`; matching `RX ACK ... ack_to=85BC/9`; `DELIVERY ACK user=85BC/9 attempts=1/5 ... queue=0`.
- Peer s1 evidence: `RX USER session=85BC seq=9 frame=47B user=35B ... disposition=0`; this is the NEW delivery, followed by exactly one peer CHAT `< [-34/+8 Q90] FOCUSED B2A ACK-NORMAL 20260913 004`.
- Physical attempts: `1/5`; retry: none; queue after delivery: `0`.

## Presentation and BLE

- Sender `>` appeared once for each USER. Peer `< ...payload` appeared once for each payload.
- Matching ACK/reliability internals appeared through telemetry and did not create a separate ACK CHAT message.
- No spontaneous BLE disconnect/reconnect occurred after both sessions reached connected. Initial session opening showed only the normal `reconnecting → connected` lifecycle for each target.

## Final state

- Both nodes were returned to `/chat`; echo was not toggled and remained OFF.
- Final status: both sessions connected with `queued_tx=0`; no pending retry or USER queue remained.
- Sessions were closed and the single agent process terminated normally through EOF.

The exact forensic and console logs are included in this bundle. The matching observation is published because this is a focused reliable-delivery validation scenario.
