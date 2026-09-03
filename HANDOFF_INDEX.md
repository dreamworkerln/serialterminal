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
Snapshot: 003
File: HANDOFF_003.md
Snapshot verified file checkpoint: dreamworkerln/serialterminal/dev_handoff@86aa1147f0dde755f4c4d353cd0a397890503323
Snapshot blob: fb3a789635b9ddc2a40116c0865c6ae16c72b70d
```

`HANDOFF_003.md` was created and read back before this index was advanced. `HANDOFF_001.md` and `HANDOFF_002.md` remain immutable historical snapshots.

## Current source roles

```text
Active SerialTerminal source/docs recorded by snapshot 003:
  dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2

Multi-session wait/concurrent JSONL accepted docs checkpoint:
  dreamworkerln/serialterminal/dev@aaeab3002e60bd1e85595d73e3248d42c3141c1f

Agent quality/static-analysis accepted checkpoint:
  dreamworkerln/serialterminal/dev@a74b46585b3f2c0e032b6b444b2d1089b4fde1e9

Handoff baseline immediately before snapshot 003 creation:
  dreamworkerln/serialterminal/dev_handoff@cee6f4e7251ee1b2cd891a76fa66a1ad59c89088

Related current protocol source at snapshot creation:
  dreamworkerln/lora-sack-protocol/dev_chat@49fcd72a26efa7f9f7029735242fa62d4fe66c1e
  NOTE: this is not asserted to be the exact firmware flashed during the manual hardware smoke.
```

Before code work, refetch moving `dev`; the exact source SHA above is snapshot state, not a promise that the branch has not moved.

## Current state summary

SerialTerminal has no active engineering TODO at this checkpoint. The generic machine interface is implemented, documented, CI-validated and has post-closure physical multi-device validation evidence.

Current important behavior:

- shared `ManagedSession` reconnect/RX/TX/event core used by human and agent frontends;
- `SessionManager` owns multiple independent long-lived physical-device sessions;
- request/response `serialterminal agent` JSONL frontend;
- reconnect-safe `send_line` / `send_bytes` with per-session TX workers/queues;
- retained cursor-based `events`;
- multi-session `wait_events` with independent cursors and deterministic merged batches;
- pending `wait_events` may execute asynchronously while ordinary JSONL commands continue;
- ordinary non-wait JSONL requests remain serialized in input order;
- responses may arrive out of request order and must be correlated by `id`;
- stdout remains request-correlated response-only output, with no unsolicited push events;
- `queued` means queue acceptance and `tx_state=written` means transport-write completion only, not peer/RF delivery;
- startup `Ctrl+T s` scanner handling works during initial discovery without concurrent scanner/discovery execution;
- CI includes compile, conservative Ruff static analysis, advisory Lizard complexity and tests;
- `AGENT_API.md` is the canonical generic machine API contract;
- `.agents/skills/serialterminal-agent/SKILL.md` is the active generic operational skill;
- `.agents/skills/node-agent/SKILL.md` is the active project-specific LoRa-Chatter node/hardware skill and is deliberately stored in this repository for stability across `lora-sack-protocol` branch/worktree changes;
- `TODO_001_AGENT_INTERFACE`, `TODO_002_AGENT_EVENT_WAIT`, and `TODO_003_AGENT_CODE_QUALITY` are CLOSED;
- `TODO_INVENTORY.md` has `Active: None`.

Final recorded current SerialTerminal CI:

```text
dev@30a084f6d726ccc0df19a3363dac129c3838f9b2
GitHub Actions run 33801154957: SUCCESS
Compile: PASS
Static analysis: PASS
Complexity: executed successfully / advisory
Tests: PASS
```

## Physical hardware validation state

Post-closure on 2026-09-03, physical multi-device agent use was observed:

- one agent process opened two physical BLE LoRa-Chatter nodes as independent sessions;
- Codex independently used `/help` to learn the node command surface;
- multi-session `wait_events` was exercised;
- ordinary commands continued while a wait remained pending;
- TX was issued from both sessions close together, exercising independent host-side per-session TX paths;
- earlier node-to-node transfer and Chatter echo behavior are recorded in the node skill;
- node `1B44` was also observed over USB with ESP32 powered while the radio-module power was intentionally absent, producing the expected `RADIO UNAVAILABLE bootTxSelfTest (-5); RF disabled` indication.

Do not interpret the close-together two-session TX observation as proof that both LoRa frames were received. Peer delivery still requires peer RX/telemetry evidence.

```text
Exact manual smoke process log ID: UNKNOWN / not recorded
Exact flashed firmware revision:       UNKNOWN / not recorded
```

Do not invent either value during recovery.

## Knowledge base

Primary project knowledge at the recorded source/docs checkpoint:

```text
dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2:AGENTS.md
dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2:AGENT_API.md
dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2:.agents/skills/serialterminal-agent/SKILL.md
dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2:.agents/skills/node-agent/SKILL.md
dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2:README.md
dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2:TODO_INVENTORY.md
dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2:todos/TODO_001_AGENT_INTERFACE.md
dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2:todos/TODO_002_AGENT_EVENT_WAIT.md
dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2:todos/TODO_003_AGENT_CODE_QUALITY.md
dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2:source comments/tests/CI configuration
```

Management policies remain in repository root. At the recorded synchronization point the intended copies shared these blobs:

```text
HANDOFF_MANAGEMENT_POLICY.md  f98fb6c475e1e890d7dedb962b06a57d2d72a016
TODO_MANAGEMENT_POLICY.md     c175d70073d9dc2b0c66ede9485d4ece8be3e050
```

## Authority boundaries

- `dev` is SerialTerminal implementation/documentation source authority.
- `dev_handoff` is recovery authority only.
- `AGENT_API.md` owns the generic SerialTerminal JSONL contract.
- Generic agent workflow belongs in `.agents/skills/serialterminal-agent/SKILL.md`.
- LoRa-Chatter node observations/operational guidance belong in `.agents/skills/node-agent/SKILL.md` for stable availability.
- Firmware/protocol implementation truth remains the actual relevant `lora-sack-protocol` source revision and physical evidence; the node skill does not replace source inspection.
- A future MCP adapter, if needed, must wrap the existing `SessionManager` rather than creating a parallel transport/session stack.

## Immediate continuation

There is no mandatory SerialTerminal code task after snapshot 003.

1. Refetch `dev` before any new source work.
2. Only open new terminal work when Chatter/hardware use exposes a concrete bug, missing API behavior or operational need.
3. Optional future polish, not active TODO: stable permission-error mapping and per-backend `discover scope:auto` diagnostics.
4. MCP remains deferred until a real consumer requires it.
5. Keep `.agents/skills/node-agent/SKILL.md` current when new physical findings materially change agent operation/validation.
6. Keep delivery claims tied to peer RX/telemetry, not merely `queued`, `written`, or local sender output.

## Standing reminders

- `TODO_INVENTORY.md`: `Active: None`.
- Current recorded `dev` CI is green at run `33801154957`.
- Post-closure physical multi-session validation has been observed; historical closure notes saying hardware was not a gate must not be misread as current `NOT RUN` status.
- Preserve human console behavior, generic API authority and shared session/transport ownership boundaries.
- Keep `dev_handoff` recovery-only and published snapshots immutable.
- Exact manual smoke log ID and exact flashed firmware revision are unknown.
