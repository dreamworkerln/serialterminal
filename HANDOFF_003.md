# SerialTerminal handoff snapshot 003

```text
Snapshot: HANDOFF_003.md
Previous: HANDOFF_002.md
Created:  2026-09-27T01:57:25Z
Handoff authority before snapshot creation:
  dreamworkerln/serialterminal/dev@a9b7499798a287937e07907913a30cd6c7e9190c
Source checkpoints:
  accepted TODO_028 implementation:
    dreamworkerln/serialterminal/dev@d868d026c05dac9373a47c0935673836432f9073
  current documented source/recovery baseline:
    dreamworkerln/serialterminal/dev@a9b7499798a287937e07907913a30cd6c7e9190c
  hardware evidence/executor:
    dreamworkerln/serialterminal/node_observations@7fdfc328fa70e200d40ee6636dc5de2523bc816c
  Chatter firmware source reference:
    dreamworkerln/lora-sack-protocol/dev_chat_ack@c95e56c4f93c1f97bd10da7a56f78be151d4b9d0
Knowledge base:
  dreamworkerln/serialterminal/dev
  TODO_INVENTORY.md
  todos/TODO_028_GENERIC_SWEEP_AGENT_API.md
Transfer / promotion boundary:
  source + automated validation accepted; hardware validation not run
```

## Recovery authority

This snapshot supersedes `HANDOFF_002.md` for current recovery state.

`HANDOFF_002.md` remains immutable historical evidence of the interrupted implementation state. It must not be edited to reflect the later completion.

For current implementation truth always refetch `dev`; this snapshot records the accepted TODO_028 checkpoint and the validation evidence that existed when the handoff was published.

## Repository roles

### `dev`

Owns:

- SerialTerminal source;
- generic JSONL agent API;
- sweep engine and profile adapters;
- tests;
- architecture/API/logging docs;
- engineering TODO state;
- handoff/recovery docs.

### `node_observations`

Owns:

- physical hardware executor policy;
- immutable physical RUN/OBS evidence.

No physical-node work was performed as part of TODO_028 source closure.

## TODO_028 final architecture

TODO_028 is closed.

The maintained sweep architecture is:

```text
serialterminal agent JSONL frontend
              |
              v
      generic sweep job API
              |
              v
       generic sweep engine
              |
              v
    profile-owned adapter registry
              |
              v
      measurement adapter
```

Generic sweep responsibilities:

- ordered sweep axes;
- deterministic Cartesian traversal;
- exact caller-specified repetition count;
- long-running job lifecycle;
- bounded cursor/window event history;
- progress snapshots;
- cancellation;
- terminal retention;
- session mutation ownership;
- mechanical forensic events.

Generic sweep explicitly does not own:

- RF-quality analytics;
- ACK/CRC/HDR/retry interpretation;
- CLEAN/DEGRADED classification;
- automatic anomaly detection;
- adaptive repetition changes;
- Chatter command semantics.

The first concrete adapter is:

```text
chatter.reliable_user
```

and lives under the Chatter profile side of the architecture.

## Machine API

The existing long-lived entry point remains:

```bash
python3 serialterminal.py agent
```

Sweep operations are part of the same JSONL API:

```text
sweep_start
sweep_observe
sweep_cancel
sweep_close
```

The API preserves:

```text
one request id -> one response
no unsolicited JSON
```

`sweep_observe` uses the same long-poll style as existing `observe`.

Important semantics:

- `sweep_start` returns promptly;
- only one active sweep is allowed per agent process in this version;
- participating sessions must already be open;
- participating sessions are mutation-owned during the active sweep;
- external `send_line`, `send_bytes` and `close` are rejected on owned sessions;
- read-only status/observation remain available where documented;
- non-participating sessions are not implicitly blocked;
- isolation of the physical RF environment outside declared ownership remains caller responsibility;
- `sweep_cancel` requests cancellation and does not falsely claim immediate terminal cancellation;
- every blocking adapter phase has finite deadlines;
- `sweep_close` releases retained terminal job state;
- terminal job retention is globally bounded even if callers forget to close jobs.

## Event/cursor contract

Sweep events use a job-local monotonic sequence.

Reader cursor means:

```text
cursor = last event already consumed
return events with seq > cursor
```

The API exposes:

```text
events
cursor
head_cursor
state
progress
timed_out
```

The response window is bounded by the server-advertised maximum.

Expired retained-history cursors fail explicitly rather than silently skipping events.

Terminal job state is distinct from API request success/failure.

## Session ownership / concurrency contract

The implementation adds background mutation through the sweep worker, so ordinary session mutations and sweep mutations share a centralized ownership gate.

A successful sweep start atomically owns all participating sessions.

Ownership is released on terminal sweep transition, not on `sweep_close`.

A second active sweep is rejected.

The generic core does not inspect command text to decide whether a mutation is dangerous; external mutations on an owned session are rejected uniformly.

## Chatter reliable-user settlement

The accepted adapter behavior includes:

