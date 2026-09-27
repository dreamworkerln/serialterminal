# Current work context

Status: COMPLETED

## Current operation

Snapshot 008 publication is complete on the authoritative recovery branch `dev_handoff`.

No production/source implementation change was part of this handoff operation.

## Exact completed state

```text
SerialTerminal current source/docs:
  dreamworkerln/serialterminal/dev@ef22b2dd3a4073794abce21eaf2aeb91c33be73c
  GitHub Actions 36287455559 SUCCESS
  compile PASS / Ruff PASS / complexity PASS / pytest 209 passed

TODO_028 accepted implementation:
  dreamworkerln/serialterminal/dev@d868d026c05dac9373a47c0935673836432f9073
  GitHub Actions 36286979122 SUCCESS
  compile PASS / Ruff PASS / complexity PASS / pytest 209 passed

Observation evidence:
  dreamworkerln/serialterminal/node_observations@7fdfc328fa70e200d40ee6636dc5de2523bc816c

Chatter firmware/controller reference:
  dreamworkerln/lora-sack-protocol/dev_chat_ack@f04950672b895bd463b367cb02c155ed715bb111

Pre-snapshot handoff checkpoint:
  dreamworkerln/serialterminal/dev_handoff@2332e27190d779b7912d9bcadb00db86e2d1ad79

Verified snapshot creation:
  dreamworkerln/serialterminal/dev_handoff@ce63d8a92e137f5ee4114b5c8c45f9f6089f8c14
  HANDOFF_008.md blob ef37b94cdec4fa7b1a9ad8a23d7576e1f978363a

Index publication:
  dreamworkerln/serialterminal/dev_handoff@70ddc380e481dbf11ff4e6a83010f146f643c90d
  HANDOFF_INDEX.md blob 5c249b47409c9cc58591b6585fb41f9a5c9066f6
```

`HANDOFF_INDEX.md` now points to verified `HANDOFF_008.md`. Older published snapshots remain immutable.

## Current recovery state

Recovery order:

1. read current source `dev:AGENTS.md`;
2. read this `CONTEXT.md`;
3. read `HANDOFF_INDEX.md` on `dev_handoff`;
4. read verified `HANDOFF_008.md`;
5. read current `TODO_INVENTORY.md` and relevant source docs on `dev`;
6. refetch moving `dev`, `node_observations`, and relevant firmware refs before current work.

## Current project state

- `dev_handoff` is the authoritative recovery branch.
- `dev` is source/tests/docs authority.
- `node_observations` is physical hardware executor/evidence authority.
- `TODO_028_GENERIC_SWEEP_AGENT_API` is CLOSED.
- Generic sweep support lives in the existing `serialterminal agent` JSONL API; no separate sweep process/protocol exists.
- Sweep execution is exact-plan/fixed-repetition and intentionally contains no RF/protocol analytics or adaptive repetition policy.
- `sweep_observe` uses request/response cursor-window long-poll semantics with no unsolicited push.
- Participating sessions are mutation-owned while a sweep is active.
- First profile-owned adapter is `chatter.reliable_user`.
- Chatter sample settlement is correlated through a new local `DELIVERY WAIT_ACK` and subsequent terminal delivery result for the same delivery ID.
- Mechanical sweep events are persisted in the existing forensic log as `[SWEEP]` records.
- Current source/docs head is green in GitHub Actions with 209 tests.
- No physical TODO_028 sweep/hardware validation was performed.
- Current inventory suggests `TODO_024` HCI/BlueZ BLE burst-loss boundary isolation as the next implementation item.

## Validation

Current source/docs validation:

```text
dev@ef22b2dd3a4073794abce21eaf2aeb91c33be73c
GitHub Actions 36287455559 SUCCESS
Compile PASS
Ruff PASS
Complexity PASS
pytest 209 passed
```

Accepted TODO_028 source validation:

```text
dev@d868d026c05dac9373a47c0935673836432f9073
GitHub Actions 36286979122 SUCCESS
Compile PASS
Ruff PASS
Complexity PASS
pytest 209 passed
```

Hardware validation:

```text
NOT RUN
```

## Next action

No handoff publication action remains.

For the next engineering task:

1. refetch all moving refs;
2. treat TODO_028 as source/API closed unless a new bug is demonstrated;
3. run any real sweep as a separate hardware task through the observation workspace;
4. otherwise continue from current `TODO_INVENTORY.md`, whose suggested next item is TODO_024.

Do not use source-side handoff files on `dev` as the authoritative recovery series; use `dev_handoff/HANDOFF_INDEX.md`.
