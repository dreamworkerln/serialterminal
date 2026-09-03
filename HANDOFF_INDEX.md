# Handoff index

This file is the mutable stable recovery entry point for the `serialterminal` workstream.

## Recovery order

1. Applicable repository/workstream operating instructions (`AGENTS.md`), if present.
2. `CONTEXT.md`, if present and relevant.
3. `HANDOFF_INDEX.md`.
4. Latest verified snapshot named below.
5. Project knowledge/docs referenced by that snapshot.
6. Refetch the actual source checkpoint/ref before current code work.

## Snapshot rules

- `HANDOFF_NNN.md` snapshots are immutable after publication through this index.
- Create and read-back/verify a new snapshot before advancing this index.
- Never replace historical exact SHAs with moving branch heads.
- `dev_handoff` is handoff/recovery authority; `dev` remains source-code authority.

## Current latest snapshot

```text
Snapshot: 002
File: HANDOFF_002.md
Snapshot verified file checkpoint: dreamworkerln/serialterminal/dev_handoff@9ada46f6e3e7a4b37a29fc140ccb1d30fdb9c4f4
```

`HANDOFF_002.md` was created and read back before this index was advanced.

## Current source roles

```text
Active source recorded by snapshot 002:
  dreamworkerln/serialterminal/dev@b5bd01eeb1f016ff58d3a69d3421087ac4027019

Accepted agent implementation checkpoint:
  dreamworkerln/serialterminal/dev@396f499305c7ab1c425483b5a5f10e8521125f4f

Handoff baseline before snapshot 002 creation:
  dreamworkerln/serialterminal/dev_handoff@7b3d7039266e0733d5ddebcf98270dbad477b686

Policy provenance source:
  dreamworkerln/lora-sack-protocol/dev_exp_sim_validation@a75aabb2f8eefdbe061bb9f9fb75b37ce586d5d4
```

Before code work, refetch moving `dev`; the exact source SHA above is snapshot state, not a promise that the branch has not moved.

## Current state summary

The first generic Codex/agent interface is implemented and automated-validation complete:

- shared `ManagedSession` reconnect/RX/TX/event core;
- human `TerminalSession` migrated onto the shared core;
- `SessionManager` for multiple independent device sessions;
- local request/response `serialterminal agent` JSONL frontend;
- reconnect-safe `send_line` and raw `send_bytes`;
- cursor-based retained `events` receive/wait with stream tags;
- agent `auto_id=true` connect/reconnect preamble with explicit opt-out;
- unique default `logs/serialterminal-*.log` paths for normal human/agent runs;
- agent request/response + state/TX/RX/error events in one chronological process log;
- `AGENT_API.md` documentation;
- `TODO_001_AGENT_INTERFACE` CLOSED.

Final recorded source CI:

```text
dev@b5bd01eeb1f016ff58d3a69d3421087ac4027019
GitHub Actions run 33764490648: SUCCESS
```

Hardware smoke of the new agent interface has NOT been run and is not claimed.

## Knowledge base

Primary project knowledge at the recorded source checkpoint:

```text
dreamworkerln/serialterminal/dev@b5bd01eeb1f016ff58d3a69d3421087ac4027019:README.md
dreamworkerln/serialterminal/dev@b5bd01eeb1f016ff58d3a69d3421087ac4027019:AGENT_API.md
dreamworkerln/serialterminal/dev@b5bd01eeb1f016ff58d3a69d3421087ac4027019:TODO_INVENTORY.md
dreamworkerln/serialterminal/dev@b5bd01eeb1f016ff58d3a69d3421087ac4027019:todos/TODO_001_AGENT_INTERFACE.md
dreamworkerln/serialterminal/dev@b5bd01eeb1f016ff58d3a69d3421087ac4027019:source comments and tests
```

Management policies remain in repository root:

```text
HANDOFF_MANAGEMENT_POLICY.md
TODO_MANAGEMENT_POLICY.md
```

LoRa/Chatter-specific Codex hardware-test skills are intentionally owned by `lora-sack-protocol`, not by the generic SerialTerminal implementation.

## Immediate continuation

1. Refetch `dev` before further source work.
2. Run a live local `python3 serialterminal.py agent` hardware smoke and inspect the generated process log.
3. Verify real `discover -> open -> send/events -> close` and, if hardware permits, two simultaneous physical sessions.
4. Define LoRa/Chatter-specific Codex skills and acceptance scenarios in `lora-sack-protocol` when ready.
5. If MCP is needed later, create a separate TODO and wrap the existing `SessionManager` API.
6. Keep the scanner/Bluetooth hardware validation thread from snapshot 001 separate unless it affects live agent testing.

## Standing reminders

- Automated CI is green for the recorded final source; hardware validation of the agent frontend remains pending.
- `tx_state=written` is transport write evidence, not LoRa/peer delivery evidence.
- Preserve human console behavior and shared session/transport ownership boundaries.
- Keep `dev_handoff` recovery-only; do not implement production code there by default.
- Keep future published snapshots immutable.
