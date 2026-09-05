# TODO_004 — Automated node run bundles

Status: DEFERRED

## Purpose

Automate preservation and publication of complete hardware-run evidence so that a later reviewer can inspect a run directly from GitHub without requiring manual copy/paste of the executor report or SerialTerminal logs.

Planning baseline:

```text
dev@fe6ad62a1d72daf2b385e6abc980d633a883f270
```

## Return condition

Start this TODO only after the in-progress SerialTerminal observation refactor has an accepted `dev` checkpoint that provides both:

- one canonical agent observation API returning raw forensic events and completed logical firmware lines;
- a companion human-oriented SerialTerminal console logfile generated from the same canonical line/session model.

Record the exact accepted dependency checkpoint before implementation begins.

## Current problem

The existing observation workflow intentionally stores a short factual `OBS_*.md` record in the append-only `node_observations` branch, while the full executor report and the complete SerialTerminal run log remain local.

As a result, review currently requires manual transfer of:

- the executor's full final report;
- the forensic SerialTerminal logfile;
- optionally a human-readable reconstruction of what was typed and what the node console displayed.

That manual copy/paste step should be removed without weakening the current append-only observation model.

## Target behavior

A completed hardware run should produce and publish one immutable run bundle next to its short observation record.

Target layout in the existing `node_observations` orphan branch:

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

The observation remains the concise reviewer/learning record. The run bundle contains the complete run artifacts.

## Artifact roles

### `OBS_*.md`

Short factual observation according to `NODE_OBSERVATION_RECORDING_POLICY.md`:

- task and result;
- exact SerialTerminal and firmware revisions;
- compact setup/actions/evidence;
- anomalies/conflicts;
- final state;
- pointer to the matching run bundle.

### `REPORT.md`

Full executor report for the hardware task.

It should be written before the executor sends its final user-facing response, so the persistent report is the authoritative detailed account of the run rather than a later reconstruction.

The chat response may be shorter, but it must summarize the persisted report rather than independently inventing a second result narrative.

### `serialterminal.log`

Exact forensic SerialTerminal run logfile.

Do not post-process or normalize it during bundling. It remains the transport/API source of truth.

### `serialterminal.console.log`

Exact companion human-console logfile produced by SerialTerminal for the same run.

It is a convenience view of what a human would have typed/seen in SerialTerminal and does not replace forensic evidence. The run-bundle publisher should copy the file produced by SerialTerminal rather than reconstructing console output itself.

## Bundle manifest

`MANIFEST.json` should be small, machine-readable, and sufficient to identify the exact run context and bundle members.

Initial schema direction:

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
  "files": {
    "report": "REPORT.md",
    "console": "serialterminal.console.log",
    "serialterminal_log": "serialterminal.log",
    "observation": "../../observations/OBS_....md"
  }
}
```

Concrete MAC addresses, node IDs, USB paths, RSSI/SNR/Q and other run-specific instance data remain allowed inside run evidence, but should not be promoted into manifest-level identity or class-level assumptions unless a later requirement explicitly needs them.

## End-to-end workflow

Target executor flow:

```text
hardware run
    -> collect evidence through the canonical SerialTerminal observation API
    -> write the full REPORT.md
    -> create the short OBS_*.md
    -> copy the exact SerialTerminal forensic logfile
    -> copy the exact SerialTerminal companion console logfile
    -> create MANIFEST.json
    -> guarded commit/push of observation + matching bundle
    -> independent remote-ref verification
    -> concise final response with result, paths, commit and verification state
