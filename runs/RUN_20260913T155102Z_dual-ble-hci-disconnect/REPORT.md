# Focused dual-BLE idle stability with HCI correlation

## Task and revision

Диагностика причины уже известного dual-BLE disconnect; это не LoRa/firmware test. SerialTerminal: `dreamworkerln/serialterminal@c9c6d4099c3532494bac8bfecb9fead37e27fe1e` (`dev`). Один agent process, PID `268004`.

## Sessions

- `s1`: `LoRa-Chatter-1B44`
- `s2`: `LoRa-Chatter-72E0`
- Both opened dynamically over BLE; `/id` confirmed both identities. No `/both`, reboot, reflash, USER or ECHO.

## Idle result: PASS

Idle window started at `2026-09-13T18:44:39.898+03:00`, after final status reported both sessions `connected` and `queued_tx=0`. It ended at final status `2026-09-13T18:50:20.924+03:00`: `341.026 s` total, exceeding the required 180 seconds.

Canonical multi-session `observe` was used throughout with returned cursors. No spontaneous SerialTerminal `disconnected`, `reconnecting`, or reconnect `connected` state event occurred for either session during the idle window. The only state transitions were initial open lifecycle and explicit close cleanup.

Final status before close: `s1 connected`, `s2 connected`, both `queued_tx=0`. Sessions were then closed and the agent exited through EOF with code `0`; no traceback occurred.

## Host TX boundary

Manual host TX after opening consisted only of `/id` on `s1` and `s2` at `2026-09-13T18:44:21.864–18:44:21.866+03:00`. No manual TX followed `/id`; no USER/ECHO traffic was sent. No reconnect occurred, so no automatic reconnect preamble was generated after `/id`.

## HCI and Bluetooth journal correlation

The requested external `btmon` was started by the human operator outside the sandbox, but `/tmp/dual-ble-repro.btsnoop` and the external `btmon` process were not visible from this execution environment after the run. Therefore no `btmon -r` decode was possible and no HCI handle, `Disconnection Complete`, reason code, controller error, or nearby LE connection event can be correlated.

Read-only journal query for `2026-09-13T18:44:00+03:00`–`18:51:00+03:00` returned `No entries`; no bluetoothd/kernel message evidence was available. HCI cause: **not established**. This limitation does not alter the SerialTerminal PASS verdict for the no-disconnect 341-second idle window.

## Artifacts

- `serialterminal.log`: exact forensic log from agent PID `268004`.
- `serialterminal.console.log`: exact companion console log from the same process.
- Matching observation: `observations/OBS_20260913T155102Z_dual-ble-hci-disconnect.md`.
