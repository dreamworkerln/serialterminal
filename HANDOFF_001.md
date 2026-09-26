# SerialTerminal engineering handoff

Snapshot: HANDOFF_001.md
Previous: none
Created: 2026-09-26T22:29:35Z
Handoff authority: dreamworkerln/serialterminal/dev root, pre-snapshot checkpoint `1f90928c79b894b3bd6fae425d6336644db55e10`
Source checkpoints:
  Active SerialTerminal source: dreamworkerln/serialterminal/dev@`1f90928c79b894b3bd6fae425d6336644db55e10`
  Hardware evidence/executor workspace: dreamworkerln/serialterminal/node_observations@`7fdfc328fa70e200d40ee6636dc5de2523bc816c`
Knowledge base:
  dreamworkerln/serialterminal/dev@`1f90928c79b894b3bd6fae425d6336644db55e10`: `AGENTS.md`, `ARCHITECTURE.md`, `AGENT_API.md`, `LOGGING.md`, `TODO_INVENTORY.md`, `TODO_MANAGEMENT_POLICY.md`, `HANDOFF_MANAGEMENT_POLICY.md`, `NODE_SKILL_LEARNING_POLICY.md`
Transfer / promotion boundary:
  Source-development work stays on `dev`; physical-node execution/evidence stays on `node_observations`. The branches are not merged as one workflow.

## Recovery order

1. Read root `AGENTS.md`.
2. Read `HANDOFF_INDEX.md`.
3. Read this snapshot.
4. Read `TODO_INVENTORY.md` and the specific active TODO before implementation.
5. Refetch the actual `dev` head before making current-state claims or edits.
6. Read `ARCHITECTURE.md` when work touches discovery, profiles, transports, session lifecycle, human presentation or agent open/session behavior.
7. Read `AGENT_API.md` when work changes machine-facing JSONL semantics.
8. For physical-node execution, switch context to the independent `serialterminal-observations` workspace and follow its own `AGENTS.md` / hardware skill; do not use this source snapshot as executor instructions.

Source code is authoritative for current implementation. This snapshot is authority only for the engineering state recorded at the checkpoint above.

## Repository / branch roles

### `dev`

Owns:

- SerialTerminal source and tests;
- generic transport/session/agent API;
- controller profiles and human frontend;
- maintained scenario/sweep runner source;
- architecture and API documentation;
- engineering TODO and reviewer policies.

### `node_observations`

Owns:

- physical LoRa-Chatter executor instructions;
- immutable RUN/OBS hardware evidence;
- executor evidence policies;
- reviewer state for hardware observations.

The physical executor treats `../serialterminal` as read-only runtime/source. It must not repair SerialTerminal source, tests, docs, TODOs or CI during a hardware run.

## Accepted architecture / invariants

The durable dependency direction is:

```text
human CLI -------------------+
                             |
JSONL agent -----------------+----> TerminalProfile configuration
                             |              |
                             |              v
                             +-------> SessionManager / TerminalSession
                                            |
                                            v
                                      ManagedSession
                                            |
                                            v
                                       Transport API
```

Controller-specific behavior belongs behind `TerminalProfile` or in higher-level consuming/scenario code. Generic discovery, transport, session and JSONL mechanics must remain controller-agnostic.

Important current contracts:

- `generic` remains the default profile;
- Chatter is selected explicitly with `profile:"chatter"`;
- discovery remains capability-based rather than controller-name based;
- `ManagedSession` owns reconnect, ordered TX, raw `SessionEvent` history and canonical logical-line assembly;
- `observe` is the receive/cursor API;
- default `observe` returns `lines`, `cursors`, `timed_out`;
- raw `events/data_b64` require `include_events:true`;
- `queued` / `written` are transport facts, not peer-delivery proof;
- `tx_state:"unknown"` is terminal for that TX and must not be blindly resent;
- forensic sequence loss is explicit through `forensic_gap`;
- human and agent frontends both create a timestamped companion `.console.log`, while their primary `.log` roles remain different.

## Material changes represented by the current checkpoint

### Hardware executor separation

Physical-node execution has moved out of the source-development workspace.

On `dev`:

