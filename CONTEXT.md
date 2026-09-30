# Current work context

Status: PAUSED / HANDOFF PUBLISHED

## Current operation

The active workstream is on `dev_tui`. The latest substantial implementation work
covers profile-aware TUI, Chatter BINARY USER, FT1 file transfer/reconnect repair,
filesystem picker, scrollback/usability and base64 redaction.

The immediate unfinished operation is a timing investigation into low file-transfer
chunk cadence. The operator runs two SerialTerminal processes from the same source
directory on one computer and supplied a current console trace showing redacted BINARY
lines mostly about 0.67-0.77 seconds apart.

No root-cause conclusion has been established.

## Exact baselines

```text
Active source:
  dreamworkerln/serialterminal/dev_tui@3360be0ba73b4be7693c43c94f482755bd2e0508
  GitHub Actions 36629183647 SUCCESS
  pytest 306 passed

Stable source baseline:
  dreamworkerln/serialterminal/dev@7cf0459c4e00a81592d447e0592e83a1142e18d9

Physical evidence authority:
  dreamworkerln/serialterminal/node_observations@4f66626663521fab98eb3b80ef4409719e9ec3a8

Firmware reference inspected read-only:
  dreamworkerln/lora-sack-protocol/dev_chat_binary@e08b3851c6ec506b12f607601a0b7e6cb1af618b

Latest recovery snapshot:
  HANDOFF_012.md
  snapshot commit b6dfe3749583c65f0227e6f4a6b0ab06e3221747
  snapshot blob a20dc91f39d8140b5c1c5ccabf03ef848a543a25
```

## Invariants / do not change

- Firmware repo is read-only from the SerialTerminal workstream.
- Generic session/transport code must not learn file/controller semantics.
- Do not add/remove arbitrary pacing delays until the timing path is evidenced.
- Do not infer that two ST processes sharing one cwd implies a process-global lock.
- Physical evidence belongs on `node_observations`, not source branches.
- Raw base64 stays hidden from human screen and redacted from persisted logs by default.

## Last completed action

`HANDOFF_012.md` was created on `dev_handoff` and read back successfully.

## Next action

Resume the file-transfer timing investigation:

1. refetch `dev_tui`;
2. inspect `file_transfer/core.py` sender loop;
3. inspect `file_transfer/transport.py` and Chatter `binary_user.py`;
4. inspect ManagedSession TX settlement and BLE write path;
5. correlate host write -> firmware DELIVERY WAIT_ACK/ACK -> next chunk;
6. check shared cwd paths/state for the two ST processes without assuming causality.

## Required validation

If a source fix is required, use focused commits, inspect deletions/function definitions,
run targeted tests and full CI. Physical timing/reconnect claims require separate
hardware evidence.

## Recovery order

1. current source `dev_tui:AGENTS.md`;
2. this `CONTEXT.md`;
3. `HANDOFF_INDEX.md`;
4. `HANDOFF_012.md`;
5. current `dev_tui` docs/source;
6. refetch moving source/evidence/firmware refs.
