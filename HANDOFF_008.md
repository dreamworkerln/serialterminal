# Handoff snapshot 008

```text
Snapshot: HANDOFF_008.md
Previous: HANDOFF_007.md
Created: 2026-09-27T02:02:00Z
Handoff authority before snapshot creation:
  dreamworkerln/serialterminal/dev_handoff@2332e27190d779b7912d9bcadb00db86e2d1ad79
Source checkpoints:
  SerialTerminal current source/docs:
    dreamworkerln/serialterminal/dev@ef22b2dd3a4073794abce21eaf2aeb91c33be73c
  TODO_028 accepted implementation:
    dreamworkerln/serialterminal/dev@d868d026c05dac9373a47c0935673836432f9073
  Node observation evidence:
    dreamworkerln/serialterminal/node_observations@7fdfc328fa70e200d40ee6636dc5de2523bc816c
  Chatter firmware/controller reference inspected during TODO_028:
    dreamworkerln/lora-sack-protocol/dev_chat_ack@f04950672b895bd463b367cb02c155ed715bb111
Knowledge base:
  dreamworkerln/serialterminal/dev@ef22b2dd3a4073794abce21eaf2aeb91c33be73c
  AGENTS.md
  ARCHITECTURE.md
  AGENT_API.md
  LOGGING.md
  TODO_INVENTORY.md
  todos/TODO_028_GENERIC_SWEEP_AGENT_API.md
  .agents/skills/serialterminal-agent/SKILL.md
Transfer / promotion boundary:
  none; TODO_028 source/API work is closed by automated validation,
  physical sweep/hardware validation remains a separate task
```

This snapshot becomes immutable after publication through `HANDOFF_INDEX.md`.

## 1. Recovery / authority

Authoritative recovery state lives on:

```text
dreamworkerln/serialterminal/tree/dev_handoff
```

Repository roles:

```text
dev
    source/tests/docs authority

dev_handoff
    handoff/recovery authority

node_observations
    physical hardware executor/evidence authority
```

The source-side `HANDOFF_*.md` / `HANDOFF_INDEX.md` files that exist on `dev` are not the authoritative recovery series for this workstream. The operator explicitly selected `dev_handoff` for handoff publication.

Before any new engineering work, refetch moving refs. Historical exact SHAs in this snapshot are immutable checkpoint facts, not claims that branch heads will remain there.

## 2. Material changes since HANDOFF_007

Snapshot 007 recorded the earlier profile-refactor state around:

```text
dev@ab8dfde761e06649bdbb89173401e4054f9e8c18
```

Since then the source workstream advanced substantially. The material item for this handoff is closure of:

```text
TODO_028_GENERIC_SWEEP_AGENT_API
```

TODO_028 was redesigned before implementation from a Chatter-specific QA runner into a generic long-running sweep primitive inside the existing `serialterminal agent` JSONL API.

The implementation was initially interrupted at:

```text
dev@a131ac14ea5956d4511c0695aeff10f1760482db
```

with one failing Chatter adapter test. Work later resumed in small CI-gated checkpoints and the TODO was completed and closed.

Important resumed checkpoints:

```text
0a4851fe6ec9546ae6c26bc6816b46e906e2effc  fix: stabilize Chatter radio value parsing
47c498d8be63f6d5593f5afeb786e02e9a1d194e  sweep: harden generic job publication
d23ccf4d8bc669c4879fed5472546cb79b58d5c3  test: lock sweep session ownership contract
32ea573ef4abdd8fab5bfa8d04bf1884e3f1abe7  test: share sweep adapter factory identity
bb4786c5c97a66ebd780abbb379e0cec3c20796b  test: lock sweep JSONL error semantics
a90efdffdca9b35ba97922937dfa00734ccc4876  chatter: harden sweep settlement correlation
05d55148ae86bb7c327ed2ea1248500c9f5fcb07  test: correlate sweep events with forensic log
69bc5206e0b3526a1a319280db3d7109a1df32ec  test: fix forensic correlation lint
c4f0ae1eec8b097a37ea51c1ae0041a194940db1  chatter: guarantee sweep telemetry visibility
c0849a1e0cc481c8648072fb1a7dd143d98a1ca5  docs: document sweep agent API
907e6ee724efa3726838ef88f280eae7fd7ca6e9  docs: fix sweep direction example
a82f0c2b189c38c8a5baf0b6d87ab88c612963a7  docs: record sweep architecture and logging
999076af690fec2b8a134ba08e154704ccb918c3  docs: teach agent skill sweep workflow
73b4488e690994001008f790ba5f5cba279dc577  chatter: correlate sweep delivery by WAIT_ACK
d868d026c05dac9373a47c0935673836432f9073  test: lock sweep lifecycle deadlines
```

Closure/documentation commits after the accepted implementation checkpoint:

```text
a9b7499798a287937e07907913a30cd6c7e9190c  todo: close generic sweep agent API
786f7b7daee160d409042418d5b3fcfb557cfa6b  handoff: record accepted sweep implementation
ef22b2dd3a4073794abce21eaf2aeb91c33be73c  handoff: advance recovery index to snapshot 003
```

