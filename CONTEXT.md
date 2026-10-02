# Current work context

Status: PAUSED / HANDOFF PUBLISHED

## Current operation

The active source workstream is `dev_tui`.

The latest completed source work added deferred file-transfer timing instrumentation
and updated the generic agent skill so fast transfers are not throttled by per-chunk
LLM/tool orchestration.

The next unfinished operation is a manual BLE-vs-USB timing comparison using the new
`.fttiming.jsonl` trace. No throughput root-cause conclusion has been accepted.

## Exact baselines

```text
Active source:
  dreamworkerln/serialterminal/dev_tui@50c2536842aff60cd52f64e1031710cc5739d228
  GitHub Actions 36964002644 SUCCESS
  pytest 356 passed in 11.62 s

Stable source baseline:
  dreamworkerln/serialterminal/dev@7cf0459c4e00a81592d447e0592e83a1142e18d9

Physical evidence authority:
  dreamworkerln/serialterminal/node_observations@baf0214e1edf18179389580aa0ac56d0fcfaf76c

Firmware reference inspected read-only:
  dreamworkerln/lora-sack-protocol/dev_chat_binary@1cb43d9477b84269bc91003f89c0380f5c03b95f

Latest recovery snapshot:
  HANDOFF_013.md
  snapshot commit c8265900861a3262e87043ab9eee49c0060ab7ac
  snapshot blob b283b7153248d055a9e058c70647780a5d15b9e8
```

## Current implementation state

A normal TUI/agent run now produces:

```text
<name>.log
<name>.console.log
<name>.fttiming.jsonl
```

Timing events stay in memory while the run is active and are dumped only on clean
shutdown. Relevant events cover transport writes, BLE GATT writes/notifications,
BINARY submit/presentation/return, FT1 events and ordinary log-write durations.

The agent skill explicitly says not to chase every DATA chunk with
`file_transfer_observe`/model turns. Use coarse `status` snapshots about every
2–5 seconds and inspect finalized logs after the run.

## Invariants / do not change

- Firmware repo is read-only from the SerialTerminal workstream.
- Generic session/transport timing remains controller-agnostic.
- Chatter BINARY semantics stay profile-owned.
- Do not add/remove pacing delays before timing evidence.
- Do not add per-event disk writes to the timing trace.
- Do not use per-chunk model/tool orchestration for fast file transfer.
- Raw base64 remains hidden/redacted by default.
- Ctrl+C behavior remains ordinary quit semantics.

## Last completed action

`HANDOFF_013.md` was created on `dev_handoff` and read back successfully.

## Next action

1. refetch `dev_tui`;
2. manually send `3.jpg` over BLE from ordinary TUI;
3. close ST cleanly and preserve `.fttiming.jsonl`;
4. repeat over USB with the same file/radio settings;
5. compare targeted middle DATA chunks;
6. identify the dominant interval before changing source.

## Known related findings

- A successful USB diagnostic transfer completed 593/593 and remote RESULT OK.
- Per-chunk agent event-history following caused `file_cursor_expired` while the
  actual transfer still completed; this is an orchestration issue and the skill now
  warns against it.
- A separate stress attempt recorded both serial transports disconnected about 2.19 ms
  apart after about 9.28 s with no FT1 progress. The physical cause remains unknown.

## Required validation

The source checkpoint is CI-green. The new timing trace still needs physical manual BLE
and USB runs before any performance conclusion or pacing change is accepted.

## Recovery order

1. current source `dev_tui:AGENTS.md`;
2. this `CONTEXT.md`;
3. `HANDOFF_INDEX.md`;
4. `HANDOFF_013.md`;
5. current `dev_tui` docs/source;
6. refetch moving source/evidence/firmware refs.
