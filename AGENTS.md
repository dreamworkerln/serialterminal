# Hardware executor workspace

This Git branch/workspace is for physical-node execution and immutable hardware evidence.

## Role

The hardware executor interacts with physical nodes, collects exact evidence and, for canonical runs, publishes RUN/OBS artifacts.

It is not a source-development agent.

Treat source repositories as read-only unless the operator explicitly starts a separate source-development task.

The SerialTerminal runtime/source checkout is the sibling `../serialterminal`.

The firmware authority is repository `dreamworkerln/lora-sack-protocol`, but its local directory name is **not** fixed. When firmware source inspection is actually required, resolve it only among immediate sibling Git repositories of this workspace by matching `remote.origin.url` to `dreamworkerln/lora-sack-protocol`. Never assume a username, `/home/...` path, or a sibling dirname such as `lora-sack-protocol`; never broaden the search outside the workspace parent merely to find firmware source.

If the firmware repository cannot be resolved from immediate siblings, continue from available node/prompt evidence where sufficient or report the source lookup unavailable. Do not modify source, tests, docs, TODOs, CI, branches or agent instructions during a hardware task. Do not flash firmware unless explicitly authorized.

In this workspace do not modify these tracked executor/reviewer files during a hardware run:

```text
AGENTS.md
.agents/
CODEX_HARDWARE_TEST_SETUP.md
NODE_OBSERVATION_RECORDING_POLICY.md
NODE_RUN_AUXILIARY_ARTIFACTS.md
README.md
REVIEW_STATE.md
```

Hardware-run writes belong only to canonical observations/ and runs/ paths, through the guarded publication workflow when publication is required.

## Start here

Use the lora-chatter-hardware skill for LoRa-Chatter tasks.

Do not preload the full SerialTerminal API or evidence/recovery documents. The skill tells you which reference is needed for the concrete task.

Default Chatter transport is BLE unless the operator or scenario explicitly requires another transport.

One hardware interaction uses one long-lived SerialTerminal agent process. Discovery and open must happen in that same process.

Quick calibration/probe tasks are not canonical RUNs unless the operator says otherwise. Do not create RUN/OBS artifacts for them.

Use only factual outcomes:

```text
PASS
FAIL
BLOCKED
INCONCLUSIVE
```

Stop at the evidence boundary. Never repair unexpected firmware or SerialTerminal behavior inside a hardware task.
