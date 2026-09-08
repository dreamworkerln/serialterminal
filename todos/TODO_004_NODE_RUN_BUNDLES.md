# TODO_004 — Automated node run bundles

Status: IMPLEMENTED / physical validation OPEN

## Purpose

Automate preservation and publication of complete hardware-run evidence so a later reviewer can inspect a run directly from GitHub without manual copy/paste of the executor report or SerialTerminal logs.

## Dependency checkpoint

The deferred return condition is satisfied and accepted.

Accepted SerialTerminal observation/logging checkpoint:

```text
dev@e6c025805d39c95b959272cb8a9d8c74ddc6eb23
GitHub Actions 33969326449 SUCCESS
```

Live two-node smoke on that checkpoint:

```text
node_observations commit:
  d57640bd4c2cc1b871e0c5012aae41ef985dacd9

observation:
  observations/OBS_20260905T161000Z_bidirectional-user-smoke.md

result:
  PASS
  observe.result.events preserved raw chunks/data_b64
  observe.result.lines returned completed logical lines
  companion console log matched human-console I/O
```

That checkpoint provides both prerequisites required by this TODO: canonical `observe` raw+lines evidence and the companion human-console logfile from the same session/line model.

## Implemented design

Run evidence uses the existing `node_observations` orphan branch and independent sibling clone.

Canonical layout:

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

A complete run may be published as either:

```text
RUN + matching OBS
```

or:

```text
RUN only
```

RUN-only is explicit in `MANIFEST.json` with `observation.state=not-required`; a missing OBS is never silently inferred.

When an observation belongs to a run, both use the same `<stamp>_<topic>` identity and the observation contains exactly one canonical pointer:

```text
Run bundle: runs/RUN_<stamp>_<topic>/
```

## Artifact ownership

### Executor owns semantics

The hardware executor creates all evidence artifacts:

```text
hardware execution
    -> restore/finalize hardware state
    -> close sessions / finalize SerialTerminal process
    -> write REPORT.md
    -> copy exact forensic logfile
    -> copy exact companion console logfile
    -> decide whether OBS is required by policy
    -> create matching OBS when required
    -> write MANIFEST.json
    -> invoke guarded publication helper
```

The executor chooses the task verdict, relevant evidence, topic, source revisions and observation requirement.

### Publication helpers are intentionally dumb/strict

Helpers never:

- invent or reinterpret evidence;
- generate/repair `REPORT.md`;
- generate/repair an observation;
- choose a local SerialTerminal logfile;
- copy/move source logs into a bundle;
- guess source revisions;
- repair incomplete staging.

Their role is only:

```text
validate prepared artifacts
    -> exact allowlist stage
    -> commit
    -> normal push
    -> verify local/remote state
```

## Manifest schema v1

Canonical direction is now fixed in `NODE_OBSERVATION_RECORDING_POLICY.md` and enforced by code.

Recorded-observation form:

```json
{
  "schema": 1,
  "observed_at": "YYYY-MM-DDTHH:MM:SSZ",
  "topic": "normal-ack",
  "result": "PASS",
  "serialterminal": {
    "repo": "dreamworkerln/serialterminal",
    "sha": "<exact 40-hex SHA>"
  },
  "firmware": {
    "repo": "dreamworkerln/lora-sack-protocol",
    "sha": "<exact 40-hex SHA or unknown>"
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

RUN-only form:

```json
"observation": {
  "state": "not-required",
  "path": null,
  "reason": "<short explicit reason>"
}
```

Helpers validate identity, result values, exact revision form, canonical file mapping and bidirectional OBS/RUN linkage. Semantic correctness of `not-required` remains executor/policy responsibility.

## Guarded helpers

Stable no-argument commands:

```text
python3 -I scripts/commit-node-observation
python3 -I scripts/commit-node-run
```

Implementation is split into:

```text
scripts/commit-node-observation
scripts/commit-node-run
scripts/node-publication-common.py
```

Each wrapper verifies that itself and the shared publication module match current `HEAD` before loading shared logic.

### `commit-node-observation`

Publishes all eligible standalone observations in one commit/push.

It ignores recognized pending RUN staging and refuses to consume a run-bound observation.

### `commit-node-run`

Publishes all complete valid run bundles in one commit/push.

For each `observation.state=recorded` run, matching OBS is included in the same commit. RUN-only bundles are published without OBS.

## Pending/backlog coexistence

The sibling clone is both append-only branch checkout and local staging area. Recognized untracked artifacts may survive between executor runs.

Supported states:

```text
multiple standalone OBS files
multiple complete RUN bundles
incomplete old RUN staging
run-bound OBS whose RUN is incomplete
standalone OBS + RUN staging simultaneously
```

Selection rules:

```text
commit-node-observation
    -> drains eligible standalone OBS only

commit-node-run
    -> drains complete valid RUNs only
    -> includes matching recorded OBS
```

Incomplete or invalid-but-canonical run A does not block complete unrelated run B. It remains pending and is never repaired/deleted by the helper.

Unknown/noncanonical untracked paths remain a hard failure; no helper performs broad staging.

After publication, final state may still contain recognized untracked pending artifacts, but must contain no tracked modifications, no staged residue, and published paths must no longer be pending.

## Push-failure recovery

A commit may succeed locally while push fails because of network/remote failure.

Implemented recovery:

1. helper preserves the local commit and reports exact SHA/diagnostic;
2. next invocation fetches `origin/node_observations` first;
3. if remote is not ahead and local is only safely ahead, every local-ahead commit is validated as append-only publication content;
4. helper retries normal push of existing local-ahead commit(s);
5. after synchronization it may publish newly accumulated eligible untracked backlog in the same invocation.

Hard failure without automatic merge/rebase/reset:

```text
remote ahead while unpublished local work exists
local/remote divergence
unsafe local-ahead modification/deletion
local-ahead path outside publication namespaces
tracked/staged working-tree residue
```

No force push is used.

## Persistent agent rules

Runtime executor rules no longer depend on this TODO.

Authority after implementation:

```text
NODE_OBSERVATION_RECORDING_POLICY.md
    canonical storage/artifact/report/manifest/helper/backlog/recovery policy

