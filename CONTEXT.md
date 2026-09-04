# Current work context

Status: COMPLETED

## Current operation

Snapshot 004 publication is complete.

No production Python source change was part of this handoff operation.

## Exact completed state

```text
SerialTerminal source/docs:
  dreamworkerln/serialterminal/dev@0da242eb9c67bf82d59fbfbbcb0bca3ced92a942
  GitHub Actions run 33909130096 SUCCESS

Observation evidence:
  dreamworkerln/serialterminal/node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198

Operating-instructions sync:
  dreamworkerln/serialterminal/dev_handoff@544bd8fdacab5581cf5da985e0d7426ccf767c77

Pre-snapshot context checkpoint:
  dreamworkerln/serialterminal/dev_handoff@390ce4ebe138f9661b20603a37618a0edc15ba65

Verified snapshot creation:
  dreamworkerln/serialterminal/dev_handoff@04b85a08f65a8d22c710f5cf7b289f9a977f4eaa
  HANDOFF_004.md blob 6600bd4c52ee84107dc23a0522f06470951c80a9

Index publication:
  dreamworkerln/serialterminal/dev_handoff@5e06958e4a229e2fa1fd178251f9f9b54ebb984f
```

`HANDOFF_INDEX.md` now points to `HANDOFF_004.md`. Older published snapshots remain immutable.

## Current recovery state

Recovery order:

1. read `AGENTS.md`;
2. read this `CONTEXT.md`;
3. read `HANDOFF_INDEX.md`;
4. read verified `HANDOFF_004.md`;
5. refetch moving `dev` and any relevant evidence/protocol refs before current work.

## Current project state

- `dev` is source/docs authority; `dev_handoff` is recovery-only.
- `AGENT_API.md` is the generic SerialTerminal JSONL contract.
- `.agents/skills/serialterminal-agent/SKILL.md` is the generic operational skill.
- `.agents/skills/node-agent/SKILL.md` contains reusable class-level LoRa-Chatter guidance only.
- Run-specific hardware evidence lives in orphan branch `node_observations` under `observations/*.md`.
- Executor evidence recording is governed by `NODE_OBSERVATION_RECORDING_POLICY.md`.
- Reviewer generalization/promotion is governed by `NODE_SKILL_LEARNING_POLICY.md`.
- `node_observations@b024b43e...` contains three observations and `REVIEW_STATE.md` is still unadvanced (`none`).
- Node skill currently documents ACK-capable reliable USER semantics and focused reliability validation rules.
- `TODO_INVENTORY.md` remains `Active: None`.
- No SerialTerminal Python core file changed between snapshots 003 and 004.

## Oversized text boundary

Current Chatter guidance uses `1..200` UTF-8 bytes for USER/ECHO payloads. Generic SerialTerminal does not hard-code that firmware limit.

`send_line` queue success is not firmware acceptance. An oversized Chatter line is sent through the generic transport path and the firmware rejection is returned later through RX. Current inspected behavior emits:

```text
[SYS] INPUT TOO LONG: max 200 bytes
```

For the machine interface this is an RX/SYSTEM event consumed through `events`/`wait_events`, not synchronous `send_line ok:false`.

## Validation

Current recorded `dev` CI:

```text
dev@0da242eb9c67bf82d59fbfbbcb0bca3ced92a942
GitHub Actions run 33909130096 SUCCESS
```

No new hardware interaction was performed by this handoff task.

## Next action

No handoff publication action remains. Refetch `dev` for the next engineering task. If processing the existing observation range, perform a separate reviewer pass according to `NODE_SKILL_LEARNING_POLICY.md`; do not assume the current records have already been reviewed.
