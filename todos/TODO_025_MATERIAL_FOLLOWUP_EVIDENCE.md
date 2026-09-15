# TODO_025 — Persist material follow-up evidence used by hardware reports

Status: OPEN

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
- Prefer publishing such a follow-up as its own canonical RUN/OBS identity and cross-referencing it from the primary report, rather than silently broadening the existing manifest schema.
- Do not copy reconstructed snippets in place of exact SerialTerminal logs.
- Temporary `/tmp` evidence may be deleted after publication only after every materially cited artifact has a durable canonical home.

## Documentation / policy scope

Review and align:

```text
NODE_OBSERVATION_RECORDING_POLICY.md
.agents/skills/node-agent/SKILL.md
```

The policy should make the boundary explicit: `REPORT.md` may summarize exploratory checks, but a claim that affects verdict/root-cause isolation/acceptance must point to persisted evidence if it depends on a separate run.

## Validation

- [ ] policy explicitly distinguishes non-evidentiary exploratory checks from materially cited follow-up evidence;
- [ ] node-agent skill tells executor to publish a separate linked run/observation when an isolated reproduction becomes part of the conclusion;
- [ ] no requirement is added to publish every scratch experiment;
- [ ] an example multi-run investigation shows primary RUN plus separately published control/follow-up RUN with cross-reference;
- [ ] documentation review PASS.
