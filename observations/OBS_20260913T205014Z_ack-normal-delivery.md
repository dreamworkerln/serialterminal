# Node observation

Observed: 2026-09-13T20:50:14Z
Task: ack-normal-delivery
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@c9c6d4099c3532494bac8bfecb9fead37e27fe1e
Firmware: unknown

## Setup

- Dynamic discovery found two BLE LoRa-Chatter nodes: `LoRa-Chatter-1B44` and `LoRa-Chatter-72E0`.
- One SerialTerminal agent process held sessions `s1` and `s2` simultaneously.
- No firmware update, flashing, or node reboot was performed.

## Evidence

- Both sessions reached `connected`; `/id` returned the canonical identities above, and both nodes confirmed `/both`.
- A→B payload `FOCUSED A2B ACK-NORMAL 20260913 003`: sender USER identity `EC14/7`; physical `TX USER ... attempt=1/5`; `WAIT_ACK user=EC14/7`; peer `RX USER ... disposition=0` (NEW) and peer CHAT payload exactly once; matching `RX ACK ... ack_to=EC14/7`; `DELIVERY ACK ... attempts=1/5 ... queue=0`. No retry observed.
- B→A payload `FOCUSED B2A ACK-NORMAL 20260913 004`: sender USER identity `85BC/9`; physical `TX USER ... attempt=1/5`; `WAIT_ACK user=85BC/9`; peer `RX USER ... disposition=0` (NEW) and peer CHAT payload exactly once; matching `RX ACK ... ack_to=85BC/9`; `DELIVERY ACK ... attempts=1/5 ... queue=0`. No retry observed.
- Sender `>` and peer `< ...payload` each appeared once per direction. ACK/reliability details appeared in telemetry; no separate ACK CHAT message was generated.
- No spontaneous BLE disconnect/reconnect occurred after both sessions became connected. The initial open lifecycle was `reconnecting → connected` for each session.

## Final state

- Both nodes were returned to `/chat`; echo was not toggled and remained OFF.
- Final status for both sessions: `connected`, `queued_tx=0`; no pending retry or queue remained.
- Both sessions were closed and the agent process ended normally via EOF.

Run bundle: runs/RUN_20260913T205014Z_ack-normal-delivery/