Those source-side handoff files are historical/source-branch records only; recovery authority is now this `dev_handoff` series.

## 3. Current TODO_028 implementation state

TODO_028 is CLOSED.

Accepted implementation checkpoint:

```text
dreamworkerln/serialterminal/dev@d868d026c05dac9373a47c0935673836432f9073
```

Current source/docs head:

```text
dreamworkerln/serialterminal/dev@ef22b2dd3a4073794abce21eaf2aeb91c33be73c
```

### Generic sweep engine

The source now has a generic sweep layer, centered on:

```text
src/serialterminal/sweep.py
```

Core properties:

- ordered caller-supplied axes/coordinates;
- exact fixed `repetitions=N`;
- deterministic traversal;
- no adaptive 3->10 extension;
- bounded plan/schema validation before job creation;
- bounded event history;
- cursor/window event reads;
- explicit job state/progress snapshot;
- cancellation;
- terminal-job retention bound;
- explicit `sweep_close`;
- adapter phase deadlines;
- one active sweep per agent process in the first version.

Schema hygiene rejects at least:

- duplicate axis names;
- collisions between constants and axis names;
- empty axis values;
- non-positive/invalid repetitions;
- excessive serialized plan size;
- excessive axis count;
- excessive Cartesian/sample count.

### Existing agent JSONL API extension

The machine-facing entry point remains:

```text
python3 serialterminal.py agent
```

No second sweep process/protocol was introduced.

Sweep operations are:

```text
sweep_start
sweep_observe
sweep_cancel
sweep_close
```

The API preserves:

```text
one request id
-> exactly one correlated response
```

There is no unsolicited JSON push.

`sweep_observe` reuses the established long-poll model:

- reader cursor;
- caller-requested window;
- server-advertised maximum window;
- `head_cursor`;
- timeout;
- current state/progress;
- terminal wakeup.

Job failure remains distinct from API request failure.

### Session ownership / concurrency

A running sweep owns mutation rights for its declared participating sessions.

While ownership is active, external mutation paths such as:

```text
send_line
send_bytes
close
```

are rejected before side effects on owned sessions.

Read-only observation remains available where documented.

Ownership is all-or-nothing across declared sessions and is released on terminal/failure/shutdown paths.

The first version intentionally allows only one active sweep per agent process. This avoids claiming that disjoint session sets are independent physical measurement domains.

Non-participating sessions/devices are not globally blocked. Physical RF/environment isolation beyond declared ownership remains caller/coordinator responsibility.

### Adapter boundary

Generic agent/sweep code does not branch on concrete Chatter adapter names.

Concrete adapters are profile-owned through the generic adapter registry/interface.

The first maintained adapter is:

```text
chatter.reliable_user
```

It operates only on already-open compatible sessions.

The generic engine does not contain:

- Chatter command strings;
- ACK/CRC/HDR/retry quality analytics;
- CLEAN/DEGRADED classification;
- anomaly policy;
- adaptive repetition policy.

Protocol-specific synchronization required to know when a sample is operationally settled belongs to the adapter.

### Chatter reliable-USER adapter

The adapter establishes a controlled measurement state and performs the first real use case without turning the generic sweeper into a Chatter QA framework.

Important behavior now covered by source/tests:

- settle old reliable work before radio mutation;
- disable/quiet background modes required by the measurement setup;
- guarantee delivery telemetry visibility needed for operational synchronization;
- apply requested power/frequency/BW/SF;
- verify actual radio configuration;
- start one reliable USER sample at a time;
- do not treat `queued` or transport `written` as device/radio settlement;
- bind a sample to the first new local `DELIVERY WAIT_ACK` after sample start;
- correlate subsequent terminal `ACK` / `FAILED` by that exact reliable delivery ID;
- do not compare reliable delivery IDs against `/id` application identity;
- block the next sample/config transition until the prior sample reaches its adapter-defined operational settlement;
- use bounded cancellation/deadline behavior.

Important firmware/source finding resolved during implementation:

```text
/id identity
    !=
reliable DELIVERY user=session/seq session identity
```

The adapter therefore must not infer delivery correlation from `/id`.

Another resolved firmware formatting issue:

- Chatter `formatMilli()` canonicalizes trailing decimal zeroes;
- adapter parsing compares numeric values rather than requiring padded strings such as `470.000` or `500.000`.

### Forensic logging

Sweep execution events are persisted through the existing SerialTerminal forensic logger.

Mechanical records use:

```text
[SWEEP]
```

and carry the same job-local event sequence used by the in-memory/API event stream.

This permits exact correlation of API progress with surrounding TX/RX evidence after in-memory sweep history is released.

The sweep logger records execution mechanics, not RF/protocol interpretation.

## 4. Architecture / invariants

Preserve the dependency direction documented in `ARCHITECTURE.md`:

```text
generic agent/session/transport
        |
        v
generic sweep job/engine
        |
        v
SweepAdapter interface / registry
        |
        v
profile-owned concrete adapter
```

Do not introduce:

```python
if adapter == "chatter.reliable_user":
    ...
```

