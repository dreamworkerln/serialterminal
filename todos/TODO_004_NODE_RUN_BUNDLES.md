# TODO_004 — Automated node run bundles

Status: DEFERRED

## Purpose

Automate preservation and publication of complete hardware-run evidence so that a later reviewer can inspect a run directly from GitHub without requiring manual copy/paste of the executor report or SerialTerminal logs.

Planning baseline:

```text
dev@fe6ad62a1d72daf2b385e6abc980d633a883f270
```

## Return condition

Start implementation only after the SerialTerminal observation/logging refactor has an accepted `dev` checkpoint that provides both:

- one canonical agent observation API returning raw forensic events and completed logical firmware lines;
- a companion human-oriented SerialTerminal console logfile generated from the same canonical line/session model.

Record the exact accepted dependency checkpoint before implementation begins.

This TODO may continue to receive design clarifications while `DEFERRED`; design-only edits do not mean implementation has started.

## Current problem

The existing observation workflow intentionally stores a short factual `OBS_*.md` record in the append-only `node_observations` branch, while the full executor report and the complete SerialTerminal run log remain local.

As a result, review currently requires manual transfer of:

- the executor's full final report;
- the forensic SerialTerminal logfile;
- the human-readable SerialTerminal console logfile.

That manual copy/paste step should be removed without weakening the current append-only observation model.

The current `scripts/commit-node-observation` helper intentionally accepts only untracked `observations/OBS_*.md` files. Therefore an untracked `runs/` tree currently makes that helper refuse publication. TODO_004 must define coexistence rules for pending observation-only records, pending run bundles, interrupted bundle creation, and local commits whose push did not complete.

## Target storage layout

Run evidence remains in the existing `node_observations` orphan branch and independent sibling clone.

Target layout:

```text
observations/
    OBS_YYYYMMDDTHHMMSSZ_<topic>.md

runs/
    RUN_YYYYMMDDTHHMMSSZ_<topic>/
        MANIFEST.json
        REPORT.md
        serialterminal.log
        serialterminal.console.log
```

The run bundle is the complete immutable execution artifact. An observation is a concise factual/reviewer record and is not required merely to duplicate the report.

A hardware run therefore has two valid publication shapes:

```text
run with observation:
    observations/OBS_<stamp>_<topic>.md
    runs/RUN_<stamp>_<topic>/...

run without standalone observation:
    runs/RUN_<stamp>_<topic>/...
```

When an observation belongs to a run, the observation and run use the same `<stamp>_<topic>` identity.

A run without an observation must be explicit in `MANIFEST.json`; absence of an observation must never be inferred silently from a missing file.

## Artifact roles

### `serialterminal.log`

Exact forensic SerialTerminal run logfile.

It is the API/transport source of truth: requests/responses, raw RX chunk boundaries, `data_b64`, session sequence numbers, state/TX records and errors.

Do not post-process or normalize it during bundling.

### `serialterminal.console.log`

Exact companion human-console logfile produced by SerialTerminal for the same run.

It is the presentation/audit view of what a human would have typed/seen. It does not replace forensic or protocol evidence. The executor copies the file emitted by SerialTerminal; bundle publication must not reconstruct it from the forensic log.

### `REPORT.md`

Complete curated executor report for the hardware task.

It is not a raw execution log and not a dump of all JSON evidence. It records:

- exact task/result and source revisions actually known;
- relevant discovered hardware/session context;
- what was executed;
- validation/verdict per requested scenario;
- important anomalies or limitations;
- final hardware/session state;
- pointers to the persistent evidence artifacts.

`REPORT.md` is written before the executor sends its final user-facing response. The final chat response summarizes the persisted report rather than creating an independent second narrative.

### `OBS_*.md`

Short factual observation according to `NODE_OBSERVATION_RECORDING_POLICY.md`.

It answers "what did this run establish or observe?", not "what steps did the executor perform while working?".

Typical content:

- task and result;
- exact SerialTerminal and firmware revisions when known;
- compact setup/stimulus needed to understand the evidence;
- key observed evidence;
- anomalies/conflicts;
- final state;
- pointer to the matching run bundle when the observation belongs to a run.

