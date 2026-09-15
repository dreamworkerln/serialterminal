# TODO_021 — Harden node-agent executor/provenance boundary

Status: OPEN

## Purpose

Keep the physical-node operating skill focused on observable hardware behavior and evidence, while source-selection, firmware-history and deployment-provenance decisions remain outside the hardware executor unless explicitly supplied by a higher-level task.

## Finding checkpoint

```text
dev@159f7a1ab52fb8f615af33b175545f13e04dd989
```

The current node skill correctly separates generic SerialTerminal mechanics from firmware/protocol authority, but it still discusses choosing between different firmware checkpoints inside the operational skill and does not explicitly prohibit flashing as part of ordinary hardware validation.

For trustworthy evidence, a physical executor must not infer what firmware revision is deployed merely from the host source tree or from expected runtime behavior. A run manifest may use an exact firmware revision only when provenance was independently captured for the device/run; otherwise it must use the policy's unknown form.

Hardware validation also needs a durable safety boundary: observing/testing current nodes is different from changing their firmware state.

## Target behavior

- Node-agent skill clearly separates physical executor responsibilities from higher-level source/provenance selection.
- Ordinary hardware executor does not inspect/switch firmware branches or history as part of operating nodes; a separate explicit source-review task may do so outside the physical execution lane.
- Never infer deployed firmware SHA from the checked-out source branch, expected behavior, node name or a previous run.
- Published evidence records exact firmware revision only when independently captured for that deployment; otherwise records `unknown` according to observation policy.
- Node-agent workflow must not flash devices. Flashing requires a separate explicit task/procedure outside ordinary validation.
- Reboot remains allowed only when the scenario explicitly requires reboot/fault/recovery, consistent with current guidance.
- Do not encode concrete lab node identities, branch names or current topology into reusable skill text.

## Validation

- [ ] `.agents/skills/node-agent/SKILL.md` updated with the executor/provenance boundary;
- [ ] `NODE_OBSERVATION_RECORDING_POLICY.md` reviewed for consistent firmware revision language;
- [ ] `NODE_SKILL_LEARNING_POLICY.md` reviewed so reviewer/source authority remains distinct from executor duties;
- [ ] root `AGENTS.md` hardware rules remain consistent;
- [ ] documentation review verifies no concrete lab state leaked into class-level skill.