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
Snapshot: 004
File: HANDOFF_004.md
Snapshot verified file checkpoint: dreamworkerln/serialterminal/dev_handoff@04b85a08f65a8d22c710f5cf7b289f9a977f4eaa
Snapshot blob: 6600bd4c52ee84107dc23a0522f06470951c80a9
```

`HANDOFF_004.md` was created and read back before this index was advanced. `HANDOFF_001.md`, `HANDOFF_002.md`, and `HANDOFF_003.md` remain immutable historical snapshots.

## Current source roles recorded by snapshot 004

```text
SerialTerminal source/docs:
  dreamworkerln/serialterminal/dev@0da242eb9c67bf82d59fbfbbcb0bca3ced92a942
  GitHub Actions run 33909130096: SUCCESS

Node observation evidence:
  dreamworkerln/serialterminal/node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198

Snapshot 004 pre-creation handoff checkpoint:
  dreamworkerln/serialterminal/dev_handoff@390ce4ebe138f9661b20603a37618a0edc15ba65
```

Before new work, refetch moving `dev` and any relevant evidence/protocol refs; the SHAs above are snapshot state.

## Current state summary

- No active generic SerialTerminal engineering TODO (`TODO_INVENTORY.md`: `Active: None`).
- Generic SerialTerminal Python transport/session/terminal core did not change between snapshots 003 and 004.
- `AGENT_API.md` remains the generic JSONL authority; current launch guidance says to run the agent with elevated privileges in the intended hardware environment.
- `.agents/skills/node-agent/SKILL.md` is now strictly class-level reusable LoRa-Chatter guidance; run-specific facts belong in `node_observations`.
- `NODE_OBSERVATION_RECORDING_POLICY.md` governs executor raw evidence and guarded observation publication.
- `NODE_SKILL_LEARNING_POLICY.md` governs reviewer generalization/promotion and `REVIEW_STATE.md` advancement.
- `node_observations` currently contains three observation records; its `REVIEW_STATE.md` is still unadvanced (`none`).
- Current node skill documents ACK-capable reliable USER behavior, bounded retry/queue/cancellation/duplicate semantics and focused two-node reliability gates.
- Chatter USER/ECHO guidance uses `1..200` UTF-8 bytes, but generic SerialTerminal does not hard-code that application limit.
- Oversized Chatter text is queued/written generically and firmware rejection returns later through RX; `[SYS] INPUT TOO LONG: max 200 bytes` is an RX/SYSTEM outcome, not synchronous `send_line ok:false`.

## Knowledge base

Primary current SerialTerminal docs at the recorded `dev` checkpoint:

```text
AGENTS.md
AGENT_API.md
.agents/skills/serialterminal-agent/SKILL.md
.agents/skills/node-agent/SKILL.md
NODE_OBSERVATION_RECORDING_POLICY.md
NODE_SKILL_LEARNING_POLICY.md
scripts/commit-node-observation
TODO_INVENTORY.md
source/tests/CI configuration
```

Evidence state at the recorded `node_observations` checkpoint:

```text
REVIEW_STATE.md
observations/OBS_20260904T075106Z_max-text-payload.md
observations/OBS_20260904T085207Z_oversized-payload.md
observations/OBS_20260904T134143Z_empty-and-size-speed.md
```

Firmware/protocol implementation truth remains the actual relevant `lora-sack-protocol` source/docs revision; snapshot 004 does not invent an exact firmware SHA that was not established.

## Immediate continuation

There is no mandatory SerialTerminal code task after snapshot 004.

1. Refetch `dev` before source/docs changes.
2. For hardware execution, follow `NODE_OBSERVATION_RECORDING_POLICY.md`.
3. For observation review/promotion, follow `NODE_SKILL_LEARNING_POLICY.md`; current evidence range is not yet advanced in `REVIEW_STATE.md`.
4. For ACK/retry details, check the actual relevant firmware source/docs before treating current implementation-policy values as permanent constants.
5. For oversized text, wait for firmware RX/SYSTEM evidence; generic queue/write success is not application acceptance.
6. Open new generic terminal implementation work only for a concrete defect or requirement.

## Standing reminders

- Preserve source/evidence/recovery separation: `dev` / `node_observations` / `dev_handoff`.
- Do not put concrete run IDs, addresses, measurements or topology into the class-level node skill.
- Do not overclaim peer delivery from `queued`, `written`, or local TX markers.
- Published snapshots stay immutable.