Observation remains reviewer/learning input. It must not grow into a duplicate of `REPORT.md` or the logs.

A routine run may legitimately have no standalone observation when the executor explicitly records that decision in the manifest/report and the recording policy says no observation is required. Conversely, FAIL/BLOCKED/anomaly/fault/recovery or otherwise reusable evidence should continue to produce an observation according to the observation policy.

## Agent/executor versus publication helper

The executor owns all semantic decisions and creates all artifact contents.

Executor responsibilities:

```text
hardware execution
    -> close/finalize SerialTerminal run
    -> write REPORT.md
    -> decide whether an OBS record is required by policy
    -> write OBS_*.md when required
    -> copy exact forensic logfile
    -> copy exact console logfile
    -> write MANIFEST.json
    -> leave a complete publishable run bundle in the observation clone
```

The publication helper is intentionally dumb and strict.

`commit-node-run` must never:

- invent, summarize or reinterpret evidence;
- generate or repair `REPORT.md`;
- generate or repair an observation;
- choose which local SerialTerminal logfile belongs to the run;
- copy/move source logs into a bundle;
- guess source revisions;
- edit an incomplete bundle into a complete one.

Its role is only:

```text
validate already prepared artifacts
    -> stage exact allowed paths
    -> commit
    -> normal push
    -> verify local/remote publication state
```

The same principle remains true for `commit-node-observation`: the agent creates the observation; the helper validates and publishes it.

## Bundle manifest

`MANIFEST.json` should be small, machine-readable, and sufficient to identify the exact run context and bundle members.

The final schema is still to be finalized during implementation, but it must represent the observation relationship explicitly.

Direction:

```json
{
  "schema": 1,
  "observed_at": "YYYY-MM-DDTHH:MM:SSZ",
  "topic": "normal-ack",
  "result": "PASS",
  "serialterminal": {
    "repo": "dreamworkerln/serialterminal",
    "sha": "<exact SHA>"
  },
  "firmware": {
    "repo": "dreamworkerln/lora-sack-protocol",
    "sha": "<exact SHA or unknown>"
  },
  "observation": {
    "state": "recorded",
    "path": "../../observations/OBS_....md"
  },
  "files": {
    "report": "REPORT.md",
    "console": "serialterminal.console.log",
    "serialterminal_log": "serialterminal.log"
  }
}
```

A valid run without observation must use an explicit form such as:

```json
"observation": {
  "state": "not-required",
  "path": null,
  "reason": "<short explicit reason>"
}
```

The helper validates the declaration but does not decide whether the reason is semantically correct; that is executor/policy responsibility.

Concrete MAC addresses, node IDs, USB paths, RSSI/SNR/Q and other run-specific instance data remain allowed inside run evidence, but should not be promoted into manifest-level identity or class-level assumptions unless a later requirement explicitly needs them.

## End-to-end workflow

Target executor flow:

```text
hardware run
    -> collect evidence through canonical SerialTerminal observation API
    -> restore/finalize hardware/session state
    -> close SerialTerminal run so both logs are final
    -> write REPORT.md
    -> optionally create OBS_*.md according to policy
    -> copy exact SerialTerminal forensic logfile
    -> copy exact SerialTerminal companion console logfile
    -> create MANIFEST.json
    -> invoke the appropriate guarded publication helper
    -> independent remote-ref verification
    -> concise final response with result, paths, commit and verification state
```

The final user-facing response is only a completion notification/pointer layer. Example:

```text
Result: PASS
Observation: observations/OBS_...      # when present
Run bundle: runs/RUN_.../
Commit: <SHA>
Remote verification: verified
```

Do not require the final chat response to reproduce full `observe.result.lines`, the entire console transcript or the forensic JSON once those exact artifacts are persisted in the run bundle.

## Guarded publication helpers

Keep two stable no-argument publication commands with separate responsibilities:

```text
python3 -I scripts/commit-node-observation
python3 -I scripts/commit-node-run
```

### `commit-node-observation`

Publishes standalone pending observations only.

It must never stage an observation that is explicitly bound to a pending run bundle.

### `commit-node-run`

Publishes complete pending run bundles and any observations explicitly bound to those runs.

