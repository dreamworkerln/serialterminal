# SerialTerminal handoff snapshot 002

```text
Snapshot: HANDOFF_002.md
Previous: HANDOFF_001.md
Created:  2026-09-27T01:15:27Z
Handoff authority before snapshot creation:
  dreamworkerln/serialterminal/dev@c263a7f90c17012141e52bca673d64e76edd2be3
Source checkpoints:
  interrupted sweep implementation:
    dreamworkerln/serialterminal/dev@a131ac14ea5956d4511c0695aeff10f1760482db
  current documentation/recovery baseline before this snapshot:
    dreamworkerln/serialterminal/dev@c263a7f90c17012141e52bca673d64e76edd2be3
  hardware evidence/executor:
    dreamworkerln/serialterminal/node_observations@7fdfc328fa70e200d40ee6636dc5de2523bc816c
  Chatter firmware source reference inspected during implementation:
    dreamworkerln/lora-sack-protocol/dev_chat_ack@c95e56c4f93c1f97bd10da7a56f78be151d4b9d0
Knowledge base:
  dreamworkerln/serialterminal/dev
  TODO_INVENTORY.md
  todos/TODO_028_GENERIC_SWEEP_AGENT_API.md
Transfer / promotion boundary:
  none; implementation is partial, CI is red, no hardware validation was run
```

## Recovery authority

Read current source from the repository, not from this snapshot.

This snapshot records the exact interrupted state after the operator explicitly requested:

- stop all further implementation;
- preserve what had already been committed;
- document the interruption;
- publish a handoff;
- do not continue debugging the code in the current session.

`HANDOFF_001.md` remains immutable historical state. It predates both the final generic sweep redesign and the partial implementation recorded here.

For current sweep semantics and resume instructions, this snapshot plus:

```text
TODO_INVENTORY.md
todos/TODO_028_GENERIC_SWEEP_AGENT_API.md
```

supersede the old TODO_028 description inside `HANDOFF_001.md`.

## Repository roles

### `dev`

Owns:

- SerialTerminal source;
- tests;
- generic JSONL agent API;
- profiles;
- architecture/API/logging docs;
- source-development TODOs;
- handoff/recovery state.

### `node_observations`

Owns:

- physical-node executor policy;
- immutable hardware RUN/OBS evidence.

Do not use `node_observations` for source-development edits.

No hardware work was performed during this interrupted sweep implementation.

## What changed since HANDOFF_001

TODO_028 was first redesigned from a Chatter-specific runner into a generic long-running sweep-job facility in the existing JSONL agent.

The accepted design boundary before implementation was:

```text
generic sweep engine
    plan / axes / deterministic traversal
    exact caller-specified repetitions
    job lifecycle
    cursor/window progress
    cancellation
    retention
    session ownership

profile-owned measurement adapter
    device/protocol-specific coordinate apply/verify
    one-sample operational settlement

caller / reviewer
    experiment analytics
    log interpretation
    adaptive follow-up decisions
```

The generic engine must not contain:

- Chatter command strings;
- ACK/CRC/HDR/retry analytics;
- CLEAN/DEGRADED classification;
- automatic anomaly detection;
- adaptive 3->10 repetition logic;
- experiment-specific policy.

The sweeper executes exactly the requested plan.

## Interrupted implementation state

The implementation was stopped at:

```text
dreamworkerln/serialterminal/dev@a131ac14ea5956d4511c0695aeff10f1760482db
```

That checkpoint is partial and unaccepted.

### Generic implementation present

Files added/changed on the implementation path include:

```text
src/serialterminal/sweep.py
src/serialterminal/agent.py
src/serialterminal/profiles/base.py
src/serialterminal/profiles/generic.py
src/serialterminal/profiles/chatter/profile.py
src/serialterminal/profiles/chatter/sweep.py
tests/test_sweep.py
tests/test_agent_sweep.py
tests/test_chatter_sweep_adapter.py
tests/test_agent.py
```

Implemented so far:

- sweep-plan normalization;
- schema hygiene checks;
- bounded Cartesian/sample limits;
- generic `SweepJob`;
- generic `SweepJobManager`;
- one-active-sweep-per-process admission;
- bounded event ring;
- bounded terminal-job retention;
- fixed repetitions;
- deterministic ordered Cartesian traversal;
- job-local monotonic event sequence;
- cursor/window reads;
- terminal job close;
- cancellation state;
- profile-owned adapter registry;
- capability-limited adapter context restricted to declared sessions;
- session mutation ownership;
- external mutation rejection for owned sessions;
- `sweep_start`;
- `sweep_observe`;
- `sweep_cancel`;
- `sweep_close`;
- asynchronous JSONL handling for `sweep_observe`;
- forensic `[SWEEP]` event records;
- initial Chatter reliable-USER adapter;
- initial generic/ownership/adapter regression tests.

