# Handoff snapshot 001

```text
Snapshot: HANDOFF_001.md
Previous: none
Created: 2026-09-03T13:14:00Z
Handoff authority: dreamworkerln/serialterminal/dev_handoff@1e2f7632e7ea6d0cd20283ef713d811ca32dd178 (checkpoint before snapshot creation)
Source checkpoints:
  Active source: dreamworkerln/serialterminal/dev@1e2f7632e7ea6d0cd20283ef713d811ca32dd178
Knowledge base: dreamworkerln/serialterminal/dev@1e2f7632e7ea6d0cd20283ef713d811ca32dd178:README.md, AGENTS.md, source comments/tests
Transfer / promotion boundary: dev_handoff is recovery-only; source authority remains dev; no production/source changes belong on dev_handoff unless explicitly requested
```

This snapshot becomes immutable after publication through `HANDOFF_INDEX.md`.

## 1. Recovery / authority

- Active implementation authority is `dreamworkerln/serialterminal` branch `dev`.
- Authoritative handoff/recovery infrastructure for this workstream is the repository root on branch `dev_handoff`.
- Before code work or any statement about current implementation, refetch `dev`; this snapshot records historical state at the exact source SHA above and does not make a moving branch immutable.
- `HANDOFF_MANAGEMENT_POLICY.md` and `TODO_MANAGEMENT_POLICY.md` are present in both the recorded `dev` source checkpoint and the initial `dev_handoff` baseline. They were copied bit-for-bit from `dreamworkerln/lora-sack-protocol/dev_exp_sim_validation@a75aabb2f8eefdbe061bb9f9fb75b37ce586d5d4`.
- Policy source blobs at transfer time:
  - `HANDOFF_MANAGEMENT_POLICY.md`: `d133a4912f5a8f988e01de7717cf5f015c602ac5`
  - `TODO_MANAGEMENT_POLICY.md`: `c175d70073d9dc2b0c66ede9485d4ece8be3e050`
- No previous handoff snapshot/index existed in `serialterminal`; this is the initial numbered recovery checkpoint.
- TODO management policy is installed, but `TODO_INVENTORY.md` / `todos/` task records have not been initialized. Do not invent TODO IDs until actual task-management work requires them.
- No external Chatter firmware exact revision is claimed by this snapshot. Firmware-facing behavior below is the host contract documented/implemented in this source checkpoint; refetch the firmware repository separately before cross-repository validation.

## 2. Material state captured by this initial snapshot

This is the first handoff snapshot, so there is no previous snapshot delta. It captures the current accumulated host-side state:

- unified line-oriented terminal for USB Serial, BLE NUS and Classic Bluetooth SPP/RFCOMM;
- sticky reconnect to the same selected physical identity;
- reconnect-safe ordered outgoing command/payload queue;
- local Unicode line editing with complete-line transmit only after `Enter`;
- Chatter text commands and raw output/echo controls;
- Serial-only automatic `/id` request on each connect/reconnect before the user TX gate opens;
- BLE `0003` as the human-console stream and optional `0004` as background/transcript-only machine telemetry;
- firmware-owned RF-success presentation (`>`), with a separate bounded host pending-presentation tracker;
- aggressive Bluetooth capability scanner with capability cache;
- BLE scanner probes kept on one asyncio/BlueZ event loop and fresh BLE address resolution before each GATT connection;
- Classic SPP discovery restricted to explicit BR/EDR inquiry results instead of the mixed BlueZ device cache;
- serial discovery filtering that hides empty `/dev/ttyS*` placeholders while retaining identified legacy UARTs and USB serial devices;
- Linux Bluetooth disconnect diagnostics documented with `btmon` and system-package update guidance;
- project-level `AGENTS.md`, handoff policy and TODO policy now present.

## 3. Current implementation state

### Implemented

- Main launcher: `python3 serialterminal.py`.
- Default transcript: `serialterminal.log`.
- Package version at this checkpoint: `0.4.1`.
- Supported transports:
  - USB Serial via `pyserial`;
  - BLE NUS via `bleak`;
  - Classic Bluetooth SPP/RFCOMM on Linux.
- Stable reconnect identities:
  - Serial: `/dev/serial/by-id` first, then VID/PID + serial number, VID/PID + location, then concrete path;
  - BLE: BLE address;
  - SPP: Bluetooth address + confirmed RFCOMM channel.
