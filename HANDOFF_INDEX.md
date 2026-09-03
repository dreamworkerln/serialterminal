# Handoff index

This file is the mutable stable recovery entry point for the `serialterminal` workstream.

## Recovery order

1. `CONTEXT.md`, if present and relevant.
2. `HANDOFF_INDEX.md`.
3. Latest verified snapshot named below.
4. Project knowledge/docs referenced by that snapshot.
5. Refetch the actual source checkpoint/ref before current code work.

## Snapshot rules

- `HANDOFF_NNN.md` snapshots are immutable after publication through this index.
- Create and read-back/verify a new snapshot before advancing this index.
- Never replace historical exact SHAs with moving branch heads.
- `dev_handoff` is handoff/recovery authority; `dev` remains source-code authority.

## Current latest snapshot

```text
Snapshot: 001
File: HANDOFF_001.md
Snapshot verified file checkpoint: dreamworkerln/serialterminal/dev_handoff@5d54bf72f9505e33032e9fb6c8b4f09d9820bf63
```

`HANDOFF_001.md` was created and read back before this index was advanced.

## Current source roles

```text
Active source: dreamworkerln/serialterminal/dev@1e2f7632e7ea6d0cd20283ef713d811ca32dd178
Handoff baseline before snapshot creation: dreamworkerln/serialterminal/dev_handoff@1e2f7632e7ea6d0cd20283ef713d811ca32dd178
Policy provenance source: dreamworkerln/lora-sack-protocol/dev_exp_sim_validation@a75aabb2f8eefdbe061bb9f9fb75b37ce586d5d4
```

Before code work, refetch moving `dev`; the exact source SHA above is the state recorded by snapshot 001, not a promise that `dev` has not moved.

## Knowledge base

Primary project knowledge at the recorded source checkpoint:

```text
dreamworkerln/serialterminal/dev@1e2f7632e7ea6d0cd20283ef713d811ca32dd178:README.md
dreamworkerln/serialterminal/dev@1e2f7632e7ea6d0cd20283ef713d811ca32dd178:AGENTS.md
dreamworkerln/serialterminal/dev@1e2f7632e7ea6d0cd20283ef713d811ca32dd178:source comments and tests
```

Management policies are in repository root:

```text
HANDOFF_MANAGEMENT_POLICY.md
TODO_MANAGEMENT_POLICY.md
```

The TODO policy is installed, but `TODO_INVENTORY.md` / thematic TODO records are not initialized at snapshot 001.

## Immediate continuation

1. Refetch `dev` before further source work.
2. Run the pending live `Ctrl+T s` -> all scanner regression check described in `HANDOFF_001.md`.
3. Continue BLE stability observation; capture `btmon` HCI reason if disconnects recur.
4. Initialize the TODO inventory only when substantive tracked tasks require it.
5. Publish `HANDOFF_002.md` only at the next meaningful recovery checkpoint, using create -> read-back/verify -> advance-index order.

## Standing reminders

- Automated CI is green for recorded source `dev@1e2f7632...`; exact-current-head hardware validation is not claimed.
- Do not conflate historical HCI/BLE observations with a closed current hardware validation gate.
- Keep normal reconnect paused throughout scanner operation.
- Keep `dev_handoff` recovery-only; do not implement production code there by default.
- Keep future published snapshots immutable.
