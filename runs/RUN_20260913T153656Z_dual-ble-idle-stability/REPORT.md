# Focused reproduction report: dual BLE idle stability

## Task

Determine whether SerialTerminal produces spontaneous BLE session disconnect/reconnect transitions when two physical LoRa-Chatter BLE nodes are open simultaneously in one agent process with no user traffic.

## Revision and setup

- SerialTerminal: `dreamworkerln/serialterminal@c9c6d4099c3532494bac8bfecb9fead37e27fe1e` (`dev`).
- One agent process, PID `266869`, sessions `s1` and `s2`.
- Dynamic BLE discovery found and opened two nodes.
- Canonical identities from `/id`: `s1` = `LoRa-Chatter-1B44`; `s2` = `LoRa-Chatter-72E0`.
- No reboot, reflash, `/both`, USER, or ECHO traffic.

## Idle window

- Start: `2026-09-13T18:33:26.627+03:00`, after final status confirmed both sessions connected.
- End: `2026-09-13T18:35:19.029+03:00`, after the required post-disconnect observation interval.
- Duration: `112.402 s` of idle observation; the first spontaneous disconnect occurred after `72.941 s`.
- Receive used only multi-session `observe` with returned cursors: `{s1:34,s2:34}` → `{s1:34,s2:37}` → `{s1:34,s2:59}` → `{s1:61,s2:59}` → `{s1:65,s2:84}` → `{s1:90,s2:84}`.

## Verdict: FAIL

Spontaneous BLE disconnect/reconnect reproduced on `s1` while both sessions were open and no manual traffic was sent.

Transitions during idle window, from forensic state events:

- `s1` `disconnected` at `2026-09-13T18:34:39.567+03:00`, event seq `60`.
- `s1` `reconnecting` at `2026-09-13T18:34:39.868+03:00`, event seq `61`.
- `s1` `connected` at `2026-09-13T18:34:52.245+03:00`, event seq `63`.
- `s2`: no `disconnected`, `reconnecting`, or reconnect `connected` transition during the idle window.

Initial session setup also recorded normal open transitions: `s1` reconnecting `18:32:36.192+03:00` → connected `18:32:41.768+03:00`; `s2` reconnecting `18:32:41.769+03:00` → connected `18:32:47.761+03:00`.

## Host TX and final status

The only manual host TX after opening was `/id` on each session at `18:33:07.645/646+03:00`. After those `/id` commands, there was no manual host TX. The only later TX was SerialTerminal's automatic `/id` connect preamble for `s1` at `18:34:52.245+03:00`, required by `auto_id=true` during reconnect. Final status before close: both `connected`, `queued_tx=0`; `s1` latest seq `90`, `s2` latest seq `109`.

## Shutdown behavior

Both sessions were closed explicitly (`18:36:17.127+03:00` and `18:36:19.113+03:00`). The agent process then received EOF and exited normally with code `0` at `18:36:28.436+03:00`. No Ctrl-C and no traceback occurred. Close-generated `state=closed` events are lifecycle cleanup, not part of the spontaneous BLE reproduction.

## Artifacts

- `serialterminal.log` is the exact forensic log from this process.
- `serialterminal.console.log` is the exact companion console log from this process.
- Matching focused observation: `observations/OBS_20260913T153656Z_dual-ble-idle-stability.md`.
