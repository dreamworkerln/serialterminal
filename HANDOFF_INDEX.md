# SerialTerminal handoff index

Latest verified snapshot: `HANDOFF_003.md`
Snapshot publication commit: `786f7b7daee160d409042418d5b3fcfb557cfa6b`
Recorded accepted TODO_028 implementation checkpoint: dreamworkerln/serialterminal/dev@`d868d026c05dac9373a47c0935673836432f9073`
Recorded documented closure checkpoint: dreamworkerln/serialterminal/dev@`a9b7499798a287937e07907913a30cd6c7e9190c`
Recorded hardware evidence/executor checkpoint: dreamworkerln/serialterminal/node_observations@`7fdfc328fa70e200d40ee6636dc5de2523bc816c`

## Current recovery state

TODO_028 is **CLOSED**.

Accepted source checkpoint:

```text
dev@d868d026c05dac9373a47c0935673836432f9073
GitHub Actions 36286979122 SUCCESS
209 tests PASS
```

Documented closure checkpoint:

```text
dev@a9b7499798a287937e07907913a30cd6c7e9190c
GitHub Actions 36287085802 SUCCESS
```

`HANDOFF_003.md` records the final generic sweep architecture, API, Chatter adapter settlement rules, source-review gate and validation provenance.

No physical sweep or hardware validation was performed as part of TODO_028 closure.

`HANDOFF_002.md` remains immutable historical state for the interrupted implementation checkpoint.

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

- TODO_028 source work is closed; use `HANDOFF_003.md` for the accepted sweep API/architecture state. Any real sweep is a separate physical-node task.
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
3. read `HANDOFF_003.md`;
4. read `TODO_INVENTORY.md`;
5. read `TODO_INVENTORY.md` for the currently selected next task; TODO_028 is closed;
6. refetch actual `dev` before source work;
7. inspect current source/tests at that ref before editing;
8. use the independent hardware executor workspace only for an explicitly separate physical-node task.

Historical snapshot state never overrides refetched source for current implementation truth.
