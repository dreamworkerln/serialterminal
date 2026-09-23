# Node observation

Observed: 2026-09-23T11:43:06Z
Task: Dual-session SerialTerminal agent logging on two LoRa-Chatter nodes
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@5b172ca0894ecf79ae3f714f4f832208f7e651db
Firmware: dreamworkerln/lora-sack-protocol@608f1cd26d76a1b02d3401cbd17a9b4c9ab44716

Run bundle: runs/RUN_20260923T114306Z_agent-dual-session-logging/

## Setup

One long-lived BLE `serialterminal agent` process opened `LoRa-Chatter-1B44` (`s1`) and `LoRa-Chatter-72E0` (`s2`) with `profile:"chatter"`. No flashing or special RF traffic was used.

## Actions

Confirmed `/id`; applied `/heartbeat off`, `/diag off`, `/echo-loop stop`, `/cancel all`, `/power 2`, `/config`; sent `/id`, `/version`, `/power`, `/config` through `send_line` on both sessions; collected completed logical responses with `observe`; closed both sessions and finalized the process.

## Evidence

Both exact companion files were created. The forensic `.log` contains API/request-response and raw TX/RX transport evidence. The `.console.log` contains both `[s1]` and `[s2]`, `[I]` command records, `[O]` completed logical firmware records, offset-aware ISO-8601 timestamps with milliseconds, one logical record per physical line, and chronological ordering. Background telemetry did not duplicate console records.

## Anomalies / conflicts

None affecting the logging contract. The forensic and console files intentionally differ in role and content; byte-for-byte identity is not expected.

## Final state

Both nodes: power 2 dBm, heartbeat OFF, diagnostic mode OFF, echo loop stopped, no pending delivery; sessions closed.

