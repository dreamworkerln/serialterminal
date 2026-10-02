# Handoff index

This file is the mutable stable recovery entry point for the `serialterminal` workstream.

## Recovery order

1. Read applicable source operating instructions from current `dev_tui:AGENTS.md`.
2. Read `CONTEXT.md` on `dev_handoff`.
3. Read this `HANDOFF_INDEX.md`.
4. Read latest verified snapshot named below.
5. Read current `dev_tui` docs/source referenced by that snapshot.
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
Snapshot: 013
File: HANDOFF_013.md
Snapshot publication checkpoint:
  dreamworkerln/serialterminal/dev_handoff@c8265900861a3262e87043ab9eee49c0060ab7ac
Snapshot blob:
  b283b7153248d055a9e058c70647780a5d15b9e8
```

`HANDOFF_013.md` was created and read back before this index was advanced.

## Current source roles recorded by snapshot 013

```text
Stable SerialTerminal source baseline:
  dreamworkerln/serialterminal/dev@7cf0459c4e00a81592d447e0592e83a1142e18d9

Active TUI / BINARY USER / file-transfer work:
  dreamworkerln/serialterminal/dev_tui@50c2536842aff60cd52f64e1031710cc5739d228
  GitHub Actions 36964002644: SUCCESS
  pytest 356 passed in 11.62 s

Physical observation evidence:
  dreamworkerln/serialterminal/node_observations@baf0214e1edf18179389580aa0ac56d0fcfaf76c

Firmware reference inspected read-only:
  dreamworkerln/lora-sack-protocol/dev_chat_binary@1cb43d9477b84269bc91003f89c0380f5c03b95f
```

Before new work, refetch moving refs; these SHAs are snapshot state.

## Current state summary

- `dev_tui` contains the active profile-aware TUI, Chatter BINARY USER and FT1.
- File transfer is sequential at the local BINARY settlement boundary; no accepted
  artificial per-chunk sleep is present in the normal path.
- A deferred `<name>.fttiming.jsonl` companion trace is implemented for both TUI and
  agent runs.
- Timing events are collected in RAM with `perf_counter_ns()` and written only on
  clean close, keeping timing-file disk I/O out of the active transfer path.
- The timing trace covers transport/BLE write, BLE notify, BINARY submit/presentation/
  return, FT1 events and ordinary log-write start/done markers.
- Agent skill now forbids per-chunk model/tool orchestration for fast file transfers;
  use coarse `status` snapshots about every 2–5 seconds and post-run targeted log
  analysis.
- A successful USB diagnostic transfer completed 593/593 with remote RESULT OK.
- A separate fault attempt recorded both serial transports entering disconnected about
  2.19 ms apart after about 9.28 s without FT1 progress. Physical root cause remains
  unproven.
- Exclusive serial ownership prevents the separately proven case of two cooperating ST
  processes opening the same POSIX tty.
- Firmware remains read-only from this workstream.

## Open operation

The next operation is manual timing measurement with the new deferred trace.

Use ordinary TUI, send the same `3.jpg` first over BLE and then over USB, close ST
cleanly after each run, and compare middle DATA chunks. Do not change pacing or
protocol semantics before the timing evidence identifies the dominant delay.

## Knowledge base

Active source/docs authority:

```text
dreamworkerln/serialterminal/dev_tui@50c2536842aff60cd52f64e1031710cc5739d228
```

Read as needed:

```text
AGENTS.md
ARCHITECTURE.md
AGENT_API.md
FILE_TRANSFER.md
LOGGING.md
.agents/skills/serialterminal-agent/SKILL.md
src/serialterminal/timing.py
src/serialterminal/runlog.py
src/serialterminal/session.py
src/serialterminal/transports/base.py
src/serialterminal/transports/ble_nus.py
src/serialterminal/profiles/chatter/binary_user.py
src/serialterminal/file_transfer/core.py
src/serialterminal/terminal.py
src/serialterminal/tui.py
src/serialterminal/agent.py
```

## Immediate continuation

1. Refetch `dev_tui`.
2. Run one manual BLE transfer of `3.jpg`; exit cleanly and preserve
   `.fttiming.jsonl`.
3. Run equivalent USB transfer; exit cleanly and preserve its timing trace.
4. Analyze targeted 20–50 middle DATA chunks, not whole large forensic logs.
5. Compare write duration, write->notify, notification->presentation-match,
   presentation-match->return and return->next-submit.
6. Correlate ordinary log-write timing markers to see whether synchronous logging is
   material.
7. Only after measurement decide whether any throughput source change is justified.
8. Keep the dual-serial-disconnect root-cause investigation separate unless evidence
   connects it.

## Standing reminders

- Authoritative recovery branch is `dev_handoff`.
- Active TUI/file-transfer source is `dev_tui`.
- Published snapshots remain immutable.
- Deferred timing files require clean shutdown to be finalized.
- GitHub Actions is source validation, not physical BLE/radio validation.
- Do not modify `node_observations` during ordinary source work.
- Do not modify firmware from the SerialTerminal workstream.
- Do not reintroduce per-chunk LLM/tool file-transfer control loops.
- Raw base64 remains hidden/redacted by default.
- FT1 same-process repair is not persistent resume.