- already-open distinct Chatter sessions;
- cleanup of prior reliable work with `/cancel all`;
- background diagnostic/heartbeat/echo-loop quieting;
- forcing output mode `BOTH` so delivery telemetry is observable even where BLE telemetry stream 0004 is optional;
- node identity checks;
- power/frequency/BW/SF application;
- `SAVED` synchronization;
- `/config` verification;
- exactly one measured reliable USER transaction in flight at a time;
- no next sample or radio mutation until the previous sample is operationally settled;
- bounded cancellation and cleanup.

The adapter does not classify RF quality.

Important correlation detail:

- `/id` reports a hardware/eFuse-derived node identity;
- delivery records use the protocol boot-session/sequence identifier;
- those identities must not be compared;
- the adapter binds the measured sample to the first new local `DELIVERY WAIT_ACK user=session/seq` after sample start;
- later ACK/FAILED records are correlated by that exact delivery identifier.

## Firmware formatting compatibility

Chatter firmware `formatMilli()` removes trailing fractional zeroes.

Examples:

```text
470.000 -> 470
500.000 -> 500
62.500  -> 62.5
7.800   -> 7.8
```

The adapter parses numeric `FREQ/BW ... SAVED` and `CFG RADIO` values and compares normalized numeric values rather than padded textual formatting.

## Forensic logging

Mechanical sweep lifecycle is persisted through the existing `RunLog` using:

```text
[SWEEP]
```

records.

The forensic event carries the same job-local event sequence used by the in-memory sweep event ring, allowing precise correlation between API progress and durable TX/RX evidence.

The forensic sweep records contain execution mechanics only. They do not contain RF/protocol analytics.

## Implementation checkpoints after interrupted HANDOFF_002

Material post-handoff commits:

```text
0a4851fe6ec9546ae6c26bc6816b46e906e2effc  fix: stabilize Chatter radio value parsing
47c498d8be63f6d5593f5afeb786e02e9a1d194e  sweep: harden generic job publication
32ea573ef4abdd8fab5bfa8d04bf1884e3f1abe7  test: share sweep adapter factory identity
bb4786c5c97a66ebd780abbb379e0cec3c20796b  test: lock sweep JSONL error semantics
a90efdffdca9b35ba97922937dfa00734ccc4876  chatter: harden sweep settlement correlation
69bc5206e0b3526a1a319280db3d7109a1df32ec  test: fix forensic correlation lint
c4f0ae1eec8b097a37ea51c1ae0041a194940db1  chatter: guarantee sweep telemetry visibility
c0849a1e0cc481c8648072fb1a7dd143d98a1ca5  docs: document sweep agent API
907e6ee724efa3726838ef88f280eae7fd7ca6e9  docs: fix sweep direction example
a82f0c2b189c38c8a5baf0b6d87ab88c612963a7  docs: record sweep architecture and logging
999076af690fec2b8a134ba08e154704ccb918c3  docs: teach agent skill sweep workflow
73b4488e690994001008f790ba5f5cba279dc577  chatter: correlate sweep delivery by WAIT_ACK
d868d026c05dac9373a47c0935673836432f9073  test: lock sweep lifecycle deadlines
```

The TODO/inventory closure was then recorded at:

```text
dev@a9b7499798a287937e07907913a30cd6c7e9190c
```

## Automated validation

Accepted source checkpoint:

```text
dev@d868d026c05dac9373a47c0935673836432f9073
GitHub Actions 36286979122 SUCCESS
compile PASS
ruff PASS
complexity PASS
pytest 209 passed
```

Current documented closure checkpoint:

```text
dev@a9b7499798a287937e07907913a30cd6c7e9190c
GitHub Actions 36287085802 SUCCESS
```

No hardware validation was run.

## Source-review gate

The final source review used:

```text
base: 5996a7eaa0275784cccc860199c1a69c0b8ef666
head: d868d026c05dac9373a47c0935673836432f9073
```

Recorded review outcome:

- all pre-existing source deletions inspected;
- no pre-existing function definition disappeared;
- `agent.py` deletions were replacements by ownership-aware mutation/shutdown/async handling;
- generic `agent.py` and `sweep.py` contain no Chatter/reliable-user special case or adapter-name branch;
- controller-specific behavior remains under the Chatter profile adapter;
- no hardware execution performed.

## Documentation state

The accepted API/architecture is documented in:

```text
AGENT_API.md
ARCHITECTURE.md
LOGGING.md
.agents/skills/serialterminal-agent/SKILL.md
todos/TODO_028_GENERIC_SWEEP_AGENT_API.md
TODO_INVENTORY.md
```

## Current status

```text
TODO_028:
  CLOSED

implementation:
  dev@d868d026c05dac9373a47c0935673836432f9073

implementation CI:
  36286979122 SUCCESS
  209 tests PASS

documented closure:
  dev@a9b7499798a287937e07907913a30cd6c7e9190c

closure CI:
  36287085802 SUCCESS

hardware:
  NOT RUN
```

## Next engineering direction

TODO_028 source work is complete.

The inventory currently points back to TODO_024 for the BLE/HCI burst-loss isolation work.

Any real sweep using the new API is a separate physical-node task and must follow the independent hardware-executor workflow rather than being treated as part of this source closure.
