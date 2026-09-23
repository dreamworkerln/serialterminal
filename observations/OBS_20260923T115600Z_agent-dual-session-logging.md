# Node observation

Observed: 2026-09-23T11:56:00Z
Task: Dual-session SerialTerminal companion logging
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@0db99efb5155ca0068d6dd3ecf6ed0f272537a10
Firmware: dreamworkerln/lora-sack-protocol@608f1cd26d76a1b02d3401cbd17a9b4c9ab44716

Run bundle: runs/RUN_20260923T115600Z_agent-dual-session-logging/

## Setup

One long-lived BLE `serialterminal agent` process opened `LoRa-Chatter-1B44` (`s1`) and `LoRa-Chatter-72E0` (`s2`) with profile `chatter`.

## Actions

Confirmed `/id` and `/version`; applied `/heartbeat off`, `/diag off`, `/echo-loop stop`, `/cancel all`, `/power 2`, and `/config`; sent `/id`, `/version`, `/power`, and `/config` on both sessions; observed completed responses; closed both sessions.

## Evidence

The companion log contains both sessions, `[I]` command records, `[O]` completed logical firmware lines, offset-aware millisecond timestamps, one physical line per logical record, and chronological order. It contains no background telemetry records. The forensic log retains raw agent request/response and TX/RX evidence. This is a reusable confirmation of the TODO_026 logging contract.

## Anomalies / conflicts

None observed.

## Final state

Both nodes remained at power 2 dBm with heartbeat and diagnostic mode OFF, echo loop stopped, and no pending delivery.
