# TUI main menu and baud selector TODO

TODO-ID: TODO_039
Status: OPEN
Related: `TODO_033_FT1_RESUMABLE_TRANSFER_AND_CONTROLLER_RECOVERY`, `TODO_038_FT1_REMOTE_PROGRESS_WATCHDOG`

## Purpose

Turn the current curses TUI from a mostly-hotkey-driven interface into a discoverable menu-driven terminal in the spirit of Midnight Commander, while keeping existing function-key shortcuts available for experienced users.

The primary user-facing rule should become:

```text
all ordinary interactive TUI functions are discoverable from F9 Main Menu
function keys and legacy Ctrl+T sequences are shortcuts, not the only way to find features
```

The first concrete configuration item that must use this framework is serial baud-rate selection.

## Current behavior / finding checkpoint

Finding checkpoint:

```text
SerialTerminal dev_tui@268710b97660eeb073dc94390eda7b3e531ff0b3
```

At that checkpoint the curses TUI exposes direct function keys such as:

```text
F2 Device
F3 Profile
F4 Clear
F5 Send file
F6 Cancel
F8 Mouse
F9 Help
```

The legacy/classic human frontend separately has a `Ctrl+T` prefix command layer, including global controls and Chatter-specific output-mode controls. The curses TUI does not currently provide an equivalent discoverable command menu.

At the same checkpoint serial baud was temporarily changed globally to `921600` in multiple places (`SerialTransport`, `DeviceSelector`, serial CLI default and unified-auto CLI default). That global default is useful for the current Chatter/firmware speed work but is not the desired long-term policy.

## UI direction

### F9 opens the main menu

Reassign curses TUI `F9` from direct Help to **Main Menu**.

Do not use F10 as the primary menu key. Desktop terminals such as GNOME Terminal commonly reserve or intercept F10; the TUI should not require the user to reconfigure the terminal emulator for basic application navigation.

Target interaction:

```text
F9
  -> top-level menu bar / dropdown menu
  -> arrow-key navigation
  -> Enter activates
  -> Esc closes without side effects
```

The terminal output should remain visible behind/around the menu. This is a TUI overlay/menu system, not a separate full-screen configuration application.

### Initial menu organization

Exact wording may be refined during implementation, but the first version should expose the existing actions through a structure equivalent to:

```text
Device
    Select device...
    Reconnect
    Scanner...

Connection
    Status
    Transport information
    Baud rate...

Profile
    Generic
    Chatter

Transfer
    Send file...
    Cancel transfer

View
    Clear screen
    Mouse capture
    Follow tail
    Logs / log paths

Help
    Help
    Hotkeys
    About / version information if already available
```

Profile-specific actions may be added in a clearly owned section/submenu rather than hidden behind undocumented keystrokes.

For Chatter, output-mode actions such as CHAT / TELEMETRY / BOTH and echo control should remain accessible. The implementation may expose them through a profile-specific submenu rather than duplicating arbitrary global menu entries.

## One action model, multiple entry points

Do not implement menu commands as a second set of independent behavior paths.

Refactor/organize TUI actions so that:

```text
F2 shortcut
F9 -> Device -> Select device...
```

invoke the same underlying action.

Likewise:

```text
F5 shortcut
F9 -> Transfer -> Send file...
```

must have identical preemption, cancellation, reconnect and error behavior.

The menu is a discoverability/navigation layer over canonical actions, not a parallel implementation.

Existing Fx keys should continue to work unless a specific key is intentionally reassigned by this TODO.

Required reassignment:

```text
F9: Help -> Main Menu
```

Help remains reachable from the menu and may retain a secondary shortcut if useful.

## Footer / discoverability

The footer should stop trying to enumerate every possible operation once the menu exists.

A compact form equivalent to this is preferred:

```text
F2 Device | F5 Send | F8 Mouse | F9 Menu | Ctrl+Q Quit
```

The exact compact shortcuts may vary by profile/capability, but `F9 Menu` must be visible so a first-time user can discover the rest of the application without knowing hotkeys.

## Baud-rate policy

Baud-rate handling is part of this TODO because it is the first important runtime configuration that should be available through the menu.

### CLI explicit override wins

Existing CLI parameter remains supported:

```text
-b BAUD
--baud BAUD
```

If the user explicitly specifies `-b/--baud`, that value is authoritative for initial serial transport creation.

A profile must not silently replace an explicitly supplied baud rate.

Examples:

