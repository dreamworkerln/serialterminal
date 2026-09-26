# SerialTerminal handoff index

Latest verified snapshot: `HANDOFF_001.md`
Snapshot publication commit: `06b2c56c9c7e7f51125e38e8e7a2c5a14901f054`
Recorded active source checkpoint: dreamworkerln/serialterminal/dev@`1f90928c79b894b3bd6fae425d6336644db55e10`
Recorded hardware evidence/executor checkpoint: dreamworkerln/serialterminal/node_observations@`7fdfc328fa70e200d40ee6636dc5de2523bc816c`

## Current recovery state

The source-development checkpoint records `TODO_028_GENERIC_SWEEP_AGENT_API` as OPEN and selected as the next implementation task.

No sweep implementation exists yet. After `HANDOFF_001.md`, TODO_028 was deliberately redesigned at `dev@70e217c30180c4bf09a2f1e1c948cea4c2114af8`: the selected task is now a generic long-running sweep-job API inside the existing `serialterminal agent`, with fixed caller-specified repetitions, cursor/window long-poll progress, no unsolicited JSON, and no RF/protocol analytics in the generic sweeper.

`HANDOFF_001.md` remains immutable historical state and therefore still describes the superseded initial Chatter-runner formulation. For current TODO_028 semantics, the revised TODO/inventory at and after `dev@70e217c30180c4bf09a2f1e1c948cea4c2114af8` take precedence. Refetch actual `dev` before editing or claiming current implementation state.

## Repository roles

- `dev`: SerialTerminal source/tests/docs, generic JSONL API, profiles, maintained scenario/sweep code, engineering TODOs and reviewer policy.
- `node_observations`: physical hardware executor instructions and immutable RUN/OBS evidence.
- Physical hardware execution is a separate workspace/role and must not be given source-development work.

## Knowledge / authority entry points

Read as needed from the exact source checkpoint recorded by the snapshot:

- `AGENTS.md` — source-development operating rules;
- `ARCHITECTURE.md` — generic/profile/session/transport ownership boundaries;
- `AGENT_API.md` — machine-facing JSONL contract;
- `LOGGING.md` — forensic vs console logging contract;
- `TODO_INVENTORY.md` — authoritative current task/status map;
- `todos/TODO_028_GENERIC_SWEEP_AGENT_API.md` — selected next source task and authoritative revised sweep design;
- `NODE_SKILL_LEARNING_POLICY.md` — reviewer boundary for hardware evidence;
- `HANDOFF_MANAGEMENT_POLICY.md` — handoff publication/recovery rules.

## Standing reminders

- Implement `TODO_028` as a generic long-running job facility in the existing JSONL agent API, with the generic engine separated from measurement adapters.
- The sweeper executes exactly the requested repetitions; it does not perform anomaly analytics or autonomously extend a plan.
- Reuse the established cursor + timeout long-poll pattern for `sweep_observe`; no unsolicited JSON push.
- Do not bypass SerialTerminal transports with direct Bleak/pyserial.
- Do not modify `node_observations` during the source-development implementation.
- Do not perform a real hardware sweep unless explicitly requested as a separate hardware task.
- GitHub CI is software validation, not physical-node validation.
- After TODO_028, the inventory currently points back to TODO_024 HCI/BlueZ burst-loss isolation.

## Recovery order

1. read root `AGENTS.md`;
2. read this `HANDOFF_INDEX.md`;
3. read `HANDOFF_001.md`;
4. read `TODO_INVENTORY.md`;
5. read the specific selected TODO, currently `todos/TODO_028_GENERIC_SWEEP_AGENT_API.md`;
6. refetch actual `dev` before source work;
7. inspect current source/tests at that ref before editing;
8. use the independent hardware executor workspace only for an explicitly separate physical-node task.

Historical snapshot state never overrides refetched source for current implementation truth.