One run publication commit therefore contains either:

```text
RUN bundle only
```

or:

```text
matching OBS + RUN bundle
```

Both helpers use normal push only and preserve append-only history.

## Pending artifact classification and coexistence

The observation clone is a staging area as well as an append-only published branch, so valid untracked artifacts may legitimately survive between executor runs.

Helpers must classify recognized pending artifacts instead of treating the existence of the other helper's namespace as an automatic failure.

Recognized untracked namespaces are limited to canonical paths:

```text
observations/OBS_YYYYMMDDTHHMMSSZ_<topic>.md
runs/RUN_YYYYMMDDTHHMMSSZ_<topic>/...
```

Unknown/noncanonical untracked paths still cause a guard failure. The helpers must not broaden staging to arbitrary untracked files.

Classification rules:

```text
standalone observation
    OBS not declared/bound to a run
    -> eligible for commit-node-observation

complete run without observation
    valid RUN bundle with manifest observation.state=not-required
    -> eligible for commit-node-run

complete run with observation
    valid RUN bundle + matching OBS identity + manifest observation.state=recorded
    -> eligible for commit-node-run

incomplete recognized run staging
    canonical RUN/OBS identity exists but required bundle members/links are incomplete
    -> not eligible for publication yet
    -> remains pending/untracked
```

A pending observation that declares or contains a run-bundle pointer is run-bound and must not be consumed by `commit-node-observation`, even if its run bundle is incomplete or temporarily missing members.

This prevents an interrupted run from accidentally publishing the observation separately and breaking the intended atomic OBS+RUN relationship.

## Backlog behavior

Accumulation of multiple valid pending records is expected and must be supported.

`commit-node-observation`:

- may publish one or multiple eligible standalone observations in one commit/push, preserving the existing behavior;
- ignores recognized run-bound/incomplete run staging rather than staging it;
- leaves recognized pending run artifacts untouched.

`commit-node-run`:

- may publish one or multiple complete valid run bundles in one commit/push;
- includes each run's matching observation when its manifest says `recorded`;
- ignores standalone observation-only records;
- leaves incomplete recognized run staging untouched.

If eligible items exist, recognized incomplete artifacts for some other run must not block publication of complete unrelated items.

If no eligible item exists for the selected helper, return a specific diagnostic such as:

```text
no standalone observations eligible for publication
```

or:

```text
no complete run bundles eligible for publication
```

and list recognized incomplete/pending identities when useful.

After a successful publication, the observation clone does not have to be totally free of untracked files because intentionally pending recognized artifacts may remain. Final helper verification instead means:

```text
no tracked modifications
no staged changes
published paths no longer pending
local/remote branch relationship verified
only recognized pending untracked artifacts may remain
```

## Interrupted creation and abandoned staging

It is valid for an executor crash/interruption to leave a partially constructed canonical run directory or run-bound observation.

The next unrelated executor run may create additional pending artifacts without deleting or overwriting the older staging.

Publication helpers must not repair or delete the incomplete older run. They simply leave it pending and may publish other complete eligible records.

Cleanup or intentional abandonment of stale incomplete staging is a separate explicit maintenance action; helpers must not silently delete evidence-like files.

Where practical, the executor may build a run in a temporary local staging directory and move/copy the complete final artifact set into the observation clone only after logs/report/manifest are ready. This is a convenience to reduce incomplete staging, not a correctness requirement.

## Push failure and retry semantics

A network failure can occur after Git commit creation but before the push succeeds. That state must be recoverable without manual history rewriting and without recreating evidence files.

Target helper behavior:

1. Create a local commit only from fully validated eligible artifacts.
2. Attempt normal push.
3. If push fails, report clearly that the local commit exists but remote publication is incomplete, including the exact local commit SHA and Git diagnostic.
4. Do not reset, amend, rebase, force-push or recreate the artifacts.
5. On a later helper invocation, fetch the remote ref first and classify branch state.

Allowed automatic retry state:

```text
local branch ahead of origin/node_observations
remote is not ahead
all local-ahead commits validate as append-only publication commits containing only allowed observation/run additions
```