```text
--profile chatter -b 115200
    -> 115200

--profile generic -b 921600
    -> 921600
```

### Profile-aware default when `-b` is omitted

The parser/default architecture must distinguish:

```text
baud explicitly supplied
```

from:

```text
baud omitted; choose policy default after profile resolution
```

Preferred policy:

```text
profile=chatter
    -> default serial baud 921600

profile=generic/default
    -> default serial baud 115200
```

Do not keep one global `921600` default merely because the current Chatter firmware uses that rate.

The current duplicated defaults in transport/selector/parsers should be replaced by one clear baud-policy source or resolver so the effective default cannot drift between startup paths.

The CLI parser may use `None` for an omitted baud and resolve the actual baud after the profile is known.

### Unified auto mode

The same policy applies to unified `auto` startup.

If the selected transport is Serial, its baud is the resolved explicit/profile value.

If the selected transport is BLE or Bluetooth SPP, UART baud is not applicable to that connection and must not create misleading UI state.

## Runtime baud selector

`F9 -> Connection -> Baud rate...` opens a selector for Serial transport.

Initial useful set should include common rates equivalent to:

```text
9600
19200
38400
57600
115200
230400
460800
921600
1000000
Custom...
```

The exact preset list may be refined, but `115200`, `230400`, `460800`, and `921600` must be easy to select.

The currently active baud should be visibly marked.

`Custom...` should allow a positive integer baud with validation rather than requiring a source-code change for an uncommon controller.

## Runtime baud change lifecycle

Changing baud on an already-open serial connection is an operator-owned connection change.

Do not mutate the underlying pyserial baud setting in-place while the existing session/RX/TX ownership remains ambiguous.

Preferred lifecycle:

```text
operator selects new baud
-> settle / conservatively handle current local TX ownership
-> disconnect/replace the current Serial transport/session as required
-> retain the same selected physical serial identity
-> reconnect at the new baud
-> update header/status to show the effective baud
```

Reuse the existing TUI session-replacement/device identity machinery where safe rather than creating an independent reconnect stack.

If a file transfer is active, changing baud must follow the same explicit operator-preemption rules as other manual device/profile changes. It must not silently migrate an active FT1 transfer to a new serial configuration while queued writes remain ambiguous.

Exact UX should state that the transfer was cancelled/preempted if that is the selected current TUI ownership contract.

## Non-Serial transports

Baud rate is a Serial/UART property.

For BLE or native Bluetooth SPP contexts where this application cannot meaningfully change a UART baud, the menu entry should be either:

```text
disabled and visibly marked as serial-only
```

or activate a clear status explanation such as:

```text
Baud rate applies to serial transport only
```

Do not hide the concept in a way that makes users wonder why the option disappeared between transports.

## Profile switching and baud policy

Profile-aware baud defaults are startup/default policy, not an unconditional runtime command.

When a user explicitly changes baud at runtime, the application must avoid surprising automatic replacement of that operator selection merely because another UI action occurs.

Implementation must define and test the precedence/lifetime of:

```text
explicit CLI baud
runtime menu-selected baud
profile default baud
```

Preferred mental model:

```text
operator explicit choice > profile default
```

When switching profiles, do not silently change an explicitly selected baud unless the UI clearly offers/requests that behavior.

If implementation chooses to treat a profile switch as restoring that profile's default baud, this must be an explicit visible contract and requires user confirmation. Silent profile-switch baud mutation is not preferred.

## Legacy Ctrl+T controls

The existing classic frontend `Ctrl+T <key>` command prefix may remain for backward compatibility and power users.

This TODO does not require users of the curses TUI to learn or use the prefix scheme.

Do not consume common terminal editing controls such as direct `Ctrl+K`, `Ctrl+U`, etc. merely to expose application settings.

If some `Ctrl+T` shortcuts are later shared with the TUI, they should call the same canonical actions exposed by F9 rather than create another behavior implementation.

## Mouse behavior

The existing default terminal-owned mouse mode (selection/RMB available immediately; F8 toggles internal curses mouse capture) must remain intact.

Opening/navigating F9 menus must not permanently alter mouse capture state.

Mouse support for clicking menus is optional for the first implementation; keyboard operation is mandatory.

## Minimum keyboard behavior

Mandatory menu navigation:

```text
F9         open main menu
Left/Right move between top-level sections
Up/Down    move within a menu
Enter      activate selected item
Esc        close submenu/menu without action
```

Reasonable first-letter accelerators may be added, but must not be required for basic operation.

