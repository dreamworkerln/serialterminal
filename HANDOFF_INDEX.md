# SerialTerminal handoff index

Latest verified snapshot: `HANDOFF_002.md`
Snapshot publication commit: `4adc721be89fb62d7941dda829d8e06c6d5d0a1c`
Recorded interrupted implementation checkpoint: dreamworkerln/serialterminal/dev@`a131ac14ea5956d4511c0695aeff10f1760482db`
Recorded documentation/recovery baseline before snapshot: dreamworkerln/serialterminal/dev@`c263a7f90c17012141e52bca673d64e76edd2be3`
Recorded hardware evidence/executor checkpoint: dreamworkerln/serialterminal/node_observations@`7fdfc328fa70e200d40ee6636dc5de2523bc816c`

## Current recovery state

TODO_028 is **PARTIAL / IMPLEMENTATION STOPPED**.

The operator explicitly stopped implementation at:

```text
dev@a131ac14ea5956d4511c0695aeff10f1760482db
```

Do not continue from memory. `HANDOFF_002.md` records the exact partial implementation, commit sequence, architecture boundary, known risks and resume procedure.

Latest implementation validation checked before handoff:

```text
GitHub Actions 36284195278
compile PASS
ruff PASS
complexity PASS
pytest 1 failed / 182 passed
```

The remaining failure is the Chatter adapter apply test after aligning the fake transcript with firmware canonical `formatMilli()` output. No further code debugging was performed after the stop request.

No hardware sweep or physical validation was performed.

`HANDOFF_001.md` remains immutable historical state and contains the earlier pre-implementation/superseded TODO wording.

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

- Resume `TODO_028` only from `HANDOFF_002.md`; first reproduce/fix the single known failing Chatter adapter test, then complete repository validation before any hardware use.
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
3. read `HANDOFF_002.md`;
4. read `TODO_INVENTORY.md`;
5. read the specific selected TODO, currently `todos/TODO_028_GENERIC_SWEEP_AGENT_API.md`;
6. refetch actual `dev` before source work;
7. inspect current source/tests at that ref before editing;
8. use the independent hardware executor workspace only for an explicitly separate physical-node task.

Historical snapshot state never overrides refetched source for current implementation truth.