```

The final user-facing summary should make the persistent artifacts easy to locate, for example:

```text
Result: PASS
Observation: observations/OBS_...
Run bundle: runs/RUN_.../
Commit: <SHA>
Remote verification: verified
```

## Guarded publication

Do not broaden `scripts/commit-node-observation` into an unrestricted staging helper.

Add a separate guarded helper, tentatively:

```text
scripts/commit-node-run
```

The helper should use the same safety principles as the existing observation helper:

- stable no-argument invocation suitable for one-time permission approval;
- main clone must be on `dev` and helper must match current `HEAD`;
- sibling observation clone must be the expected independent clone on `node_observations` with the expected upstream;
- tracked state must be clean;
- local observation branch must be synchronized with `origin/node_observations` before staging;
- only correctly named new observation/run-bundle artifacts may be pending;
- no broad staging;
- no modification, deletion or rewriting of old observation/run artifacts;
- normal push only, never force push;
- final clean/local-vs-origin verification after push;
- precise diagnostic text on refusal/failure.

For a completed run, the helper must validate the relationship between the new observation and run bundle before committing.

At minimum verify:

- canonical `OBS_...` and `RUN_...` naming;
- `MANIFEST.json` exists and parses;
- `REPORT.md` exists;
- `serialterminal.log` exists;
- `serialterminal.console.log` exists;
- manifest points to the matching observation;
- observation points to the matching run bundle;
- manifest revision fields are present and not silently guessed;
- no unrelated untracked files are included.

Keep `scripts/commit-node-observation` available for observation-only cases where a full run bundle is not required.

## Append-only model

Run bundles are historical evidence and should be immutable after commit, following the same principle as committed observation records.

If a committed bundle is later found to contain an error, publish a new correction record/bundle rather than editing historical evidence in place.

Do not add a mutable `LATEST_RUN.md` pointer. Reviewers can determine the latest relevant run from branch history or `runs/` contents without creating one file that every executor run rewrites.

## Scope

Implementation:

- [ ] finalize the run-bundle schema after the observation/console-log dependency checkpoint is accepted;
- [ ] add creation of `RUN_.../MANIFEST.json`;
- [ ] persist the full executor report as `REPORT.md` before final chat response;
- [ ] copy the exact SerialTerminal forensic logfile into the bundle;
- [ ] copy the exact SerialTerminal companion console logfile into the bundle;
- [ ] add the bundle pointer to the matching `OBS_*.md`;
- [ ] add a guarded `scripts/commit-node-run` publication path;
- [ ] update `NODE_OBSERVATION_RECORDING_POLICY.md` with when a run bundle is required and how it is published;
- [ ] update the active node-agent skill so hardware executor tasks publish the required artifacts automatically;
- [ ] keep reviewer/learning responsibilities separate from executor evidence capture;
- [ ] document the final manifest schema and recovery/review workflow.

Non-goals:

- do not implement or redesign the SerialTerminal `observe` API in this TODO;
- do not implement a second logical-line assembler for bundle generation;
- do not reconstruct `serialterminal.console.log` from the forensic log if SerialTerminal already emitted the companion file;
- do not merge chat and machine telemetry semantics;
- do not change firmware protocol behavior;
- do not automatically promote run findings into `.agents/skills/node-agent/SKILL.md`;
- do not create mutable latest-run state;
- do not store run-specific device identity as reusable class-level configuration.

## Validation

Required validation before `CLOSED`:

- [ ] deterministic tests for bundle naming and manifest validation;
- [ ] deterministic tests that unrelated/unexpected files are rejected by the guarded helper;
- [ ] deterministic tests that old tracked observation/run artifacts cannot be modified or deleted through the helper;
- [ ] deterministic tests for observation <-> bundle cross-reference validation;
- [ ] deterministic tests for missing/invalid `REPORT.md`, forensic log, console log and manifest;
- [ ] helper success path stages exactly the intended new observation and matching bundle;
- [ ] helper failure diagnostics are specific and preserve repository state;
- [ ] full SerialTerminal Python test suite PASS for affected shared infrastructure;
- [ ] relevant compile/lint/static checks PASS according to current repo CI;
- [ ] one physical hardware run produces an observation and complete run bundle automatically;
- [ ] a reviewer can inspect that hardware run from GitHub alone without manual copy/paste from the operator;
- [ ] independent remote verification confirms the published `node_observations` commit;
- [ ] exact implementation and validation checkpoints are recorded here and in `TODO_INVENTORY.md`.

## Closure criteria

This TODO may move to `CLOSED` only when implementation and all required validation gates above are complete.

Expected final state:

```text
hardware executor run
    -> concise append-only observation
    -> immutable complete run bundle
    -> guarded publication
    -> independently verified remote commit
    -> reviewer can fetch report + human console + forensic log directly from GitHub
```

Exact implementation checkpoint: not started.

Exact validation checkpoint: not started.