### Schema hygiene implemented before job creation

The generic plan normalizer currently rejects at least:

- duplicate axis names;
- axis/constant name collisions;
- empty axis values;
- invalid/non-positive repetitions;
- excessive axis count;
- excessive serialized plan size;
- excessive Cartesian/sample count.

These checks are synchronous before a sweep job is created.

### Chatter adapter draft

The first adapter is registered as:

```text
chatter.reliable_user
```

It is intentionally profile-owned rather than special-cased in the generic engine.

The draft adapter currently attempts to:

- require two already-open distinct Chatter sessions;
- settle pre-existing reliable work with `/cancel all`;
- disable diagnostic/heartbeat/echo-loop background behavior;
- establish distinct node identities;
- apply power/frequency/BW/SF;
- verify actual radio config with `/config`;
- submit one reliable USER sample;
- wait for terminal reliable settlement before the next sample;
- use `/cancel all` for bounded cancellation/cleanup;
- derive a finite settlement timeout from the actual PHY/frame airtime.

This adapter is not yet accepted because automated validation is red.

## Important implementation commit sequence

```text
c87e200d4d4ef3d43b265fb1365554084934ed00  sweep: add generic job engine
665404041dd19901a0a87802954d9a42e1611064  sweep: add Chatter reliable-user adapter
7fb27bd0e49c4efe39471cfd51f85d2a25fdebd8  sweep: expose profile adapter registry
87f5eaee7604a8e69451ad85ea9ef6f42b188cbc  sweep: keep generic profile adapter-free
d49af2f4253308af8c16ddff8ed48ef4918c118b  sweep: register Chatter adapter through profile
2dfaf0410b3784f141ac377f70190ed9e1971f6a  sweep: scope adapter context per job
508783a33610e8ba052c14effe16eb867fe806d4  sweep: integrate jobs with agent session ownership
5eb1f2c9dbcdfbf00a83181ee53042f090374bb4  sweep: join retained workers on shutdown
e4ab9ff95da04dba22356f62a6ee75a1ae324343  test: cover generic sweep job semantics
f5c88f079f391969570b87719e276c1b74f40d77  test: cover sweep ownership and async observe
73daf7d31c40fb9f5187f9a48404aaa49c068b1a  test: cover Chatter sweep settlement boundary
eaca564106be36788e20cff2072c013243d9883d  test: fix sweep lint imports
027a8045415d6ce904c6e31e44a8efc95cd5e0f2  test: fix sweep lint imports
ec05bfd5b068eef5a465397325fa6ab678a3970b  test: align agent shutdown fake with sweep hooks
f942ff927ed540fbe34e40bd63ed60eb518adbef  sweep: parse canonical Chatter saved values
a131ac14ea5956d4511c0695aeff10f1760482db  test: mirror firmware canonical radio formatting
```

Documentation after implementation stop:

```text
c88cf93bb56a1c734d6f9ae7a8fc83cc71690bbe  docs: record interrupted sweep implementation
c263a7f90c17012141e52bca673d64e76edd2be3  docs: mark sweep implementation interrupted
```

No code implementation occurred after `a131ac14...`.

## Firmware reference checked

The implementation inspected:

```text
dreamworkerln/lora-sack-protocol/dev_chat_ack@c95e56c4f93c1f97bd10da7a56f78be151d4b9d0
```

Relevant concrete firmware facts used by the adapter draft:

- reliable USER emits `DELIVERY WAIT_ACK ...`;
- terminal success emits `DELIVERY ACK ...`;
- terminal failure emits `DELIVERY FAILED ...`;
- `/cancel all` emits a DELIVERY CANCEL result;
- `/config` emits `[SYS] CFG RADIO power=... freq=... sf=... bw=...`;
- successful radio setters emit `POWER/FREQ/SF/BW ... SAVED`;
- firmware `formatMilli()` removes trailing zero groups, so values such as:
  - `470.000` are printed as `470`;
  - `500.000` are printed as `500`.

This formatting detail exposed the final currently failing unit test.

## Validation actually run

### GitHub Actions 36283994197

Checkpoint:

```text
dev@73daf7d31c40fb9f5187f9a48404aaa49c068b1a
```

Result:

- compile PASS;
- ruff FAIL;
- only two unused imports in new tests;
- complexity/tests skipped after static-analysis failure.

Those imports were removed.

### GitHub Actions 36284047762

Checkpoint:

```text
dev@027a8045415d6ce904c6e31e44a8efc95cd5e0f2
```

