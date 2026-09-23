# Agent dual-session logging

Observed: 2026-09-23T11:56:00Z
Task: Physical validation of SerialTerminal forensic and companion console logging on two LoRa-Chatter nodes.
Result: PASS

## Revisions and setup

- SerialTerminal: `dreamworkerln/serialterminal@0db99efb5155ca0068d6dd3ecf6ed0f272537a10`
- Physical firmware: `dreamworkerln/lora-sack-protocol@608f1cd26d76a1b02d3401cbd17a9b4c9ab44716` (both nodes reported `state=clean` from `/version`)
- Nodes: `s1` = `LoRa-Chatter-1B44`; `s2` = `LoRa-Chatter-72E0`.
- Transport: BLE, profile `chatter`.
- One long-lived process was used for discovery, both opens, all commands/observes, closes, and termination:
  `python3 ../serialterminal/serialterminal.py agent --log /tmp/chatter-agent-dual-session-logging-20260923T115600Z.log`

## Actions and safe state

Both nodes were identified with `/id`. On both nodes, `/heartbeat off`, `/diag off`, `/echo-loop stop`, `/cancel all`, `/power 2`, and `/config` were executed and observed. The logging exercise then sent `/id`, `/version`, `/power`, and `/config` through `send_line` on both sessions and collected completed logical responses with `observe`. No special RF traffic was used. Both sessions were closed before the agent process terminated cleanly.

Final safe state on both nodes: power `2 dBm`, heartbeat `OFF`, diagnostic mode `OFF`, echo loop stopped, no pending delivery, configuration observed as `freq=470 MHz`, `sf=12`, `bw=125 kHz`, retry `ON`.

## Logging evidence

`serialterminal.log` and `serialterminal.console.log` were finalized by the same process and copied byte-for-byte into this RUN. The console log has 58 physical records: 29 for `s1`, 29 for `s2`; 22 `[I]` command records and 36 `[O]` completed logical response records. Every console line matches the contract `offset-aware ISO-8601 timestamp with milliseconds [s1]/[s2] [I]/[O]`, and lexical timestamp order is chronological. No `telemetry` or `SESSION` records appear in the console presentation view, so background telemetry did not multiply logical console records.

Concrete cross-checks:

- `send_line /id` appears as `[I] /id` for both sessions in `serialterminal.console.log`.
- Completed `[SYS] CHATTER NODE ...`, firmware, power, and config responses appear as `[O]` records for both sessions.
- The forensic log contains the agent ready record with both paths plus raw `TX` and `RX` records, including chunked RX evidence; it is therefore the forensic/API/transport view, while `.console.log` is the presentation/audit view. Byte-for-byte identity between the two files is not expected or required.

## Verdict

PASS. Both logging files were simultaneously created, populated, finalized, and conform to the requested multi-session companion logging contract.

Evidence:

- Forensic log: `runs/RUN_20260923T115600Z_agent-dual-session-logging/serialterminal.log`
- Console log: `runs/RUN_20260923T115600Z_agent-dual-session-logging/serialterminal.console.log`
