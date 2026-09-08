# Handoff snapshot 006

```text
Snapshot: HANDOFF_006.md
Previous: HANDOFF_005.md
Created: 2026-09-08T17:59:00Z
Handoff authority: dreamworkerln/serialterminal/dev_handoff@56c1533eb1ea2922a15e29e06a9ea0dde663ce6a
Source checkpoints:
  SerialTerminal source/docs: dreamworkerln/serialterminal/dev@edeb4061d60a80768f38ddada0c6620798070d87
  Node observation evidence: dreamworkerln/serialterminal/node_observations@301751038847f8416d5f6bab617185eee41f7f0a
Knowledge base:
  SerialTerminal source/docs at dev@edeb4061d60a80768f38ddada0c6620798070d87
  Node observation evidence at node_observations@301751038847f8416d5f6bab617185eee41f7f0a
Transfer / promotion boundary: none; this snapshot records current source/docs/evidence state and does not promote observation findings into class-level node guidance.
```

## Recovery / authority rules

Read applicable `AGENTS.md` first, then `CONTEXT.md`, `HANDOFF_INDEX.md`, and this snapshot. Refetch moving refs before new engineering work.

Authority split remains:

```text
dev
    source/docs authority

dev_handoff
    recovery/handoff authority only

node_observations
    append-only run-specific hardware evidence/review state
```

`AGENT_API.md` is the canonical generic SerialTerminal JSONL contract. `.agents/skills/serialterminal-agent/SKILL.md` is the concise generic operational skill. `.agents/skills/node-agent/SKILL.md` is project-specific reusable LoRa-Chatter guidance and must not contain run-specific node IDs, addresses, measurements or current topology.

## Material changes since snapshot 005

Snapshot 005 recorded `dev@e6e74a45237abaf488cb815c2bba185810215c9d` and `node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198`.

### Companion console direction markers

The accepted console-log presentation changed from ambiguous host-side arrows to explicit input/output markers:

```text
[s1] [I] user input
[s1] [O] firmware output
```

Semantics:

```text
[I] = text accepted through send_line
[O] = completed logical line received from a human-console stream
```

Firmware-owned leading `>` / `<` are preserved inside the firmware line itself. Therefore examples such as these are intentional:

```text
[s1] [I] radio-check-1B44-780
[s1] [O] > radio-check-1B44-780
[s2] [O] < [-13/+10 Q100] radio-check-1B44-780
```

This change did not alter `observe`, raw event semantics, logical-line assembly, the forensic log, or BLE machine-telemetry filtering.

Accepted implementation/docs checkpoint for the marker change:

```text
dev@e6c025805d39c95b959272cb8a9d8c74ddc6eb23
GitHub Actions run 33969326449: SUCCESS
```

Publication history contains two transient normal commits (`21c36d0e...` and `d76630e...`) created by mistaken contents API calls before the clean marker commit. The transient `DO_NOT_USE` path is absent from the accepted/current tree. History was not rewritten or force-pushed.

### TODO_004 design refinement

Current source/docs head is:

```text
dev@edeb4061d60a80768f38ddada0c6620798070d87
docs: refine node run bundle publication
GitHub Actions run 33980831322: SUCCESS
```

This commit is documentation/planning only and substantially expands `todos/TODO_004_NODE_RUN_BUNDLES.md`. `TODO_004` remains `DEFERRED`; implementation has not started and its implementation/validation checklists remain unchecked.

Its return condition is nevertheless satisfied by the accepted observation/paired-log architecture already present on `dev`: one canonical `observe` API provides raw events plus completed logical lines, and the same session line model feeds the companion human-console logfile. Before TODO_004 implementation begins, its exact accepted dependency checkpoint must be recorded as required by the TODO.

The refined target design includes:

- append-only `runs/RUN_<stamp>_<topic>/` bundles in `node_observations`;
- exact `serialterminal.log` and `serialterminal.console.log`, curated `REPORT.md`, and small `MANIFEST.json`;
- optional matching `OBS_*.md` controlled by observation policy rather than duplication;
- separate guarded `commit-node-observation` and `commit-node-run` publication helpers;
- coexistence of standalone observations, complete runs, incomplete recognized staging, and accumulated backlogs;
- retry-safe recovery when commit succeeds but normal push fails;
- hard failure for behind/diverged/unsafe local-ahead states without merge/rebase/reset/force push;
- publication helpers that validate/stage/push prepared artifacts but never invent, repair, summarize or reinterpret evidence.

`runs/.gitkeep` appearing on the evidence branch is only storage scaffolding; it is not evidence that TODO_004 implementation is complete.

## Current generic agent architecture

`observe` remains the only generic receive/cursor operation. Former `events` and `wait_events` operations are removed.

One raw per-session cursor drives both views:

```text
observe.result.events
    raw SessionEvent / transport-session forensic truth

observe.result.lines
    completed LF-terminated logical firmware lines
```

Logical-line assembly remains canonical in `ManagedSession`, independently per stream. BLE/serial transports continue exposing real chunks; logging does not create a second assembler.

A line may span an input cursor boundary. It is returned when `line.seq_last` is newer than the caller cursor even when `seq_first` is older/equal, so callers do not need to rebuild completed lines from raw chunks.

## Run logging invariants

Each agent run produces paired files:

```text
serialterminal-...-pPID.log
serialterminal-...-pPID.console.log
```

Main `.log` remains forensic/API/transport truth with raw `[RX <stream>]` records and no separate `[RX LINE ...]` / `[RX PARTIAL ...]` convenience records.

