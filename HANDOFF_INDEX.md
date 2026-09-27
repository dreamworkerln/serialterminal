# Handoff index

This file is the mutable stable recovery entry point for the `serialterminal` workstream.

## Recovery order

1. Read applicable source operating instructions from current `dev:AGENTS.md`.
2. Read `CONTEXT.md` on `dev_handoff` if relevant.
3. Read this `HANDOFF_INDEX.md`.
4. Read latest verified snapshot named below.
5. Read current source TODO/docs referenced by that snapshot.
6. Refetch actual moving source/evidence/firmware refs before new work.

## Snapshot rules

- `HANDOFF_NNN.md` snapshots are immutable after publication through this index.
- Create and read-back/verify a snapshot before advancing this index.
- Never replace historical exact SHAs with moving branch heads.
- `dev_handoff` is authoritative recovery state.
- `dev` is source/tests/docs authority.
- `node_observations` is physical hardware executor/evidence authority.

## Current latest snapshot

```text
Snapshot: 008
File: HANDOFF_008.md
Snapshot verified file checkpoint:
  dreamworkerln/serialterminal/dev_handoff@ce63d8a92e137f5ee4114b5c8c45f9f6089f8c14
Snapshot blob:
  ef37b94cdec4fa7b1a9ad8a23d7576e1f978363a
```

`HANDOFF_008.md` was created and read back before this index was advanced. `HANDOFF_001.md` through `HANDOFF_007.md` remain immutable historical snapshots.

## Current source roles recorded by snapshot 008

```text
SerialTerminal current source/docs:
  dreamworkerln/serialterminal/dev@ef22b2dd3a4073794abce21eaf2aeb91c33be73c
  GitHub Actions 36287455559: SUCCESS
  compile PASS / Ruff PASS / complexity PASS / pytest 209 passed

TODO_028 accepted implementation:
  dreamworkerln/serialterminal/dev@d868d026c05dac9373a47c0935673836432f9073
  GitHub Actions 36286979122: SUCCESS
  compile PASS / Ruff PASS / complexity PASS / pytest 209 passed

Node observation evidence:
  dreamworkerln/serialterminal/node_observations@7fdfc328fa70e200d40ee6636dc5de2523bc816c

Chatter firmware/controller reference inspected during TODO_028:
  dreamworkerln/lora-sack-protocol/dev_chat_ack@f04950672b895bd463b367cb02c155ed715bb111
```

Before new work, refetch moving refs; these SHAs are snapshot state.

## Current state summary

- `TODO_028_GENERIC_SWEEP_AGENT_API` is CLOSED in current `TODO_INVENTORY.md`.
- Generic sweep support is implemented inside the existing `serialterminal agent` JSONL API.
- Machine operations are `sweep_start`, `sweep_observe`, `sweep_cancel`, and `sweep_close`.
- Sweep execution is deliberately generic/dumb: exact caller-specified repetitions, deterministic traversal, no adaptive repetition or RF/protocol analytics.
- `sweep_observe` uses cursor/window long-poll semantics and no unsolicited server push.
- First version supports one active sweep per agent process.
- Participating sessions are mutation-owned while active; external `send_line`, `send_bytes`, and `close` are blocked before side effects on owned sessions.
- Read-only observation remains available where documented.
- Generic sweep/session code does not branch on concrete Chatter adapter names.
- First profile-owned adapter is `chatter.reliable_user`.
- Chatter adapter waits for operational reliable-USER settlement before next sample/config mutation.
- Adapter correlation binds to a new local `DELIVERY WAIT_ACK` and follows terminal delivery state by that exact delivery ID; it does not equate delivery session IDs with `/id`.
- Mechanical sweep lifecycle is persisted as `[SWEEP]` records in the existing forensic log using the same job-local event sequence as the API ring.
- Current `dev` head is green in GitHub Actions with 209 tests.
- No physical sweep or TODO_028 hardware validation has been run.
- Physical RF/environment isolation from unrelated sessions/devices remains caller/coordinator responsibility.
- Cross-process sweep resume, parallel sweep resource domains, adaptive analytics, and built-in result classification are outside TODO_028 scope.

## Knowledge base

Current source/docs authority:

```text
dreamworkerln/serialterminal/dev@ef22b2dd3a4073794abce21eaf2aeb91c33be73c
```

Read as needed:

```text
AGENTS.md
ARCHITECTURE.md
AGENT_API.md
LOGGING.md
TODO_INVENTORY.md
todos/TODO_028_GENERIC_SWEEP_AGENT_API.md
.agents/skills/serialterminal-agent/SKILL.md
src/serialterminal/sweep.py
src/serialterminal/agent.py
src/serialterminal/profiles/chatter/sweep.py
tests/test_sweep.py
tests/test_agent_sweep.py
tests/test_chatter_sweep_adapter.py
```

## Immediate continuation

1. Refetch `dev`, `node_observations`, and any relevant firmware ref.
2. Treat TODO_028 as source/API CLOSED unless a new bug is demonstrated.
3. If a real sweep is requested, execute it as a separate physical-node task through the observation workspace; do not silently reopen source work.
4. Otherwise follow current `TODO_INVENTORY.md`; its suggested next implementation item is `TODO_024` HCI/BlueZ BLE burst-loss boundary isolation.
5. Preserve the generic/profile dependency boundary and exact-repetition semantics.

## Standing reminders

- Authoritative recovery branch is `dev_handoff`.
- Source branch `dev` may contain historical/source-side handoff files, but they are not this workstream's authoritative recovery series.
- Keep source, recovery and hardware evidence on their separate refs.
- GitHub Actions is source/clean-environment validation, not physical-node validation.
- Do not infer hardware validity from TODO_028's 209 automated tests.
- Do not modify `node_observations` during ordinary source-development work.
- Published snapshots remain immutable.