In that state the helper should first retry normal push of the existing local-ahead commit(s). After the remote catches up, it may continue to publish newly accumulated eligible untracked artifacts in the same invocation.

Unsafe states remain hard failures:

```text
remote ahead while local has unpublished work
local/remote divergence
local-ahead commit modifies/deletes old evidence
local-ahead commit contains paths outside allowed publication namespaces
tracked/staged working-tree changes not owned by the publication flow
```

The helper must not auto-merge/rebase/reset these states.

This means a previous offline commit does not permanently wedge future publication: once connectivity returns, the guarded helper can replay the pending normal push and then drain the new backlog.

## Safety/integrity checks

Both helpers should retain the current observation helper's safety principles:

- main clone must be on `dev` and the helper file must match current `HEAD`;
- sibling observation clone must be the expected independent clone on `node_observations` with upstream `origin/node_observations`;
- no tracked modifications/deletions of historical evidence;
- no pre-existing staged changes;
- no broad `git add`;
- exact allowlist staging only;
- canonical naming;
- normal push only, never force push;
- precise diagnostics on refusal/failure.

For run publication additionally validate at minimum:

- canonical `RUN_...` naming;
- supported/parseable `MANIFEST.json`;
- non-empty `REPORT.md`;
- exact copied `serialterminal.log` exists;
- exact copied `serialterminal.console.log` exists;
- declared observation state is explicit;
- if observation is `recorded`, matching canonical OBS exists and both directions of the relationship agree;
- if observation is `not-required`, no matching observation is silently assumed;
- revision fields are present and unknown values are explicit rather than guessed;
- no old tracked run/observation artifact is modified or deleted;
- staged additions are exactly the helper-selected eligible identities.

## Where the agent rules live

TODO_004 is design/history, not the runtime instruction source for hardware executors.

After implementation the persistent rule ownership should be:

```text
NODE_OBSERVATION_RECORDING_POLICY.md
    canonical executor/storage/publication policy
    artifact roles
    when observation is required vs optional
    OBS/RUN layout
    helper selection
    backlog/incomplete/offline-push recovery semantics

.agents/skills/node-agent/SKILL.md
    concise operational instructions for a hardware agent
    create report/run artifacts
    use observe.lines vs observe.events correctly
    choose commit-node-run vs commit-node-observation
    final short response/pointers

AGENT_API.md
    generic SerialTerminal machine API and run-log semantics only
    does not own node-observation/run publication policy
```

`NODE_OBSERVATION_RECORDING_POLICY.md` remains the source of truth for executor publication behavior because `AGENTS.md` already directs hardware tasks there. The node skill should summarize and link to it rather than duplicating every guard/recovery detail.

## Append-only model

Committed observations and run bundles are historical evidence and are immutable after publication.

If a committed observation or bundle is later found to contain an error, publish a new correction observation/run rather than editing historical evidence in place.

Do not add a mutable `LATEST_RUN.md` pointer. Reviewers determine relevant runs from branch history or `runs/` contents.

## Scope

Implementation:

- [ ] record the accepted SerialTerminal observation/console dependency checkpoint before code implementation;
- [ ] finalize the run-bundle manifest schema including explicit recorded/not-required observation state;
- [ ] define canonical executor artifact creation order and run identity `<stamp>_<topic>`;
- [ ] persist the curated full executor report as `REPORT.md` before final chat response;
- [ ] copy the exact SerialTerminal forensic logfile into the bundle;
- [ ] copy the exact SerialTerminal companion console logfile into the bundle;
- [ ] create optional matching `OBS_*.md` according to observation policy;
- [ ] add the bundle pointer to a matching observation when present;
- [ ] implement guarded `scripts/commit-node-run` as validation/publication only, with no evidence creation/repair logic;
- [ ] update `scripts/commit-node-observation` classification so recognized pending `runs/` staging does not make standalone observation publication fail and run-bound observations are not published separately;
- [ ] support multiple accumulated eligible standalone observations;
- [ ] support multiple accumulated complete run bundles;
- [ ] allow recognized incomplete run staging to coexist without blocking publication of complete unrelated records;
- [ ] implement retry-safe local-ahead recovery after commit-success/push-failure;
- [ ] keep divergence/behind/unsafe local-ahead states as hard failures without merge/rebase/reset/force push;
- [ ] update helper final-state checks to allow only recognized pending untracked artifacts after successful publication;
- [ ] update `NODE_OBSERVATION_RECORDING_POLICY.md` as canonical executor/storage/publication policy;
- [ ] update `.agents/skills/node-agent/SKILL.md` with concise operational/reporting rules;
- [ ] keep `AGENT_API.md` focused on generic SerialTerminal API/log semantics and only cross-reference publication rules if needed;
- [ ] keep reviewer/learning responsibilities separate from executor evidence capture;
- [ ] document the final recovery/review workflow.