- `.agents/skills/node-agent/SKILL.md` is only a redirect;
- dev-side hardware evidence policy files are migration pointers where applicable;
- source-development `AGENTS.md` is not an operating guide for the hardware executor.

The active hardware executor lives in the independent `serialterminal-observations` clone on `node_observations`, using `.agents/skills/lora-chatter-hardware/SKILL.md`.

### Agent response context reduction

Implemented at:

```text
dev@b7686b809ff4f7121d59b74903a8fa2251c1b4b5
```

Raw observe events became opt-in. `TODO_027` is CLOSED.

### Unified console logging

Implemented at:

```text
dev@5965d576c3bb124d85adf7842282684e755894c7
```

Both frontends now produce a shared timestamp/session/direction companion `.console.log`. Human primary `.log` remains the compatibility transcript; agent primary `.log` remains forensic/API/transport truth.

`TODO_026` remains `IMPLEMENTED / AGENT PHYSICAL VALIDATION OPEN`.

### BLE burst isolation

`TODO_024` is PARTIAL.

Host-side deterministic isolation proves that bytes delivered to the SerialTerminal notification callback are preserved through the tested callback -> queue -> `read_chunk` -> `ManagedSession` path.

Relevant checkpoints:

```text
host isolation test: dev@a8b6c1974242df0bb267fa7156c704f8aeb0f6c0
validated tree:      dev@bb48db1709ab66df3f4492f25a51b997fe23c357
hardware evidence:   node_observations@ccab9e37747c564c5f238cf6e5eef83fd8760ea1
```

The first physical loss boundary is still not isolated. The planned next diagnostic for that TODO is a bounded HCI/BlueZ capture such as `btmon` alongside SerialTerminal evidence.

## Newly selected work: TODO_028

At the current checkpoint, the new source-development task is recorded as:

```text
todos/TODO_028_CHATTER_SWEEP_RUNNER.md
Status: OPEN
creation checkpoint: dev@1f90928c79b894b3bd6fae425d6336644db55e10
```

Purpose: implement a maintained deterministic local LoRa-Chatter reliable-USER PHY/payload sweep runner so the tight measurement loop runs in Python above the public SerialTerminal JSONL API rather than through one LLM/tool turn per USER.

Required architecture:

```text
SerialTerminal core
        ↓
generic JSONL agent API
        ↓
reusable Chatter orchestration primitives
        ↓
scripts/run-chatter-scenario
scripts/run-chatter-sweep
```

Critical invariants for TODO_028:

- keep `src/serialterminal/agent.py` generic;
- use exactly one child `serialterminal.py agent` process for one sweep;
- no direct Bleak/pyserial bypass;
- at most one measured reliable USER transaction in flight across both nodes;
- do not infer causal order from cross-session list position;
- correlate by actual sender/session/USER identity plus deterministic payload context;
- do not pre-submit future measured USERs;
- `SESSION ... hdr=N` is summary telemetry, not a new HDR event;
- `DELIVERY WAIT_ACK ... timeout=...` is not an ACK-timeout event;
- only actual `DELIVERY ACK TIMEOUT ...` counts as ACK timeout;
- CRC/HDR remain unsequenced RF evidence unless a trustworthy protocol identifier exists;
- normal point count extends from configured normal repetitions (initial target 3+3) to configured anomaly repetitions (initial target 10+10) without discarding first samples;
- SF transition must explicitly send `/config` before waiting for `CFG RADIO / CFG LINK`;
- structured result is derived output and does not replace exact SerialTerminal logs;
- no real hardware sweep is part of this source-development task unless separately requested;
- do not modify `node_observations` while implementing TODO_028.

## Current implementation state

TODO_028 is documentation/task definition only at this snapshot.

Not implemented yet:

- `scripts/run-chatter-sweep`;
- reusable common sweep/scenario orchestration module, if one is selected;
- deterministic sweep correlation/state machine;
- sweep structured JSON result;
- TODO_028 fake/mock transcript/state-machine test matrix.

Existing `scripts/run-chatter-scenario` is the starting point and must remain behavior-compatible if common code is extracted.

## Validation actually completed

For the docs-only TODO creation checkpoint:

