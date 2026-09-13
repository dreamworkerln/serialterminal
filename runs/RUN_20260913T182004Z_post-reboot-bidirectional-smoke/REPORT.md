# Post-reboot two-node smoke

Observed: 2026-09-13T18:20:04Z  
Task: post-reboot-bidirectional-smoke  
Result: PASS

## Setup

- Host was post-reboot; Bluetooth audio was not connected to Linux.
- One SerialTerminal agent process held two simultaneous BLE sessions.
- Firmware nodes were not changed or rebooted.
- Dynamic discover found `LoRa-Chatter-1B44` and `LoRa-Chatter-72E0`.

## Actions and evidence

- `/id` established canonical identities for both sessions; both remained connected.
- Two idle multi-session observe intervals of approximately 25 seconds showed no spontaneous BLE disconnect/reconnect.
- In `/both`, A→B used `SMOKE A2B 20260913 001`: sender physical TX, peer USER, and matching `DELIVERY ACK` were observed; attempts `1/5`, queue `0`.
- B→A used `SMOKE B2A 20260913 002`: sender physical TX, peer USER, and matching `DELIVERY ACK` were observed; attempts `1/5`, queue `0`.
- Final status showed both sessions connected with `queued_tx=0`; both nodes were returned to `/chat`.
- Sessions were closed and the agent process terminated normally through EOF.

## Verdict

- A→B: PASS
- B→A: PASS
- BLE stability: PASS
- No new reusable finding; standalone observation was not required.

Exact forensic and console logs are included in this run bundle.
