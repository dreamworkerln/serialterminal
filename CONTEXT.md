# Current work context

Status: COMPLETED

## Current operation

Snapshot 006 publication is complete.

No production source change was part of this handoff operation.

## Exact completed state

```text
SerialTerminal source/docs:
  dreamworkerln/serialterminal/dev@edeb4061d60a80768f38ddada0c6620798070d87
  GitHub Actions run 33980831322 SUCCESS

Observation evidence:
  dreamworkerln/serialterminal/node_observations@301751038847f8416d5f6bab617185eee41f7f0a

Pre-snapshot handoff checkpoint:
  dreamworkerln/serialterminal/dev_handoff@56c1533eb1ea2922a15e29e06a9ea0dde663ce6a

Verified snapshot creation:
  dreamworkerln/serialterminal/dev_handoff@1f2ce6be19e27621557de1f14c6d5278ecbb12cc
  HANDOFF_006.md blob 10a7c9edb1f765ae6bd886351126b4042c90d531

Index publication:
  dreamworkerln/serialterminal/dev_handoff@b0e3d2d400784b4c5baa3ffd5717214bb6e48d1a
```

`HANDOFF_INDEX.md` now points to `HANDOFF_006.md`. Older published snapshots remain immutable.

## Current recovery state

Recovery order:

1. read `AGENTS.md`;
2. read this `CONTEXT.md`;
3. read `HANDOFF_INDEX.md`;
4. read verified `HANDOFF_006.md`;
5. refetch moving `dev`, `node_observations`, and any relevant firmware/protocol refs before current work.

## Current project state

- `dev` is source/docs authority; `dev_handoff` is recovery-only; `node_observations` is append-only run-specific evidence/review state.
- `AGENT_API.md` is the canonical generic SerialTerminal JSONL contract.
- `observe` remains the only generic machine receive/cursor operation; old `events`/`wait_events` are removed.
- One raw cursor per session governs both raw `observe.result.events` and completed logical `observe.result.lines`.
- Logical line assembly lives canonically in `ManagedSession`, independently per stream; logging does not implement a second assembler.
- Agent runs produce paired forensic `.log` and human-console `.console.log` files.
- The forensic log keeps raw `[RX <stream>]` records and no separate `[RX LINE ...]` / `[RX PARTIAL ...]` convenience records.
- Companion `.console.log` uses `[session] [I] ...` for text accepted through `send_line` and `[session] [O] ...` for completed human-console RX lines.
- Firmware-owned leading `>` / `<` remain inside the firmware output text; separate BLE machine telemetry remains excluded from `.console.log` unless it actually arrives through the human-console stream.
- `TODO_004 — Automated node run bundles` remains `DEFERRED` and implementation is still not started. Its design has been expanded, but design-only changes and `runs/.gitkeep` do not constitute implementation progress.
- The TODO_004 return condition is satisfied by the accepted canonical `observe` + paired-log architecture; the exact accepted dependency checkpoint must still be recorded deliberately before implementation begins.
- `node_observations` now contains three additional observation records since snapshot 005 and `runs/.gitkeep`; `REVIEW_STATE.md` remains unadvanced (`none`).
- Chatter's 200-byte USER/ECHO guidance remains firmware/application-specific; generic SerialTerminal does not synchronously reject oversized text.
- `queued`, `written`, local TX markers, `[I]`, `[O]`, and firmware-owned `>` alone are not peer/application delivery proof.

## Validation

Current recorded source/docs validation:

```text
dev@edeb4061d60a80768f38ddada0c6620798070d87
GitHub Actions run 33980831322 SUCCESS
Compile PASS
Static analysis PASS
Complexity step PASS
Tests PASS
```

The companion-marker implementation checkpoint `dev@e6c025805d39c95b959272cb8a9d8c74ddc6eb23` also has GitHub Actions run `33969326449 SUCCESS`.

No new physical hardware interaction was performed by this handoff task.

## Next action

No handoff publication action remains.

For the next engineering task, refetch `dev` and relevant evidence/source refs first. If resuming TODO_004, record the exact accepted dependency checkpoint, update TODO state deliberately according to TODO policy, and preserve the current one-assembler / paired-log architecture. Hardware execution and observation review remain governed separately by `NODE_OBSERVATION_RECORDING_POLICY.md` and `NODE_SKILL_LEARNING_POLICY.md`.
