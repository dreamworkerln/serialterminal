# Handoff index

This file is the mutable stable recovery entry point for the `serialterminal` workstream.

## Recovery order

1. Read applicable source operating instructions from current `dev_tui:AGENTS.md`.
2. Read `CONTEXT.md` on `dev_handoff`.
3. Read this `HANDOFF_INDEX.md`.
4. Read latest verified snapshot named below.
5. Read current `dev_tui` TODO/docs/source referenced by that snapshot.
6. Refetch actual moving source/evidence/firmware refs before new work.

## Snapshot rules

- `HANDOFF_NNN.md` snapshots are immutable after publication through this index.
- Create and read-back/verify a snapshot before advancing this index.
- Never replace historical exact SHAs with moving branch heads.
- `dev_handoff` is authoritative recovery state.
- `dev` is the stable source baseline.
- `dev_tui` is the active TUI/file-transfer source branch.
- `node_observations` is physical hardware executor/evidence authority.

## Current latest snapshot

```text
Snapshot: 012
File: HANDOFF_012.md
Snapshot publication checkpoint:
  dreamworkerln/serialterminal/dev_handoff@b6dfe3749583c65f0227e6f4a6b0ab06e3221747
Snapshot blob:
  a20dc91f39d8140b5c1c5ccabf03ef848a543a25
```

`HANDOFF_012.md` was created and read back before this index was advanced.

## Current source roles recorded by snapshot 012

```text
Stable SerialTerminal source baseline:
  dreamworkerln/serialterminal/dev@7cf0459c4e00a81592d447e0592e83a1142e18d9

Active TUI / BINARY USER / file-transfer work:
  dreamworkerln/serialterminal/dev_tui@3360be0ba73b4be7693c43c94f482755bd2e0508
  GitHub Actions 36629183647: SUCCESS
  pytest 306 passed

Physical observation evidence:
  dreamworkerln/serialterminal/node_observations@4f66626663521fab98eb3b80ef4409719e9ec3a8

Firmware reference inspected read-only:
  dreamworkerln/lora-sack-protocol/dev_chat_binary@e08b3851c6ec506b12f607601a0b7e6cb1af618b
```

Before new work, refetch moving refs; these SHAs are snapshot state.

## Current state summary

- `dev_tui` contains the active profile-aware curses TUI.
- Generic TUI has anchored scrollback, wrapping, command history, internal scrollbar,
  wheel support and F8 mouse-capture toggle.
- Chatter TUI has profile-owned radio/link status and directional
  `RX rssi/snr | TX rssi/snr | Q` header data.
- F5 opens a styled filesystem browser starting from process cwd; any ordinary file may
  be selected for transmission.
- Chatter BINARY USER adapter and FT1 file transfer are implemented.
- FT1 messages are META/DATA/END/MISSING/RESULT.
- Same-process missing-chunk repair selectively resends requested DATA and repeats END.
- No persistent resume after SerialTerminal process death/restart.
- Incoming files default to the SerialTerminal source-root `files` directory for
  checkout/editable installs.
- Human screen never renders raw Chatter BINARY base64.
- Persisted logs redact BINARY base64 to `<base64>` by default.
- `--log-base64` is explicit log-only forensic opt-in.
- Live agent event retrieval remains byte-accurate.
- Firmware was inspected only; SerialTerminal workstream did not modify it.
- Physical two-node file-transfer/reconnect validation is still open.

## Open operation

The current unfinished operation is the file-transfer timing investigation.

Operator context:

```text
two SerialTerminal processes
same computer
same source directory
observed BINARY chunk cadence mostly ~0.67-0.77 s
```

No root cause is accepted yet.

The supplied trace is chat evidence only and is not yet a canonical
`node_observations` run.

## Knowledge base

Active source/docs authority:

```text
dreamworkerln/serialterminal/dev_tui@3360be0ba73b4be7693c43c94f482755bd2e0508
```

Read as needed:

```text
AGENTS.md
ARCHITECTURE.md
AGENT_API.md
FILE_TRANSFER.md
LOGGING.md
README.md
TODO_INVENTORY.md
todos/TODO_029_FILE_TRANSFER_RECONNECT_REPAIR.md
.agents/skills/serialterminal-agent/SKILL.md
src/serialterminal/tui.py
src/serialterminal/file_browser.py
src/serialterminal/file_transfer/core.py
src/serialterminal/file_transfer/protocol.py
src/serialterminal/file_transfer/transport.py
src/serialterminal/profiles/chatter/binary_user.py
src/serialterminal/profiles/chatter/tui.py
src/serialterminal/session.py
```

## Immediate continuation

1. Refetch `dev_tui`.
2. Resume timing analysis before changing pacing.
3. Inspect FT1 sender loop for explicit waits/sleeps.
4. Inspect BINARY adapter settlement and ManagedSession/BLE write path.
5. Correlate host write, firmware DELIVERY WAIT_ACK/ACK and next chunk.
6. Check shared-cwd files/state between the two ST processes without assuming causality.
7. Separate host delay from firmware reliable-USER/radio turnaround.
8. If a source fix is required, use focused commits plus the documented acceptance gate.

## Standing reminders

- Authoritative recovery branch is `dev_handoff`.
- Active TUI/file-transfer source is `dev_tui`.
- Published snapshots remain immutable.
- GitHub Actions is source validation, not physical BLE/radio validation.
- Do not modify `node_observations` during ordinary source work.
- Do not modify firmware from the SerialTerminal workstream.
- Raw base64 remains hidden/redacted by default.
- FT1 same-process repair is not persistent resume.
