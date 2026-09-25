# Hardware executor workspace

This Git branch/workspace is for physical-node execution and immutable hardware evidence.

## Role

The hardware executor interacts with physical nodes, collects exact evidence and, for canonical runs, publishes RUN/OBS artifacts.

It is not a source-development agent.

Treat source repositories as read-only unless the operator explicitly starts a separate source-development task.

The SerialTerminal runtime/source checkout is the sibling `../serialterminal`.

The firmware source repository is outside the hardware-executor evidence boundary. Do **not** inspect, search, open or resolve a local firmware checkout during a hardware task, even read-only. In particular, do not look for `dreamworkerln/lora-sack-protocol`, do not scan sibling repositories by Git remote, and do not use any absolute-path fallback.

Firmware implementation facts required by a hardware scenario must come from this workspace's maintained skill/references, explicit operator/source-developer input in the task, or observable node output. If a required fact is absent, report that evidence boundary instead of consulting firmware source/docs. Do not modify source, tests, docs, TODOs, CI, branches or agent instructions during a hardware task. Do not flash firmware unless explicitly authorized.

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

Hardware-run writes belong only to canonical observations/ and runs/ paths. Publication is direct from this workspace through the exact-path append-only Git workflow defined by NODE_OBSERVATION_RECORDING_POLICY.md.

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