- Normal BLE discovery keeps unrelated unknown BLE devices hidden unless they are project-name hints, advertise NUS, or have cached confirmed NUS capability.
- Aggressive scanner can probe all BLE for NUS and Classic BR/EDR devices for SPP.
- BLE compatibility boundary is RX `0002` + primary/human TX `0003`; telemetry `0004` is optional.
- BLE logical streams use independent incremental UTF-8 decoder state.
- BLE `0004` telemetry is logged but does not appear in the normal human console and cannot resolve pending USER/ECHO presentation outcomes.
- Chatter text commands recognized by the host:
  - `/help`
  - `/id`
  - `/chat`
  - `/tele`
  - `/both`
  - `/echo`
  - `/reboot`
- Device output/echo raw controls:
  - `Ctrl+T 1/c` -> bytes `14 31` -> CHAT;
  - `Ctrl+T 2/t` -> bytes `14 32` -> TELEMETRY;
  - `Ctrl+T 3/b` -> bytes `14 33` -> BOTH;
  - `Ctrl+T e` -> bytes `14 65` -> echo toggle.
- Local controls include device chooser, Bluetooth scanner, status and help.
- `Ctrl+T ?` prints local help and queues Chatter `/help`.
- Serial transport automatically sends `/id` directly after successful transport connection and before `connected_event`, preventing queued user traffic from overtaking identity request.
- Output/echo mode is not automatically restored after a Chatter reboot; firmware defaults remain authoritative after reboot.
- Host presentation is intentionally separate from the transport queue:
  - transport queue is reconnect-safe and effectively unbounded;
  - pending presentation queue is bounded at 4 payloads;
  - commands do not consume presentation slots.
- The host does not synthesize RF success. Firmware owns success lines such as `> hello` and `> [ECHO TX] hello`.
- If firmware rejects a sent payload before RF success, the host reveals the original local payload as plain text before preserving the firmware failure output.
- Sent-but-unresolved payloads are revealed as plain local lines when the result channel is lost.
- Prompt uses `prompt_toolkit` with `erase_when_done=True`; accepted interactive input is visible while editing but its committed local echo is erased. Transcript still retains the submitted line.
- Scanner/device chooser pause the active connection and resume the same sticky target afterward.
- Scanner menu numeric choices `1/2/3` use eager key bindings and do not require `Enter`.
- BLE scanner discovery + sequential GATT probes share one asyncio event loop; each probe resolves a fresh device by address and drains disconnect callbacks before the next probe.
- Classic discovery uses `bluetoothctl ... scan bredr` results only (with legacy `hcitool` fallback); a generic `bluetoothctl devices` list is deliberately not merged because it contains LE-only devices.
- Serial auto-discovery hides `/dev/ttyS*` entries with no meaningful description/HWID, but retains identified legacy serial hardware. Explicit manual serial paths remain usable.
- Serial no-reset handling remains best-effort around DTR/RTS and Linux `HUPCL` behavior.
- Bluetooth capability cache lives under `~/.cache/serialterminal/devices.json` or `$XDG_CACHE_HOME`.

### Explicitly not implemented / intentionally absent

- No host-generated RF-success `>` marker.
- No user-facing local `VIEW=CHAT/TELEMETRY/BOTH`; human-console routing is controlled by Chatter, while BLE `0004` is background data.
- No automatic reapplication of the last Chatter output/echo mode after device reboot.
- No telemetry collector/analytics subsystem beyond transcript retention.
- No heuristic association of firmware cumulative `INPUT QUEUE FULL dropped=N` telemetry with a specific host pending payload.
- `/reboot` is text-only; there is no new raw `0x14` reboot opcode/hotkey in the host.
- TODO inventory/task records are not initialized.
- This snapshot does not assert a cross-repository firmware revision or release state.

## 4. Architecture / invariants

Do not change these without an explicit design decision/task:

