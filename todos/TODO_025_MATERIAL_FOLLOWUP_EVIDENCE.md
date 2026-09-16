# TODO_025 — Persist material follow-up evidence used by hardware reports

Status: PARTIAL

## Purpose

Ensure that a follow-up hardware run or isolated reproduction materially used to support a published conclusion remains independently reviewable instead of existing only in temporary local storage.

## Live finding checkpoint

Published report:

```text
node_observations@649352f2a53329c4dbed933b586822e306d0916a
runs/RUN_20260914T235131Z_radio-interface-smoke/REPORT.md
```

The report correctly publishes the main two-node forensic/console logs, but also relies on an isolated follow-up statement:

```text
a fresh single-session /help was complete
```

and explicitly says that the isolated follow-up `/help` run was retained in `/tmp` only and is not part of the published bundle.

That does not invalidate the exact main-run evidence, but a future reviewer cannot independently inspect the ancillary run that supports the comparison between burst behavior and isolated behavior.

## Target behavior

- Exploratory temporary runs may remain unpublished if they are not used as durable evidence.
- Any follow-up run, reproduction or control case materially cited to support a published diagnosis/verdict/comparison must have persistent exact evidence.
- A distinct follow-up/control execution that materially affects the conclusion should be published as its own canonical RUN/OBS identity and cross-referenced from the primary report.
- Exact same-run diagnostic captures that are not SerialTerminal's two canonical logs may be persisted under the bounded optional `artifacts/` namespace of that RUN.
- Do not copy reconstructed snippets in place of exact SerialTerminal logs or exact diagnostic captures.
- Temporary `/tmp` evidence may be deleted after publication only after every materially cited artifact has a durable canonical home.

## Partial implementation checkpoint

Optional same-run auxiliary artifact publication is implemented and validated:

```text
implementation:      dev@a7e567783169cbd0ba626e0dc809960e83e55230
follow-up fix/tree:  dev@4e8ac48e39232d75c774c87d9f1878a3ffb242b7
GitHub Actions:      35039172751 SUCCESS
```

`commit-node-run` now accepts zero or more regular files below:

```text
runs/RUN_<stamp>_<topic>/artifacts/
```

while preserving all existing RUN invariants:

- the four canonical RUN members remain required;
- `MANIFEST.json` schema v1 and its canonical `files` mapping remain unchanged;
- auxiliary files outside `artifacts/` remain rejected;
- artifact symlinks are rejected;
- auxiliary files are staged and published atomically with the owning RUN;
- safe retry of a local-ahead publication commit includes its auxiliary artifacts;
- an artifact-only later append to an already published RUN is not accepted as a complete RUN publication.

The durable contract is documented in `NODE_RUN_AUXILIARY_ARTIFACTS.md`. In particular, support for `artifacts/btmon.log` does **not** make `btmon` automatic: the publication helper never launches diagnostic tools. `btmon` or another capture is created only when the concrete hardware task explicitly requests that instrumentation.

This infrastructure unblocks `TODO_024` HCI-level isolation without forcing an exact HCI capture to remain in `/tmp`.

## Documentation / policy scope still open

Review and align the primary executor documents:

```text
NODE_OBSERVATION_RECORDING_POLICY.md
.agents/skills/node-agent/SKILL.md
```

The final policy/skill wording must make two different evidence shapes explicit:

1. a same-run auxiliary capture belongs under that RUN's optional `artifacts/` namespace;
2. a separate control/reproduction run that materially affects a conclusion gets its own canonical RUN/OBS identity and cross-reference.

Neither rule should require publication of every exploratory scratch experiment.

## Validation

- [x] guarded publication helper accepts optional same-run auxiliary regular files only under `artifacts/`;
- [x] helper regression covers exact auxiliary publication, invalid namespace rejection and push-failure retry;
- [x] full repository CI PASS for the auxiliary-artifact implementation checkpoint;
- [x] auxiliary-artifact contract explicitly says diagnostic tools such as `btmon` are opt-in, not automatic;
- [ ] primary recording policy explicitly distinguishes non-evidentiary exploratory checks from materially cited follow-up evidence;
- [ ] node-agent skill tells executor to publish a separate linked run/observation when an isolated reproduction becomes part of the conclusion;
- [ ] primary policy documents same-run auxiliary artifacts without requiring every scratch experiment to be published;
- [ ] an example multi-run investigation shows primary RUN plus separately published control/follow-up RUN with cross-reference;
- [ ] final documentation review PASS.