```text
dev@1f90928c79b894b3bd6fae425d6336644db55e10
commit: todo: track maintained Chatter sweep runner
GitHub Actions: 36276268588 SUCCESS
```

This CI result validates the repository at the docs-only checkpoint. It does **not** validate a sweep implementation because no sweep implementation exists yet.

No real hardware sweep was performed for TODO_028.

## Validation still required for TODO_028

Before closing TODO_028:

- fake/mock agent state-machine tests for clean 3+3;
- exact 10+10 anomaly extension behavior;
- HDR summary exclusion and real HEADER ERROR detection;
- WAIT_ACK timeout-field exclusion and actual ACK TIMEOUT detection;
- reverse/unexpected cross-session line ordering;
- exact current transaction ACK correlation;
- proof that next measured USER is not sent before settlement;
- proof that no future measured USER queue is pre-submitted;
- explicit `/sf -> SAVED -> send /config -> wait CFG` ordering regression;
- correlation-loss stop/recovery/failure behavior;
- CRC/HDR unsequenced handling;
- existing `run-chatter-scenario` regressions;
- deterministic child-process cleanup;
- targeted repository tests;
- compile/static/full repository validation required by `AGENTS.md`;
- final BASE..HEAD diff/deletion review;
- GitHub Actions SUCCESS for the resulting implementation checkpoint.

A physical sweep is not a source-task closure gate unless later explicitly added.

## Other open engineering state

The authoritative full list and statuses are in `TODO_INVENTORY.md`.

Important still-open/partial work includes:

- TODO_011 Chatter presentation correlation — OPEN;
- TODO_012 SPP capability UNKNOWN preservation — OPEN;
- TODO_013 Serial/SPP ambiguous writes — OPEN;
- TODO_014 human canonical line assembly alignment — OPEN;
- TODO_015 profile preamble scope — OPEN;
- TODO_016 BLE RX lifecycle boundary — OPEN;
- TODO_017 configured vs active streams — OPEN;
- TODO_018 observe thread retention — OPEN;
- TODO_019 strict agent request validation — OPEN;
- TODO_020 executable scanner workflow docs — OPEN;
- TODO_021 executor provenance boundary — PARTIAL;
- TODO_022 BLE connect timeout ownership — OPEN;
- TODO_023 capability cache concurrent writers — OPEN;
- TODO_024 BLE burst RX completeness — PARTIAL;
- TODO_025 material follow-up evidence — PARTIAL;
- TODO_026 unified logging — IMPLEMENTED / AGENT PHYSICAL VALIDATION OPEN;
- TODO_027 context amplification — CLOSED;
- TODO_028 maintained Chatter sweep runner — OPEN.

The current inventory-selected next implementation is TODO_028 before resuming TODO_024 HCI-boundary isolation.

## Immediate continuation steps

For TODO_028:

1. refetch `dev` and verify the branch/working tree before editing;
2. read `todos/TODO_028_CHATTER_SWEEP_RUNNER.md`;
3. inspect `scripts/run-chatter-scenario` and `tests/test_chatter_scenario_runner.py`;
4. identify the minimum reusable child-agent/orchestration primitives worth extracting;
5. design the sweep state machine around one globally serialized measured USER;
6. implement `scripts/run-chatter-sweep` above the public JSONL API;
7. add deterministic fake/mock tests for every mandatory regression in TODO_028;
8. run targeted tests, full repository validation, deletion/diff review and GitHub CI;
9. update TODO_028 and TODO_INVENTORY with exact implementation/validation checkpoints.

Do not perform a physical sweep during those source-development steps unless the operator explicitly starts a separate hardware-validation task.

## Standing reminders / risks

- Never treat a successful CI as physical-node validation.
- Never infer current-head hardware validity from historical RUNs.
- Hardware executor and source-development agent are separate roles/workspaces.
- Do not send source-development instructions to the hardware executor.
- Do not let higher-level Chatter scenario semantics leak into generic SerialTerminal transport/session code.
- When source and historical snapshot differ, refetched source wins for current implementation truth.
- Published hardware RUN/OBS evidence is immutable history; corrections are new evidence, not rewrites.