- Interactive transport input is line-oriented: edit locally, transmit only the complete line after `Enter`.
- Reconnect retries the same selected physical target; do not silently fall back to another visible device.
- Preserve ordered reconnect-safe outgoing traffic.
- Keep transport abstraction boundaries; UI behavior should not become unnecessarily transport-specific.
- Keep BLE primary/human and machine-telemetry streams logically separate, including decoder state.
- Background BLE `0004` must remain transcript-retained and must not resolve/reject human pending presentation state.
- Firmware is the authority for RF-success presentation. The host may reveal a submitted payload on failure/uncertain disconnect but must not fake success.
- Pending presentation state and transport retry state are distinct mechanisms.
- Pending presentation limit is currently 4 and intentionally mirrors the documented current firmware input-queue depth; it is a host UI safety bound, not a wire-protocol constant.
- Scanner must keep the normal terminal reconnect paused while probing.
- Aggressive BLE probing must not reuse stale `BLEDevice`/BlueZ object paths captured by the initial scan.
- Classic SPP discovery must not treat the generic BlueZ known-device list as proof of BR/EDR visibility.
- Unknown unrelated BLE devices remain hidden in normal discovery by default (`SHOW_ALL_BLE_DEVICES = False`).
- Empty kernel UART placeholders should not flood normal discovery, but meaningful legacy serial hardware and explicit user-selected paths remain supported.
- Preserve best-effort Serial no-reset behavior unless an explicit task changes it.
- Published `HANDOFF_NNN.md` files become immutable once `HANDOFF_INDEX.md` points to them.

## 5. Validation evidence

### Actually run / observed on the exact source checkpoint

GitHub Actions clean-environment validation for:

```text
dreamworkerln/serialterminal/dev@1e2f7632e7ea6d0cd20283ef713d811ca32dd178
workflow run: 33759411107
runner Python: 3.12
```

Completed successfully:

```text
pip install -e . pytest                         PASS
python -m compileall -q src serialterminal.py tools   PASS
pytest -q                                      PASS
```

The two final commits at this source checkpoint are documentation-only policy additions; the exact checkpoint itself has a successful CI run.

### Historical hardware/environment evidence carried forward

These are useful engineering observations, but they are **not** promoted to exact-current-head hardware validation:

- A laptop BLE connection to `LoRa-Chatter-1B44` (`44:1B:F6:8D:B7:A9`) previously showed repeated HCI `Disconnect Complete` with `Reason: Connection Timeout (0x08)`.
- Chatter telemetry counters/session progression continued across those laptop disconnects, strongly indicating the ESP32 was not rebooting during the observed drops.
- A phone running Kai Morich Serial Bluetooth Terminal was historically stable in sequential tests with the same Chatter device.
- Disabling `btusb` autosuspend did not eliminate the observed `0x08` timeouts.
- The user upgraded `bluez` and `linux-firmware`, and also moved to an Ubuntu HWE 6.8 kernel. After those system updates the BLE link appeared substantially more stable / possibly stopped dropping, but long-run confirmation remained observational rather than a closed validation gate.
- The LoRa transmitter used during debugging can operate around 1 W / 30 dBm. RF desense/front-end overload remains physically plausible but was not isolated as the cause.

### Still pending

- Live scanner regression check on the current code after the one-event-loop / BR/EDR-only fixes:
  - no `dbus-fast` `Future exception was never retrieved` / `BrokenPipeError`;
  - LoRa BLE-only target must not appear as a Classic/SPP candidate;
  - normal terminal reconnect remains paused for the entire scanner operation;
  - Chatter GATT connection during BLE scanner phase is attributable to the scanner probe, not the main reconnect loop;
  - immediate `1/2/3` scanner menu behavior remains clean in a real TTY.
- Hardware smoke test of the exact source checkpoint `1e2f7632...` across USB/BLE/SPP has not been recorded here.
- Continue long-run BLE stability observation after BlueZ/firmware/kernel updates; if a drop recurs, capture the HCI reason with `btmon`.
- Cross-repository compatibility validation against an exact Chatter firmware SHA remains unrecorded in this snapshot.

## 6. Findings / limitations / risks

