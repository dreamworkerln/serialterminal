# Handoff index

This file is the mutable stable recovery entry point for the `serialterminal` workstream.

## Recovery order

1. Applicable repository/workstream operating instructions (`AGENTS.md`).
2. `CONTEXT.md`, if present and relevant.
3. `HANDOFF_INDEX.md`.
4. Latest verified snapshot named below.
5. Project knowledge/docs/evidence referenced by that snapshot.
6. Refetch the actual moving source/evidence/firmware refs before current work.

## Snapshot rules

- `HANDOFF_NNN.md` snapshots are immutable after publication through this index.
- Create and read-back/verify a new snapshot before advancing this index.
- Never replace historical exact SHAs with moving branch heads.
- `dev_handoff` is handoff/recovery authority; `dev` remains source/docs authority.

## Current latest snapshot

```text
Snapshot: 007
File: HANDOFF_007.md
Snapshot verified file checkpoint: dreamworkerln/serialterminal/dev_handoff@faf4c2dcfabfc1b47ecf3926924a89bd3e38e49b
Snapshot blob: 594f42f22a403249977a8b01fad5c224c9f9bada
```

`HANDOFF_007.md` was created and read back before this index was advanced. `HANDOFF_001.md` through `HANDOFF_006.md` remain immutable historical snapshots.

## Current source roles recorded by snapshot 007

```text
SerialTerminal source/docs:
  dreamworkerln/serialterminal/dev@ab8dfde761e06649bdbb89173401e4054f9e8c18
  GitHub Actions run 34787938656: SUCCESS
  compile PASS / Ruff PASS / pytest 122 passed
  Lizard non-blocking: 14 threshold warnings

Node observation evidence:
  dreamworkerln/serialterminal/node_observations@761712ae7a7892764fbf47c1649710a1ef3e270f
  REVIEW_STATE.md remains unadvanced (none)

Chatter firmware/controller reference used for profile-boundary review:
  dreamworkerln/lora-sack-protocol/dev_chat@49fcd72a26efa7f9f7029735242fa62d4fe66c1e

Snapshot 007 pre-creation handoff checkpoint:
  dreamworkerln/serialterminal/dev_handoff@f624c5495ad48056f272144482187918ab568805
```

Before new work, refetch all relevant moving refs; these SHAs are snapshot state.

## Current state summary

- TODO_004 is CLOSED; snapshot 006's deferred/unimplemented description is historical only. Current `TODO_INVENTORY.md` reports no active TODOs.
- `ManagedSession`, `observe`, raw cursor model, per-stream logical-line assembly and `RunLog` remain invariants of the profile refactor.
- SerialTerminal now has a small profile seam: generic core/session mechanics do not need firmware lifecycle callbacks.
- Human CLI accepts `--profile generic|chatter` and defaults to `generic`.
- Generic profile sends no connect preamble, has no controller-specific hotkeys/presentation semantics, and uses standard BLE NUS `0002` write + `0003` receive as stream `main`.
- Chatter profile carries controller conveniences: `/id` preamble, `/help` forwarding, Chatter presentation, and BLE `0003 -> chat` plus optional `0004 -> telemetry`.
- Agent `open` is per-session profile-aware and defaults to `generic`; Chatter node workflows must explicitly use `"profile":"chatter"`. One process may mix profiles.
- Legacy `auto_id` remains only as a compatibility override; it is no longer the generic default behavior.
- `BleNusTransport` receive/write layout is injected; the transport no longer owns Chatter `0004` stream semantics.
- Generic decoupling is not complete: LoRa/Chatter discovery hints, Pinger/Repeater aliases, scanner `CHAT/TELEMETRY` capability labels and some constants still live outside the Chatter profile.
- Chatter raw shortcut actions are still `SendLine` and therefore still append EOL; exact no-EOL `SendBytes(14 31/32/33/65)` conversion remains pending as a deliberate behavior change.
- `README.md` is materially stale relative to current profile defaults. `AGENT_API.md` and both active agent skills were updated; README synchronization is immediate follow-up source/docs work.
- Current profile-refactor head has automated CI but no current-revision physical hardware proof. The latest evidence head contains runs performed with older SerialTerminal revisions; do not treat them as hardware validation of `dev@ab8dfde...`.
- `REVIEW_STATE.md` remains unadvanced; do not infer review/promotion from published run bundles.

## Knowledge base

Primary source/docs at the recorded `dev` checkpoint:

```text
AGENTS.md
AGENT_API.md
README.md                              # known stale profile sections
.agents/skills/serialterminal-agent/SKILL.md
.agents/skills/node-agent/SKILL.md
TODO_INVENTORY.md
NODE_OBSERVATION_RECORDING_POLICY.md
src/serialterminal/profiles/
src/serialterminal/terminal.py
src/serialterminal/agent.py
src/serialterminal/cli.py
src/serialterminal/transports/ble_nus.py
src/serialterminal/ble_discovery.py
tests/test_generic_profile.py
tests/test_profiles.py
tests/test_ble_nus.py
tests/test_agent.py
```

Evidence state at the recorded `node_observations` checkpoint:

```text
REVIEW_STATE.md
observations/
runs/
```

Firmware/controller source reference for this architectural boundary:

```text
dreamworkerln/lora-sack-protocol/dev_chat@49fcd72a26efa7f9f7029735242fa62d4fe66c1e
```

## Immediate continuation

1. Refetch `dev`, `node_observations`, and relevant firmware refs.
2. Synchronize `README.md` on `dev` with the generic-default / explicit-Chatter profile behavior.
3. Continue the deliberate audit of Chatter/LoRa assumptions still present in BLE discovery/scanner/name aliases without pulling `ManagedSession` or `observe` into a plugin framework.
4. Treat raw Chatter shortcut conversion to exact `SendBytes` without EOL as a separate tested behavior change.
5. Run a current-revision hardware regression through the real agent API with `open(profile="chatter")`; verify identity/help, expected BLE streams, and a narrow real node communication path before claiming physical validation of the profile refactor.
6. Preserve generic regression: connect/reconnect must emit zero controller-specific unsolicited bytes and arbitrary controller output must not be interpreted as Chatter.

## Standing reminders

- Preserve source/evidence/recovery separation: `dev` / `node_observations` / `dev_handoff`.
- TODO_004 is CLOSED.
- Published snapshots stay immutable.
- Profiles configure controller compatibility/convenience; firmware owns Chatter command/radio semantics.
- Do not put concrete run IDs, addresses, measurements or topology into the class-level node skill.
- `.console.log` is presentation/audit convenience; main `.log` and raw events remain forensic truth.
- Do not infer observation review/promotion while `REVIEW_STATE.md` remains unadvanced.
