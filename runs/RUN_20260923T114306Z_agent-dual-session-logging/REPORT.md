# Agent dual-session logging

Observed: 2026-09-23T11:43:06Z
Task: CANONICAL_RUN physical validation of dual-session SerialTerminal agent logging.
Result: PASS

## Revisions and setup

- SerialTerminal runtime: `dreamworkerln/serialterminal@5b172ca0894ecf79ae3f714f4f832208f7e651db`.
- Physical firmware: `dreamworkerln/lora-sack-protocol@608f1cd26d76a1b02d3401cbd17a9b4c9ab44716` (both nodes reported `state=clean` from `/version`).
- Physical nodes: `LoRa-Chatter-1B44` (`s1`, BLE `44:1B:F6:8D:B7:A9`) and `LoRa-Chatter-72E0` (`s2`, BLE `E0:72:A1:D5:4C:15`).
- One long-lived process was used for discovery, both opens, all commands/observes, closes, and final log termination:
  `python3 ../serialterminal/serialterminal.py agent --log /tmp/chatter-agent-dual-session-logging-20260923T114006Z.log`
- Transport: BLE; both sessions opened with `profile:"chatter"`; no firmware flashing and no special RF traffic.

## Actions

Identity was confirmed with `/id` on both sessions. On both nodes the safety state sequence was run:
`/heartbeat off`, `/diag off`, `/echo-loop stop`, `/cancel all`, `/power 2`, `/config`.

The multi-session logging set was sent with `send_line` on both sessions: `/id`, `/version`, `/power`, `/config`. Corresponding completed logical responses were obtained with `observe`. Sessions were then closed before the same agent process was terminated.

## Evidence and logging-contract checks

- Both files were created and finalized by the same process. The forensic log is 132098 bytes / 300 physical lines; the companion console log is 4298 bytes / 58 physical lines.
- `serialterminal.console.log` contains records from both sessions: 29 `[s1]` and 29 `[s2]` records, with both `[I]` and `[O]` records.
- Commands are represented as `[I]`, including `/id`, `/version`, `/power`, and `/config` for both sessions.
- Completed firmware logical records are represented as `[O]`, including `[SYS] CHATTER NODE ...`, `[SYS] FIRMWARE ...`, `[SYS] POWER 2 dBm`, and `[SYS] CFG RADIO ...` for both sessions.
- Every console line has an offset-aware ISO-8601 timestamp with millisecond precision, e.g. `2026-09-23T14:41:57.451+03:00`; the timestamp sequence is chronological/monotonic.
- Each console record is one physical logfile line. Background telemetry was present in the forensic transport evidence but did not multiply console logical records; the console is a presentation/audit view.
- The primary `serialterminal.log` remains forensic/API/transport evidence: it contains agent requests/responses plus raw TX/RX records, including `send_line` request/response and the raw fragments underlying completed logical lines. The two logs are not expected to be byte-for-byte identical.
- Concrete cross-file correlation: forensic `send_line` `/id` request and TX records correspond to console `[I] /id`; forensic RX fragments for `CHATTER NODE LoRa-Chatter-1B44` and `LoRa-Chatter-72E0` correspond to console `[O] [SYS] CHATTER NODE ...`; `/config` raw RX fragments correspond to console `[O] [SYS] CFG RADIO power=2 dBm ...`.

The `/version` response on both nodes reported firmware git `608f1cd26d76a1b02d3401cbd17a9b4c9ab44716`, `state=clean`, image validation status `OK`, and the same image/build metadata. The exact source SHA is therefore recorded above; image/toolchain hashes are retained in the forensic evidence but are not substituted for the firmware SHA.

## Final safe state

Both nodes reported `POWER 2 dBm`, `heartbeat=OFF`, and `diag=OFF` in `/config`; echo loop was stopped and `/cancel all` completed with nothing pending. Both sessions were closed.

## Verdict

PASS — the real two-node, one-process run confirmed simultaneous creation and correct population of `serialterminal.log` and `serialterminal.console.log` under the stated logging contract.