- HCI `Connection Timeout (0x08)` is a link supervision timeout and is below the Python/Bleak application layer; historical evidence did not look like an intentional local application disconnect.
- The scanner previously created repeated asyncio loops around Bleak probes; the current implementation intentionally uses one loop to reduce BlueZ/dbus-fast lifecycle races. Live confirmation that this removes the observed `BrokenPipeError` remains pending.
- The scanner previously merged `bluetoothctl devices` into Classic discovery, causing LE-only targets such as LoRa-Chatter to receive pointless SDP probes. Current source restricts Classic candidates to explicit BR/EDR inquiry results.
- Initial BLE discovery objects can become stale BlueZ D-Bus paths while sequential probes run; current probe logic therefore resolves a fresh BLE device by address immediately before connection.
- Firmware telemetry `INPUT QUEUE FULL dropped=N` is cumulative and does not identify a specific submitted line. The host intentionally does not guess which pending line was dropped.
- System-package/kernel updates appear correlated with improved laptop BLE stability, but the individual responsible component was not isolated.
- High-power LoRa RF interaction with laptop radio front ends remains an unclosed hypothesis, not an established cause.

## 7. Knowledge references

At source checkpoint `dreamworkerln/serialterminal/dev@1e2f7632e7ea6d0cd20283ef713d811ca32dd178`:

- `README.md` — user-facing behavior, Chatter command/stream contract, presentation semantics, scanner behavior and Bluetooth diagnostics.
- `AGENTS.md` — repository working rules, transport/BLE invariants and validation expectations.
- `HANDOFF_MANAGEMENT_POLICY.md` — handoff publication/recovery rules.
- `TODO_MANAGEMENT_POLICY.md` — task-management rules (infrastructure installed; inventory not initialized).
- `src/serialterminal/terminal.py` — terminal lifecycle, reconnect, queueing, controls and integration of presentation state.
- `src/serialterminal/presentation.py` — firmware-owned success/pending presentation state machine.
- `src/serialterminal/ble_discovery.py` — safe/default BLE discovery and fresh-device NUS probing.
- `src/serialterminal/bluetooth_scanner.py` — aggressive BLE/SPP scanner and interactive scanner menu.
- `src/serialterminal/transports/serial.py` — serial identity/discovery and Serial transport behavior.
- `src/serialterminal/transports/ble_nus.py` — BLE NUS transport and stream handling.
- `src/serialterminal/transports/bluetooth_spp.py` — BR/EDR discovery, SDP/SPP probing and RFCOMM transport.
- `tests/` — automated regression coverage for presentation, background telemetry, BLE discovery/NUS, scanner, SPP, serial, terminal, identity and CLI behavior.
- `.github/workflows/ci.yml` — clean-environment compile + pytest gate.

Policy provenance source at transfer time:

```text
dreamworkerln/lora-sack-protocol/dev_exp_sim_validation@a75aabb2f8eefdbe061bb9f9fb75b37ce586d5d4
```

## 8. Transfer / promotion notes

- `dev_handoff` is a dedicated recovery/handoff branch. It is not source-code authority and should not receive production implementation edits by default.
- No whole-tree promotion or merge from `dev_handoff` to `dev` is part of this handoff.
- Source changes continue on `dev`; when `dev` moves materially, refetch it and create a new numbered snapshot rather than rewriting `HANDOFF_001.md` after publication.
- Policy-file updates should be intentional and provenance-recorded; do not silently drift the copied generic policies.

## 9. Immediate continuation

1. Refetch `dreamworkerln/serialterminal/dev` and confirm whether it still matches the recorded source checkpoint before any new code work.
2. Run a live `Ctrl+T s` -> all Bluetooth scanner test on current source and verify the pending scanner regression points listed above.
3. Continue observing Chatter BLE stability; if a disconnect recurs, use the documented `btmon` filter and record the HCI reason.
4. If future work becomes a substantial tracked engineering task, initialize `TODO_INVENTORY.md` / `todos/` according to `TODO_MANAGEMENT_POLICY.md` instead of creating ad-hoc checklist files.
5. When a new meaningful recovery checkpoint is reached, create and verify `HANDOFF_002.md` before advancing `HANDOFF_INDEX.md`.

## 10. Standing reminders

- Hardware validation and long-run BLE stability are separate from the green automated CI gate and remain open where stated above.
- Do not claim a new moving `dev` HEAD inherits hardware validation from an older checkpoint without re-checking relevance.
- Keep scanner/main reconnect ownership separate: the normal connection must stay paused while scanner probes devices.
- Keep `dev_handoff` recovery-only and `dev` as source authority.
- For every future snapshot: refetch exact source -> create snapshot -> read-back/verify -> only then advance index.
