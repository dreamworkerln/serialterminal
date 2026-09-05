# Current work context

Status: IN PROGRESS

## Current operation

Publish handoff snapshot 005 for the accepted SerialTerminal agent observation/logging refactor.

No production source change is part of this handoff operation.

## Exact source state being captured

```text
SerialTerminal source/docs:
  dreamworkerln/serialterminal/dev@e6e74a45237abaf488cb815c2bba185810215c9d
  GitHub Actions run 33959407933 SUCCESS

Observation evidence:
  dreamworkerln/serialterminal/node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198

Handoff baseline before this publication:
  dreamworkerln/serialterminal/dev_handoff@afb7f5bf14d9f346086c05c3e009566644d64f54
```

## Recovery invariant during publication

`HANDOFF_INDEX.md` must remain on verified snapshot 004 until `HANDOFF_005.md` exists and has been read back/verified.

Older published snapshots remain immutable.

## Material state to capture

- `observe` is now the only machine receive/cursor operation; former `events` and `wait_events` operations are removed.
- One raw per-session cursor drives both `observe.result.events` and `observe.result.lines`.
- Logical LF-terminated lines are assembled canonically in `ManagedSession`, independently per stream, with UTF-8 split handling, CRLF normalization in the line view, empty-line preservation and `seq_first`/`seq_last` correlation.
- Raw transport/session events remain forensic source of truth and preserve chunk boundaries and `data_b64`.
- Agent runs now emit paired forensic and human-console logs: `serialterminal-...log` and `serialterminal-...console.log`.
- The forensic log no longer emits separate `[RX LINE ...]`/`[RX PARTIAL ...]` records.
- The companion console log records `send_line` as `[session] > ...` and completed human-console RX lines as `[session] < ...`; BLE machine telemetry is excluded unless equivalent text actually arrives through the human-console stream.
- `AGENT_API.md`, generic agent skill, node skill and README are synchronized with the new API/logging model.
- `TODO_004_NODE_RUN_BUNDLES` remains `DEFERRED`, but its stated dependency/return condition is now satisfied by `dev@e6e74a4...`; resumption is a separate task and must record this exact accepted dependency checkpoint before implementation.
- `node_observations` remains unchanged at `b024b43e...`; `REVIEW_STATE.md` is still unadvanced (`none`).

## Last completed action

Refetched `dev`, `dev_handoff` and `node_observations`; reviewed `AGENTS.md`, handoff policy, snapshot 004/index/context, current API/skills, TODO inventory/TODO_004 and exact CI state.

## Next action

1. refetch `dev_handoff` after this context commit;
2. create `HANDOFF_005.md` only;
3. read it back and verify provenance, current API/logging semantics, TODO/evidence state and validation;
4. only then advance `HANDOFF_INDEX.md` to 005;
5. finalize this `CONTEXT.md` as completed and verify final branch/CI state.

## Validation

The source checkpoint being captured already has GitHub Actions run `33959407933` = SUCCESS. No new hardware interaction is required or claimed for this handoff publication.