.agents/skills/node-agent/SKILL.md
    concise hardware-agent workflow and helper selection

AGENT_API.md
    generic SerialTerminal JSONL + run-log semantics only
```

`AGENT_API.md` and `.agents/skills/serialterminal-agent/SKILL.md` were reviewed during implementation; the publication workflow is project-specific and does not change the generic machine API, so no generic API change was required.

## Implementation

- [x] accept and record SerialTerminal observe/console dependency checkpoint;
- [x] finalize manifest schema v1 with explicit `recorded` / `not-required` observation state;
- [x] define canonical `<stamp>_<topic>` identity and artifact creation order;
- [x] define curated `REPORT.md` versus concise `OBS_*.md` roles;
- [x] preserve exact forensic and companion logs as bundle members;
- [x] implement guarded `scripts/commit-node-run` as validation/publication only;
- [x] refactor `scripts/commit-node-observation` to coexist with recognized RUN staging;
- [x] prevent run-bound OBS from standalone publication;
- [x] support multiple accumulated standalone observations;
- [x] support multiple accumulated complete RUN bundles;
- [x] allow incomplete canonical staging to coexist with unrelated complete publication;
- [x] implement safe local-ahead retry after commit-success/push-failure;
- [x] keep behind/diverged/unsafe states as hard failures without destructive recovery;
- [x] allow recognized pending untracked artifacts after successful publication;
- [x] update `NODE_OBSERVATION_RECORDING_POLICY.md` as canonical executor policy;
- [x] update `.agents/skills/node-agent/SKILL.md` with concise publication/reporting rules;
- [x] extend CI compile/static-analysis/complexity scope to publication scripts;
- [x] keep reviewer/learning responsibilities separate from executor capture;
- [x] refactor publication core so TODO_004 adds no new Lizard threshold warnings.

## Automated validation

Deterministic test coverage in `tests/test_node_publication.py` currently proves:

- [x] multiple standalone observations publish together;
- [x] pending canonical RUN staging does not block standalone OBS publication;
- [x] run-bound OBS cannot be consumed by `commit-node-observation`;
- [x] complete RUN + recorded OBS publishes atomically;
- [x] RUN-only `not-required` publication works;
- [x] standalone OBS does not block RUN publication;
- [x] multiple complete RUNs publish together;
- [x] incomplete run A does not block complete run B;
- [x] invalid canonical run A does not block complete run B;
- [x] unknown/noncanonical untracked path causes refusal;
- [x] tracked historical modification causes refusal;
- [x] mismatched OBS/RUN pointer remains pending and is not published standalone;
- [x] commit-success/push-failure leaves safe local-ahead state;
- [x] restored connectivity retries old publication and then drains new backlog;
- [x] divergence after unpublished local work is a hard failure.

Repository validation checkpoint:

```text
Implementation/static-analysis checkpoint:
  dev@4d50eb1aec50bfb4a71d1d8e63f95fbc7a0f436c

GitHub Actions:
  34263084088 SUCCESS

Compile: PASS
Ruff: PASS
Tests: 106 passed
Lizard: NON-BLOCKING / exit 1 / 13 threshold warnings
         TODO_004 publication scripts add 0 warnings; warning count restored to pre-TODO baseline
```

CI includes compile, Ruff static analysis, non-blocking Lizard complexity and full pytest.

## Remaining validation

TODO remains `IMPLEMENTED`, not `CLOSED`, until production-like publication is exercised from the actual local executor/storage environment.

Still required:

- [ ] one physical hardware run creates `REPORT.md`, exact forensic log, exact console log and `MANIFEST.json` in a real `RUN_.../`;
- [ ] that run is published through `commit-node-run` with a matching observation;
- [ ] one intentional RUN-only publication is exercised physically, or an equivalent accepted hardware run explicitly uses `observation.state=not-required`;
- [ ] independent `ls-remote` verification matches the helper-reported commit SHA;
- [ ] reviewer confirms the published run is inspectable from GitHub alone without operator copy/paste;
- [ ] final physical validation checkpoint is recorded here and in `TODO_INVENTORY.md`.

## Non-goals preserved

- no redesign of SerialTerminal `observe`;
- no second logical-line assembler;
- no reconstruction of console log from forensic log;
- no helper-side evidence authoring/repair;
- no firmware protocol changes;
- no automatic learning promotion from one run;
- no mutable `LATEST_RUN.md`;
- no run-specific device identity in reusable class configuration;
- no silent deletion of abandoned staging;
- no automatic merge/rebase/reset/force-push recovery.

## Closure criteria

Close only after the remaining real hardware/publication validation gates pass.

Expected final state:

```text
hardware executor run
    -> immutable complete RUN bundle
    -> optional concise OBS when policy requires it
    -> guarded validation/publication
    -> retry-safe normal push
    -> independent remote verification
    -> reviewer fetches report + console + forensic log directly from GitHub
```

Exact implementation checkpoint:

```text
dev@4d50eb1aec50bfb4a71d1d8e63f95fbc7a0f436c
```

Exact automated validation checkpoint:

```text
GitHub Actions 34263084088 SUCCESS
```

Exact physical publication validation checkpoint: not started.
