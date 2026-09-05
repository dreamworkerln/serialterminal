# Current work context

Status: COMPLETED

## Current operation

Snapshot 005 publication is complete.

No production source change was part of this handoff operation.

## Exact completed state

```text
SerialTerminal source/docs:
  dreamworkerln/serialterminal/dev@e6e74a45237abaf488cb815c2bba185810215c9d
  GitHub Actions run 33959407933 SUCCESS

Observation evidence:
  dreamworkerln/serialterminal/node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198

Pre-snapshot context checkpoint:
  dreamworkerln/serialterminal/dev_handoff@20893774c60171d6d27d61f42031dcd67aae7951

Verified snapshot creation:
  dreamworkerln/serialterminal/dev_handoff@d85d962db5ca8157dd3a53f047bf10abece95fe3
  HANDOFF_005.md blob 4ed8464e8a479d6f26d9841b41857ae0a0097a5d

Index publication:
  dreamworkerln/serialterminal/dev_handoff@6bb4ecae4b1c6c890a3adf11a8e298aea6c92c9e
```

`HANDOFF_INDEX.md` now points to `HANDOFF_005.md`. Older published snapshots remain immutable.

## Current recovery state

Recovery order:

1. read `AGENTS.md`;
2. read this `CONTEXT.md`;
3. read `HANDOFF_INDEX.md`;
4. read verified `HANDOFF_005.md`;
5. refetch moving `dev` and any relevant evidence/protocol refs before current work.

## Current project state

- `dev` is source/docs authority; `dev_handoff` is recovery-only.
- `AGENT_API.md` is the canonical generic SerialTerminal JSONL contract.
- `observe` is now the only generic machine receive/cursor operation; old `events`/`wait_events` are removed.
- One raw cursor per session governs both raw `observe.result.events` and completed logical `observe.result.lines`.
- Logical line assembly lives canonically in `ManagedSession`, independently per stream; logging does not implement a second assembler.
- Agent runs produce paired `serialterminal-...log` forensic logs and `serialterminal-...console.log` human-console companion logs.
- The forensic log keeps raw `[RX <stream>]` records and no longer emits separate `[RX LINE ...]` / `[RX PARTIAL ...]` convenience records.
- Companion `.console.log` records session-scoped `send_line` input and completed human-console RX lines; separate BLE machine telemetry is excluded unless it actually appears in the human-console stream.
- `TODO_INVENTORY.md` now contains `TODO_004 — Automated node run bundles`, status `DEFERRED`.
- TODO_004's stated dependency/return condition is satisfied by accepted `dev@e6e74a4...`, but this handoff did not resume or change that TODO status.
- Run-specific hardware evidence remains in `node_observations`; `REVIEW_STATE.md` is still unadvanced (`none`).
- Chatter's 200-byte USER/ECHO guidance remains firmware/application-specific; generic SerialTerminal does not synchronously reject oversized text.

## Validation

Current recorded source validation:

```text
dev@e6e74a45237abaf488cb815c2bba185810215c9d
GitHub Actions run 33959407933 SUCCESS
Compile PASS
Static analysis PASS
Tests PASS (94 passed)
Lizard complexity remains advisory/non-blocking
```

No new physical hardware interaction was performed by this handoff task.

## Next action

No handoff publication action remains.

For the next engineering task, refetch `dev` first. If resuming TODO_004, record the exact accepted dependency checkpoint before implementation and preserve the current one-assembler / paired-log architecture. Hardware execution and observation review remain governed separately by `NODE_OBSERVATION_RECORDING_POLICY.md` and `NODE_SKILL_LEARNING_POLICY.md`.