Menu navigation keys must not leak into the terminal input buffer or be sent to the connected device.

## State/capability-aware menu items

The menu should reflect what is actually possible in the current context.

Examples:

```text
Cancel transfer
    disabled when no active transfer exists

Baud rate...
    serial-only

Send file...
    disabled or explained when the selected profile does not support FT1

Chatter output mode
    only meaningful for chatter profile
```

Prefer visible disabled items or explicit explanatory status over silently accepting no-op actions.

## Testing requirements

Add deterministic tests for at least:

### Menu model/navigation

- F9 opens the main menu.
- F9 no longer directly emits Help.
- Left/Right switch top-level menus.
- Up/Down select items.
- Enter invokes exactly one canonical action.
- Esc closes without invoking an action.
- Menu keystrokes do not become terminal input.
- Existing F2/F3/F4/F5/F6/F8 shortcuts keep their established behavior unless explicitly changed.

### Action sharing

- `F2` and `Device -> Select` reach the same device action contract.
- `F5` and `Transfer -> Send file` reach the same file chooser/start contract.
- Help remains reachable after F9 reassignment.

### Baud startup policy

- generic with no `-b` -> 115200.
- chatter with no `-b` -> 921600.
- chatter with explicit `-b 115200` -> 115200.
- generic with explicit `-b 921600` -> 921600.
- serial and unified-auto startup use the same resolver.
- no duplicated conflicting parser/selector/transport policy defaults remain on the normal startup path.

### Baud runtime behavior

- Serial baud menu marks the current value.
- preset selection recreates/reconnects the same serial identity at the new baud.
- Custom rejects zero/negative/non-numeric values.
- BLE/non-applicable transport cannot accidentally mutate a serial baud configuration.
- active FT1 follows explicit operator-preemption semantics on baud change.
- header/status reflects the effective new serial baud after reconnect.

### Profile interaction

- switching to Chatter with no explicit/operator baud context gets the intended 921600 default where policy resolution occurs.
- switching profile does not unexpectedly overwrite an explicit operator baud choice.

## Manual validation

After automated tests/CI, run a small interactive TUI matrix:

```text
1. generic + USB serial -> starts at 115200 without -b
2. chatter + USB serial -> starts at 921600 without -b
3. chatter -b 115200 -> stays at 115200
4. F9 -> Connection -> Baud rate -> 460800 -> same physical device reconnects
5. change back to 921600
6. F9 -> Device / Profile / Transfer / View / Help actions are discoverable
7. F2/F5/F8 shortcuts still work
8. F10 is not required
9. ordinary terminal RMB/selection remains available in default mouse mode
```

When physical Chatter firmware is expected to run at 921600, validate a real `/id`/help or equivalent normal interaction after menu-driven reconnect so a visually successful reconnect cannot mask a baud mismatch.

## Non-goals

This TODO does not require:

- replacing the curses TUI with a new GUI framework;
- removing all keyboard shortcuts;
- changing firmware UART configuration;
- changing BLE transport scheduling;
- implementing TODO_038 FT1 progress watchdog;
- making F10 usable in terminal emulators that reserve it;
- forcing the classic frontend to adopt the curses menu UI.

## Implementation order

Recommended order:

1. inspect the final baud-rate changes made by the ongoing firmware/speed work and establish an accepted base SHA;
2. centralize explicit/profile-aware baud resolution without changing unrelated transports;
3. introduce canonical TUI action methods/model so shortcuts and menus share behavior;
4. implement F9 menu state/render/navigation;
5. move Help behind the menu while retaining a useful shortcut/help action;
6. add Connection -> Baud rate selector and safe same-device reconnect;
7. capability-disable baud for non-Serial transports;
8. update footer/help documentation;
9. targeted tests;
10. BASE..HEAD deletion/function-definition review where meaningful;
11. full CI;
12. interactive serial/chatter validation.

## Acceptance

TODO_039 may be marked implemented only when:

```text
F9 is the discoverable main entry point for TUI commands
existing shortcut actions and menu actions share one behavior implementation
F10 is not required
baud is selectable from the TUI menu for Serial
-b/--baud explicit override remains supported
generic omitted-baud default is 115200
chatter omitted-baud default is 921600
runtime baud reconnect preserves the selected physical serial identity
non-Serial transports handle baud selection truthfully
existing file-transfer/operator-preemption rules are not bypassed
automated tests and CI pass
```

Physical validation status must remain explicit; do not infer real-device baud correctness solely from host-side unit tests.