Non-goals:

- do not implement or redesign the SerialTerminal `observe` API in this TODO;
- do not implement a second logical-line assembler for bundle generation;
- do not reconstruct `serialterminal.console.log` from the forensic log if SerialTerminal already emitted the companion file;
- do not make publication helpers create/repair/interpret reports, observations or evidence;
- do not merge chat and machine telemetry semantics;
- do not change firmware protocol behavior;
- do not automatically promote run findings into `.agents/skills/node-agent/SKILL.md`;
- do not create mutable latest-run state;
- do not store run-specific device identity as reusable class-level configuration;
- do not silently delete abandoned/incomplete pending staging;
- do not auto-resolve Git divergence by merge/rebase/reset/force push.

## Validation

Required validation before `CLOSED`:

- [ ] deterministic tests for bundle naming and manifest validation;
- [ ] deterministic tests for explicit observation `recorded` and `not-required` forms;
- [ ] deterministic tests that a matching run-bound OBS cannot be consumed by `commit-node-observation`;
- [ ] deterministic tests that pending canonical `runs/` files do not make `commit-node-observation` reject otherwise eligible standalone observations;
- [ ] deterministic tests that standalone pending observations do not make `commit-node-run` reject otherwise complete runs;
- [ ] deterministic tests for multiple accumulated standalone observations in one publication;
- [ ] deterministic tests for multiple accumulated complete runs in one publication;
- [ ] deterministic tests that incomplete recognized run A may remain while complete run B is published;
- [ ] deterministic tests that unknown/noncanonical untracked files still cause refusal;
- [ ] deterministic tests that old tracked observation/run artifacts cannot be modified or deleted through either helper;
- [ ] deterministic tests for observation <-> bundle cross-reference validation;
- [ ] deterministic tests for missing/invalid `REPORT.md`, forensic log, console log and manifest;
- [ ] deterministic test: commit succeeds, push fails, local branch remains safely ahead with exact diagnostic;
- [ ] deterministic test: next invocation with restored connectivity pushes validated local-ahead publication commit and then handles newly accumulated pending artifacts;
- [ ] deterministic tests that behind/diverged/unsafe-local-ahead states refuse without destructive recovery;
- [ ] helper success paths stage exactly intended additions and leave recognized unrelated pending staging untouched;
- [ ] helper final verification accepts recognized pending untracked artifacts but rejects tracked/staged residue or unknown untracked paths;
- [ ] full SerialTerminal Python test suite PASS for affected shared infrastructure;
- [ ] relevant compile/lint/static checks PASS according to current repo CI;
- [ ] one physical hardware run produces a complete run bundle automatically;
- [ ] physical validation includes at least one run with an observation and one intentional run-only bundle or deterministic equivalent for the optional-observation path;
- [ ] a reviewer can inspect a published hardware run from GitHub alone without manual copy/paste from the operator;
- [ ] independent remote verification confirms published `node_observations` commit(s);
- [ ] exact implementation and validation checkpoints are recorded here and in `TODO_INVENTORY.md`.

## Closure criteria

This TODO may move to `CLOSED` only when implementation and all required validation gates above are complete.

Expected final state:

```text
hardware executor run
    -> immutable complete RUN bundle
    -> optional concise append-only observation when policy requires it
    -> guarded validation/publication
    -> retry-safe normal push
    -> independently verified remote commit
    -> reviewer can fetch report + human console + forensic log directly from GitHub
```

Exact implementation checkpoint: not started.

Exact validation checkpoint: not started.
