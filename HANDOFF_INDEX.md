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
Snapshot: 006
File: HANDOFF_006.md
Snapshot verified file checkpoint: dreamworkerln/serialterminal/dev_handoff@1f2ce6be19e27621557de1f14c6d5278ecbb12cc
Snapshot blob: 10a7c9edb1f765ae6bd886351126b4042c90d531
```

`HANDOFF_006.md` was created and read back before this index was advanced. `HANDOFF_001.md` through `HANDOFF_005.md` remain immutable historical snapshots.

## Current source roles recorded by snapshot 006

```text
SerialTerminal source/docs:
  dreamworkerln/serialterminal/dev@edeb4061d60a80768f38ddada0c6620798070d87
  GitHub Actions run 33980831322: SUCCESS

Node observation evidence:
  dreamworkerln/serialterminal/node_observations@301751038847f8416d5f6bab617185eee41f7f0a

Snapshot 006 pre-creation handoff checkpoint:
  dreamworkerln/serialterminal/dev_handoff@56c1533eb1ea2922a15e29e06a9ea0dde663ce6a
```

Before new work, refetch moving `dev`, `node_observations`, and any relevant firmware/protocol refs; the SHAs above are snapshot state.

## Current state summary

- `observe` remains the only generic machine receive/cursor operation; one raw per-session cursor drives both raw `result.events` and completed `result.lines`.
- Raw events remain forensic transport/session truth; logical lines are assembled once in `ManagedSession`, independently per stream.
- Agent runs produce paired forensic `.log` and human-console `.console.log` files. The forensic log has raw `[RX <stream>]` records and no separate `[RX LINE ...]` / `[RX PARTIAL ...]` records.
- Companion `.console.log` now uses explicit host-side markers: `[session] [I] ...` for text accepted through `send_line`, and `[session] [O] ...` for completed human-console RX lines.
- Firmware-owned leading `>` / `<` remain part of firmware output, e.g. `[s1] [O] > payload`; they are not replaced by the host markers.
- Separate BLE machine telemetry remains excluded from `.console.log` unless equivalent text actually arrives through the human-console stream.
- Marker change accepted at `dev@e6c02580...` with Actions `33969326449: SUCCESS`; current `dev@edeb4061...` adds documentation/planning refinement for TODO_004 and also has green CI.
- `TODO_004 — Automated node run bundles` remains `DEFERRED` and implementation is still not started. Its design now covers append-only RUN bundles, manifest/report/log artifacts, helper coexistence/backlog classification, and retry-safe normal-push recovery.
- `node_observations` advanced to `30175103...` with three new observation records and `runs/.gitkeep`; this scaffolding does not mean run-bundle automation is implemented.
- `REVIEW_STATE.md` remains unadvanced (`none`); do not infer review/promotion from new observation files.
- Chatter USER/ECHO still has a firmware/application 200 UTF-8 byte limit; generic SerialTerminal intentionally does not synchronously enforce it.
- `queued`, `written`, `[I]`, `[O]`, local TX markers and firmware-owned `>` alone are not peer/application delivery proof.

## Knowledge base

Primary SerialTerminal source/docs at the recorded `dev` checkpoint:

```text
AGENTS.md
AGENT_API.md
README.md
.agents/skills/serialterminal-agent/SKILL.md
.agents/skills/node-agent/SKILL.md
TODO_INVENTORY.md
todos/TODO_004_NODE_RUN_BUNDLES.md
TODO_MANAGEMENT_POLICY.md
NODE_OBSERVATION_RECORDING_POLICY.md
NODE_SKILL_LEARNING_POLICY.md
src/serialterminal/session.py
src/serialterminal/agent.py
src/serialterminal/runlog.py
tests/test_agent_console_log.py
```

Evidence state at the recorded `node_observations` checkpoint includes:

```text
REVIEW_STATE.md
observations/OBS_20260904T201422Z_ack-normal-presentation.md
observations/OBS_20260905T130038Z_radio-discovery-empty.md
observations/OBS_20260905T161000Z_bidirectional-user-smoke.md
runs/.gitkeep
```

Firmware/protocol implementation truth remains the actual relevant `lora-sack-protocol` source/docs revision when a future task involves firmware; snapshot 006 does not invent a flashed firmware SHA that was not established.

## Immediate continuation

1. Refetch `dev`, `node_observations`, and relevant firmware/protocol refs before changes.
2. Use `observe.result.lines` for completed firmware-line reasoning and `observe.result.events` for raw/chunk/byte forensics.
3. Preserve the one-assembler boundary and `[I]` / `[O]` console-log semantics; preserve firmware-owned `>` / `<` inside output text.
4. If resuming TODO_004, record the exact accepted dependency checkpoint and deliberately change TODO state according to TODO policy before implementation.
5. For hardware execution, follow `NODE_OBSERVATION_RECORDING_POLICY.md`; for observation review/promotion, separately follow `NODE_SKILL_LEARNING_POLICY.md`.
6. Do not claim review of the new observations until `REVIEW_STATE.md` is actually advanced.

## Standing reminders

- Preserve source/evidence/recovery separation: `dev` / `node_observations` / `dev_handoff`.
- `TODO_004` remains `DEFERRED`; expanded design and `runs/.gitkeep` are not implementation completion.
- Do not put concrete run IDs, addresses, measurements or topology into the class-level node skill.
- `.console.log` is presentation/audit convenience; main `.log` and raw events remain forensic truth.
- Published snapshots stay immutable.