into generic sweep/session code.

Also preserve:

- `ManagedSession` owns generic ordered TX/event/session mechanics;
- transport `written` is not application/radio completion;
- concrete controller protocol semantics belong to profiles/adapters or consuming project-specific logic;
- experiment analytics remain outside the generic sweeper;
- exact repetitions are caller policy, not runtime analytics policy;
- detailed forensic truth remains in the existing main `.log`;
- `.console.log` remains presentation/audit convenience.

## 5. Validation evidence

### Accepted implementation checkpoint

```text
dev@d868d026c05dac9373a47c0935673836432f9073
GitHub Actions 36286979122: SUCCESS
compile: PASS
ruff: PASS
complexity: PASS
pytest: 209 passed
```

The final BASE..HEAD source review for TODO_028 used:

```text
base: 5996a7eaa0275784cccc860199c1a69c0b8ef666
head: d868d026c05dac9373a47c0935673836432f9073
```

Recorded review result:

- all pre-existing source deletions inspected;
- no pre-existing function definition disappeared;
- `agent.py` deletions were replacements by ownership-aware equivalents;
- generic `agent.py` / `sweep.py` contain no concrete Chatter/reliable-user branch;
- controller-specific behavior remains in the Chatter profile adapter.

### Current source/docs head

```text
dev@ef22b2dd3a4073794abce21eaf2aeb91c33be73c
GitHub Actions 36287455559: SUCCESS
compile: PASS
ruff: PASS
complexity: PASS
pytest: 209 passed
```

Thus the current source/docs head is also green in the clean GitHub Actions environment.

### Hardware validation

```text
NOT RUN
```

No physical sweep, BLE/serial node execution, or firmware flashing was performed as part of TODO_028 source closure.

Do not infer physical validation from automated tests.

## 6. Current TODO / workstream state

`TODO_INVENTORY.md` on current `dev` records:

```text
TODO_028: CLOSED
```

The inventory's suggested next implementation order begins with:

```text
TODO_024 — BLE burst RX completeness / HCI boundary isolation
```

Other active/partial work remains listed in the authoritative inventory.

TODO_026 remains:

```text
IMPLEMENTED / AGENT PHYSICAL VALIDATION OPEN
```

and should not be silently treated as physically closed.

## 7. Known limitations / non-goals

Current sweep design intentionally does not provide:

- cross-process persistence/resume of active sweep jobs;
- parallel active sweep jobs/resource-domain scheduling;
- automatic RF/environment isolation from unrelated devices;
- adaptive repetition based on observed results;
- RF/protocol quality classification;
- built-in experiment analysis.

These are not missing implementation bugs in TODO_028; they are outside its accepted scope.

## 8. Knowledge references

Current source/docs authority:

```text
dreamworkerln/serialterminal/dev@ef22b2dd3a4073794abce21eaf2aeb91c33be73c
```

Read as needed:

```text
AGENTS.md
ARCHITECTURE.md
AGENT_API.md
LOGGING.md
TODO_INVENTORY.md
todos/TODO_028_GENERIC_SWEEP_AGENT_API.md
.agents/skills/serialterminal-agent/SKILL.md
src/serialterminal/sweep.py
src/serialterminal/agent.py
src/serialterminal/profiles/chatter/sweep.py
tests/test_sweep.py
tests/test_agent_sweep.py
tests/test_chatter_sweep_adapter.py
```

Physical evidence authority:

```text
dreamworkerln/serialterminal/node_observations@7fdfc328fa70e200d40ee6636dc5de2523bc816c
```

Firmware/controller reference inspected during TODO_028:

```text
dreamworkerln/lora-sack-protocol/dev_chat_ack@f04950672b895bd463b367cb02c155ed715bb111
```

Before using firmware facts for new work, refetch the relevant firmware ref.

## 9. Immediate continuation

1. Read `AGENTS.md` from the current source branch.
2. Read `HANDOFF_INDEX.md` on `dev_handoff`.
3. Read this `HANDOFF_008.md`.
4. Read current `TODO_INVENTORY.md` on `dev`.
5. Refetch `dev`, `node_observations`, and any required firmware ref before changing anything.
6. Treat TODO_028 as source/API CLOSED unless a new bug is demonstrated.
7. If the operator wants a real sweep, start it as a separate physical-node task in the observation workspace; do not convert that into hidden source work.
8. Otherwise follow the current inventory ordering, whose next suggested engineering item is TODO_024 HCI/BlueZ burst-loss boundary isolation.

## 10. Standing reminders

- Authoritative recovery branch is `dev_handoff`, not `dev`.
- Keep source development, handoff recovery and physical evidence on their separate refs.
- Published handoff snapshots remain immutable.
- GitHub Actions proves clean-environment source/test behavior, not physical radio behavior.
- Generic sweeper stays dumb: execute exact plan, report mechanics, no analytics.
- Chatter-specific synchronization stays behind the profile-owned adapter boundary.
- A sweep owns only declared sessions; unrelated physical RF interference remains an external-environment responsibility.
- Do not modify `node_observations` during ordinary source-development work.
