# SerialTerminal radio interface smoke report

Observed: 2026-09-14T23:51:31Z
Task: проверить, работает ли перепиленный SerialTerminal/agent-интерфейс для работы с LoRa-Chatter radio и насколько инструкции соответствуют фактическому поведению.
Result: INCONCLUSIVE

## Revisions and setup

- SerialTerminal: `dreamworkerln/serialterminal@159f7a1ab52fb8f615af33b175545f13e04dd989`
- Firmware: unknown
- Physical setup: two discovered BLE LoRa-Chatter nodes, opened as two long-lived agent sessions with explicit `profile:"chatter"`.
- Returned streams for both sessions: `chat`, `telemetry`.

## Executed checks

- `discover(scope:auto)` and `discover(scope:ble)` returned both available BLE device keys.
- Both `open` requests succeeded with `state:"connected"`; Chatter connect preamble produced node identity output.
- `/help` and `/id` were accepted. A fresh single-session `/help` produced complete logical lines, including the documented command set and BLE `0004` telemetry explanation.
- `/tele`, `/both`, and `/chat` changed output mode and produced the expected human-console acknowledgements. The separate `telemetry` stream remained available.
- `s1 -> s2`: unique USER `st-radio-check-a1`; peer CHAT showed it once, telemetry showed `RX USER`, sender showed matching `RX ACK` and `DELIVERY ACK`, attempt `1/5`.
- `s2 -> s1`: unique USER `st-radio-check-b2`; peer CHAT showed it once, telemetry showed `RX USER`, sender showed matching `RX ACK` and `DELIVERY ACK`, attempt `1/5`.
- Sessions were closed and the agent process exited cleanly. Final output mode was restored to `CHAT`; ECHO was left `OFF`.

## Findings

1. Core agent workflow is usable for live radio work: discovery, explicit profile selection, independent BLE chat/telemetry streams, logical-line observation, and confirmed bidirectional reliable USER delivery all worked.
2. A burst of `/help` and `/id` sent to both sessions produced incomplete/misassembled human-console lines on `s1`: the help tail stopped at `machine telemetry=00`, and a later USER appeared in one logical line as `[SYS] ... machine telemetry=00> st-radio-check-a1`. The same `/help` command on a fresh session, sent alone after the initial observation, was complete. This is a reproducible burst/timing anomaly candidate, but this run does not isolate whether the loss is firmware/BLE notification handling or SerialTerminal presentation/line assembly.
3. The `/help` text itself matches the current project-specific instructions for commands, output modes, raw controls, and BLE streams. The human console log is not sufficient as delivery evidence; telemetry/application lines are required, consistent with the skill.
4. One observation request in the exploratory burst intentionally reused an old cursor and returned already-seen events. This was executor misuse, not a product failure; the canonical workflow requires continuing from returned cursors.

## Limitations

- No deterministic fault injection was performed, so retry/lost USER, lost ACK, cancellation, queue-full, wrong ACK, and peer-off scenarios remain untested.
- No USB transport or human PTY/UI hotkey path was tested.
- No firmware source SHA was available in this workspace.
- Hardware was available and used for this run; no flashing, reboot, or destructive action was performed.

## Evidence

- `serialterminal.log` is the exact forensic log from the main two-node run.
- `serialterminal.console.log` is its exact companion human-console log.
- The isolated follow-up `/help` run is retained in `/tmp` only and is not part of this published bundle.
