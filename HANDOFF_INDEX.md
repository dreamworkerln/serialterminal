# Handoff index

This file is the mutable stable recovery entry point for the `serialterminal` workstream.

## Recovery order

1. Applicable repository/workstream operating instructions (`AGENTS.md`).
2. `CONTEXT.md`, if present and relevant.
3. `HANDOFF_INDEX.md`.
4. Latest verified snapshot named below.
5. Project knowledge/docs/evidence referenced by that snapshot.
6. Refetch the actual moving source/evidence refs before current work.

## Snapshot rules

- `HANDOFF_NNN.md` snapshots are immutable after publication through this index.
- Create and read-back/verify a new snapshot before advancing this index.
- Never replace historical exact SHAs with moving branch heads.
- `dev_handoff` is handoff/recovery authority; `dev` remains source/docs authority.

## Current latest snapshot

```text
Snapshot: 005
File: HANDOFF_005.md
Snapshot verified file checkpoint: dreamworkerln/serialterminal/dev_handoff@d85d962db5ca8157dd3a53f047bf10abece95fe3
Snapshot blob: 4ed8464e8a479d6f26d9841b41857ae0a0097a5d
```

`HANDOFF_005.md` was created and read back before this index was advanced. `HANDOFF_001.md` through `HANDOFF_004.md` remain immutable historical snapshots.

## Current source roles recorded by snapshot 005

```text
SerialTerminal source/docs:
  dreamworkerln/serialterminal/dev@e6e74a45237abaf488cb815c2bba185810215c9d
  GitHub Actions run 33959407933: SUCCESS

Node observation evidence:
  dreamworkerln/serialterminal/node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198

Snapshot 005 pre-creation handoff checkpoint:
  dreamworkerln/serialterminal/dev_handoff@20893774c60171d6d27d61f42031dcd67aae7951
```

Before new work, refetch moving `dev` and any relevant evidence/protocol refs; the SHAs above are snapshot state.

## Current state summary

- `observe` is now the only generic machine receive/cursor operation. Former `events` and `wait_events` operations are removed and return `unknown_operation` through normal dispatch.
- One raw per-session cursor drives both `observe.result.events` and `observe.result.lines`.
- Raw events remain forensic source of truth with actual transport/session chunk boundaries and `data_b64`.
- Completed LF-terminated logical lines are assembled once in `ManagedSession`, independently per stream, with `seq_first`/`seq_last` correlation; callers should not manually rebuild lines already present in `result.lines`.
- Agent runs now produce paired forensic and human-console logs: `serialterminal-...log` and `serialterminal-...console.log`.
- The main forensic log no longer emits separate `[RX LINE ...]` / `[RX PARTIAL ...]` records.
- Companion `.console.log` records `send_line` as `[session] > ...` and completed human-console RX lines as `[session] < ...`; separate BLE machine telemetry is excluded unless equivalent output actually arrives through the human-console stream.
- `AGENT_API.md`, generic skill, node skill and README are synchronized with the accepted `observe`/line/logging model.
- `TODO_004 — Automated node run bundles` is present in the active inventory with status `DEFERRED`. Its stated dependency/return condition is now satisfied by `dev@e6e74a4...`, but the TODO has not been resumed by this handoff.
- `node_observations` remains at `b024b43e...`; `REVIEW_STATE.md` is still unadvanced (`none`).
- Chatter USER/ECHO guidance still uses `1..200` UTF-8 bytes, while generic SerialTerminal intentionally does not hard-code that firmware/application limit.
- `queued`, `written`, local TX markers and console-log presentation remain insufficient as peer/application delivery proof.

## Knowledge base

Primary current SerialTerminal docs/source at the recorded `dev` checkpoint:

```text
AGENTS.md
AGENT_API.md
.agents/skills/serialterminal-agent/SKILL.md
.agents/skills/node-agent/SKILL.md
TODO_INVENTORY.md
todos/TODO_004_NODE_RUN_BUNDLES.md
NODE_OBSERVATION_RECORDING_POLICY.md
NODE_SKILL_LEARNING_POLICY.md
src/serialterminal/session.py
src/serialterminal/agent.py
src/serialterminal/runlog.py
related tests / CI configuration
```

Evidence state at the recorded `node_observations` checkpoint:

```text
REVIEW_STATE.md
observations/OBS_20260904T075106Z_max-text-payload.md
observations/OBS_20260904T085207Z_oversized-payload.md
observations/OBS_20260904T134143Z_empty-and-size-speed.md
```

Firmware/protocol implementation truth remains the actual relevant `lora-sack-protocol` source/docs revision; snapshot 005 does not invent an exact firmware SHA that was not established.

## Immediate continuation

1. Refetch `dev` before source/docs changes.
2. Use `observe` as the canonical receive workflow; use `result.lines` for completed firmware-line reasoning and `result.events` for raw/chunk/byte forensics.
3. Preserve the one-assembler boundary: transport keeps raw chunks; session layer assembles logical lines; logging does not create a second assembler.
4. If resuming TODO_004, first record the exact accepted dependency checkpoint, then implement bundle publication without redesigning `observe` or reconstructing the console log.
5. For hardware execution, follow `NODE_OBSERVATION_RECORDING_POLICY.md`; for observation review/promotion, separately follow `NODE_SKILL_LEARNING_POLICY.md`.
6. For firmware-specific delivery/ACK/size behavior, refetch the actual relevant firmware source/docs and require protocol/application evidence rather than generic queue/write success.

## Standing reminders

- Preserve source/evidence/recovery separation: `dev` / `node_observations` / `dev_handoff`.
- `TODO_004` remains `DEFERRED`; dependency satisfied does not itself change TODO status.
- Do not put concrete run IDs, addresses, measurements or topology into the class-level node skill.
- `.console.log` is presentation/audit convenience; the main `.log` and raw events remain forensic truth.
- Do not overclaim peer delivery from `queued`, `written`, local TX markers or console-log lines.
- Published snapshots stay immutable.