Result:

- compile PASS;
- ruff PASS;
- complexity PASS;
- pytest: **1 failed, 182 passed**.

Failure was existing shutdown fake drift:

```text
_BlockingObserveManager
```

did not implement the newly added:

```text
cancel_sweeps()
join_sweeps()
```

The test double was updated at:

```text
ec05bfd5b068eef5a465397325fa6ab678a3970b
```

### GitHub Actions 36284195278

Final implementation checkpoint:

```text
dev@a131ac14ea5956d4511c0695aeff10f1760482db
```

Result:

- compile PASS;
- ruff PASS;
- complexity PASS;
- pytest: **1 failed, 182 passed**.

Current remaining failure:

```text
tests/test_chatter_sweep_adapter.py::
test_apply_then_verify_issues_config_only_after_saved_transitions
```

Observed failure:

```text
serialterminal.sweep.SweepPhaseTimeout:
sweep adapter phase timed out: apply
```

This appeared after changing the test fake to mirror firmware canonical radio formatting.

No further debugging was performed because the operator explicitly requested a stop.

## Validation NOT performed

- no green full repository CI for the sweep implementation;
- no accepted BASE..HEAD deletion review;
- no final function-definition before/after regression review;
- no final comment-deletion review;
- no hardware validation;
- no real Chatter sweep;
- no BLE/USB/serial device connection;
- no update of hardware-executor branch;
- no claim that the current sweep API is stable or ready.

## Documentation still intentionally incomplete

The implementation was stopped before final contract documentation.

The following source-development docs were **not yet updated to describe the implemented API exactly**:

```text
AGENT_API.md
ARCHITECTURE.md
LOGGING.md
.agents/skills/serialterminal-agent/SKILL.md
```

Do not blindly document the current code as accepted API.

First fix/validate the implementation. Then compare actual accepted behavior with TODO_028 and update those docs to the exact final contract.

## Known implementation risks to review on resume

The immediate known blocker is the single failing Chatter adapter test.

After that, still explicitly review:

- strict API type/range validation for all new sweep request fields;
- ownership atomicity/races;
- external mutation admission vs queued side effects;
- ownership release on every terminal/error/shutdown path;
- shutdown ordering and worker lifetime;
- cancellation convergence and cleanup timeout behavior;
- coherent event/state/progress snapshots;
- cursor off-by-one boundaries;
- terminal eviction and explicit close behavior;
- whether the Chatter sample correlation can accidentally bind to unrelated reliable telemetry;
- whether setup/cleanup command result matching is robust across both BLE and serial Chatter streams;
- whether the airtime-derived settlement timeout is conservative for every legal requested PHY;
- whether the first adapter needs any additional source-side state barrier before radio mutation.

Do not turn any of these into generic RF analytics.

## Immediate resume procedure

1. Read root `AGENTS.md`.
2. Read `HANDOFF_INDEX.md`.
3. Read this `HANDOFF_002.md`.
4. Read `TODO_INVENTORY.md`.
5. Read `todos/TODO_028_GENERIC_SWEEP_AGENT_API.md`.
6. Refetch actual `dev`; do not assume this snapshot is the current branch head.
7. Reproduce GitHub Actions failure `36284195278`.
8. Debug only the narrow canonical-number formatting/parser/fake interaction first.
9. Keep the generic-vs-adapter architecture unchanged unless the failure proves a real contradiction.
10. Run targeted sweep tests.
11. Run full repository CI.
12. Perform the source-change gate required by `AGENTS.md`:
    - review BASE..HEAD diff;
    - inspect all deletions;
    - compare function definitions before/after;
    - verify comments were not unintentionally removed/rewritten.
13. Only after a green accepted implementation:
    - update `AGENT_API.md`;
    - update `ARCHITECTURE.md` if needed;
    - update `LOGGING.md` for final `[SWEEP]` semantics if needed;
    - update `.agents/skills/serialterminal-agent/SKILL.md`;
    - update TODO_028/inventory status.
14. Do not run a hardware sweep unless the operator explicitly starts a separate hardware task.

## Current task status

```text
TODO_028:
  PARTIAL / IMPLEMENTATION STOPPED

implementation checkpoint:
  dev@a131ac14ea5956d4511c0695aeff10f1760482db

latest implementation CI:
  GitHub Actions 36284195278
  FAIL
  compile PASS
  ruff PASS
  complexity PASS
  pytest 1 failed / 182 passed

hardware:
  NOT RUN
```

The correct next action is not to infer completion from the amount of code already present. Resume by reproducing and fixing the known failing adapter test, then complete the remaining validation/documentation gates.
