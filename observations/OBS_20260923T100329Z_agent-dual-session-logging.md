# Node observation

Observed: 2026-09-23T10:03:29Z
Task: Physical two-node validation of SerialTerminal agent logging contract
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@5b172ca0894ecf79ae3f714f4f832208f7e651db
Firmware: dreamworkerln/lora-sack-protocol@608f1cd26d76a1b02d3401cbd17a9b4c9ab44716

Run bundle: runs/RUN_20260923T100329Z_agent-dual-session-logging/

## Setup

One long-lived BLE SerialTerminal agent process opened `LoRa-Chatter-1B44` as `s1` and `LoRa-Chatter-72E0` as `s2`, both with `profile:"chatter"`.

## Actions

Confirmed `/id` and `/version`; applied `/heartbeat off`, `/diag off`, `/echo-loop stop`, `/cancel all`, `/power 2`, `/config`; sent `/id`, `/version`, `/power`, `/config` through `send_line` on both sessions; collected completed logical responses with `observe`; closed both sessions and terminated the same process.

## Evidence

The forensic log contains API and raw TX/RX evidence. The companion log contains both `[s1]` and `[s2]`, `[I]` command records, `[O]` completed logical firmware records, offset-aware ISO-8601 timestamps with milliseconds, and one logical record per physical line. Background telemetry was not replicated into the companion view.

## Anomalies / conflicts

None affecting the logging contract.

## Final state

Both nodes remained at power `2 dBm` with heartbeat and diagnostic mode OFF and echo loop stopped.