Companion `.console.log` is presentation/audit convenience only:

```text
[sN] [I] text accepted by send_line
[sN] [O] completed human-console RX line
```

For BLE, the separate machine telemetry stream is not copied into `.console.log` merely because SerialTerminal subscribes to it. If firmware output such as `/both` emits telemetry text through the human-console/chat stream itself, that completed human-console line naturally appears in `.console.log`.

Neither console lines nor local TX state prove peer/application delivery.

## TODO state

`TODO_INVENTORY.md` currently lists one active item:

```text
TODO_004 — Automated node run bundles
Status: DEFERRED
```

Current implementation status remains not started. The planning baseline in the TODO is historical (`dev@fe6ad62a...`); the current accepted source/docs checkpoint for recovery is `dev@edeb4061...`.

Do not silently treat the expanded design or `runs/.gitkeep` as implementation progress. When implementation actually starts, follow `TODO_MANAGEMENT_POLICY.md`, record the accepted dependency checkpoint, and update TODO state deliberately.

## Node observation evidence state

Evidence branch advanced from snapshot 005 to:

```text
node_observations@301751038847f8416d5f6bab617185eee41f7f0a
```

New append-only evidence since `b024b43e...` includes:

```text
observations/OBS_20260904T201422Z_ack-normal-presentation.md
observations/OBS_20260905T130038Z_radio-discovery-empty.md
observations/OBS_20260905T161000Z_bidirectional-user-smoke.md
runs/.gitkeep
```

The three branch commits after the previous evidence checkpoint are:

```text
21d1a2bf5a1c677da6bf9242a38bbc322220c6dc  obs: record node observations
d57640bd4c2cc1b871e0c5012aae41ef985dacd9  obs: bidirectional user smoke
301751038847f8416d5f6bab617185eee41f7f0a  added runs
```

`REVIEW_STATE.md` remains unadvanced:

```text
last_reviewed_observation: none
last_reviewed_observation_commit: none
reviewed_against_dev: none
reviewed_by_commit: none
reviewed_at: none
unresolved: []
```

Do not infer review/promotion from the presence of new observations.

## Firmware/application size boundary

Chatter USER/ECHO guidance still uses a firmware/application maximum of 200 UTF-8 bytes. Generic SerialTerminal intentionally does not hard-code this Chatter-specific limit.

For an oversized line, generic `send_line` may still return queued/written transport state; firmware rejection arrives asynchronously through RX, for example as a `[SYS] INPUT TOO LONG: max 200 bytes` firmware line. Treat that as device/application feedback, not as a synchronous generic `send_line` API error.

## Validation

Current exact source/docs validation:

```text
dev@edeb4061d60a80768f38ddada0c6620798070d87
GitHub Actions run 33980831322: SUCCESS
Compile: PASS
Static analysis: PASS
Complexity step: PASS
Tests: PASS
```

The marker-change checkpoint `dev@e6c025805d39c95b959272cb8a9d8c74ddc6eb23` also has GitHub Actions run `33969326449: SUCCESS`.

No new physical hardware interaction was performed by this handoff task.

## Important current documents

Source/docs authority at `dev@edeb4061...`:

```text
AGENTS.md
AGENT_API.md
README.md
.agents/skills/serialterminal-agent/SKILL.md
.agents/skills/node-agent/SKILL.md
TODO_INVENTORY.md
todos/TODO_004_NODE_RUN_BUNDLES.md
TODO_MANAGEMENT_POLICY.md
NODE_OBSERVATION_RECORDING_POLICY.md
NODE_SKILL_LEARNING_POLICY.md
src/serialterminal/session.py
src/serialterminal/agent.py
src/serialterminal/runlog.py
tests/test_agent_console_log.py
```

Evidence authority at `node_observations@3017510...`:

```text
REVIEW_STATE.md
observations/
runs/
```

Firmware/protocol implementation truth remains the actual relevant `lora-sack-protocol` source revision when a future task involves firmware. This snapshot does not invent a flashed firmware SHA that was not established.

## Immediate continuation

1. Refetch `dev`, `node_observations`, and any relevant firmware/protocol refs before new work.
2. Continue using `observe.result.lines` for completed firmware-line reasoning and `observe.result.events` for raw/chunk/byte forensics.
3. Preserve the one-assembler boundary and the `[I]` / `[O]` companion-log markers; firmware-owned `>` / `<` remain inside output text.
4. If resuming TODO_004, first record the exact accepted observation/console dependency checkpoint and deliberately change TODO state according to TODO policy; do not redesign `observe` or reconstruct the console log.
5. For hardware runs, continue following `NODE_OBSERVATION_RECORDING_POLICY.md`; observation review/promotion remains separately governed by `NODE_SKILL_LEARNING_POLICY.md`.
6. Do not claim review of the new observations until `REVIEW_STATE.md` is actually advanced.

## Standing reminders

- Preserve source/evidence/recovery separation: `dev` / `node_observations` / `dev_handoff`.
- Published handoff snapshots are immutable.
- `TODO_004` is still `DEFERRED` and unimplemented despite its satisfied return condition and expanded design.
- Append-only committed observations/run evidence must not be rewritten in place.
- Do not store concrete run-specific identity/measurements/topology in the class-level node skill.
- `.console.log` is presentation/audit convenience, not forensic truth or delivery proof.
- `queued`, `written`, local markers, `[I]`, `[O]`, and firmware-owned `>` alone are insufficient as peer/application delivery evidence.
