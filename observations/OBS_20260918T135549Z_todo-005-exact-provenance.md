# Node observation

Observed: 2026-09-18T13:55:49Z
Task: TODO_005 exact-provenance bidirectional ACK confirmation
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@ab36ca2405f6cf8dd1a4ce572e96c8de918a754f
Firmware: dreamworkerln/lora-sack-protocol@a7eed47ecae5b21d8c7a72901e2d403c3329cd8e

## Setup

- Two physical Chatter nodes were each opened over USB and BLE with `profile=chatter`, paired by `/id`; host Bluetooth audio endpoint was not connected.
- Both physical nodes independently reported exact firmware provenance with `state=clean`, `env=esp32-s3-n16r8`; CHAT was active and ECHO was OFF.

## Actions

- Sent one unique USER A→B, waited for peer presentation and matching ACK, then sent one unique USER B→A and waited for the same evidence.

## Evidence

- `[SYS] FIRMWARE Chatter git=a7eed47ecae5b21d8c7a72901e2d403c3329cd8e state=clean env=esp32-s3-n16r8` was reported by both USB and BLE sessions.
- A→B `TODO005-A2B-20260918-1`: exactly one peer CHAT presentation and `DELIVERY ACK user=26DB/1 attempts=1/5`.
- B→A `TODO005-B2A-20260918-1`: exactly one peer CHAT presentation and `DELIVERY ACK user=CFEC/2 attempts=1/5`.
- No `DELIVERY FAILED`, unexpected reconnect, `send-outcome-unknown`, forensic gap, or cursor expiry was observed.

## Anomalies / conflicts

- none

## Final state

- Reliability state was settled with `/cancel all`, output restored to CHAT, and all sessions were closed.

Run bundle: runs/RUN_20260918T135549Z_todo-005-exact-provenance/
