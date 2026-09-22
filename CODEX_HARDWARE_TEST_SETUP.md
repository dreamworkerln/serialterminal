# Codex hardware-test setup for SerialTerminal

This document describes the machine/workspace preparation used when Codex operates
physical LoRa-Chatter nodes through SerialTerminal and publishes immutable hardware
evidence.

It is an operator/coordinator setup document. It does not replace
`.agents/skills/node-agent/SKILL.md`, `.agents/skills/serialterminal-agent/SKILL.md`,
`AGENT_API.md`, or the node observation policies.

## 1. Repository layout

Use two independent clones:

```text
coding/python/serialterminal
    development/runtime clone
    branch: dev

coding/python/serialterminal-observations
    evidence-only independent clone
    branch: node_observations
```

Do not use a linked worktree for `serialterminal-observations`.

The hardware executor runs SerialTerminal from the main `serialterminal` clone but
publishes canonical RUN/OBS evidence to the sibling
`serialterminal-observations` clone.

## 2. Codex writable root for the evidence clone

When Codex is started with `coding/python/serialterminal` as its workspace, the
sibling evidence clone is outside the default workspace-write boundary.

Without an additional writable root, Codex may ask for approval for every attempted
creation/update under:

```text
coding/python/serialterminal-observations/observations/
coding/python/serialterminal-observations/runs/
```

Configure the sibling clone as an additional writable root in the machine-local
Codex config.

For the current workstation layout:

```toml
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
writable_roots = [
    "/home/dream/coding/python/serialterminal-observations",
]
```

The absolute path is machine-specific. On another workstation, use the actual
absolute path of its independent `serialterminal-observations` clone.

If `[sandbox_workspace_write]` already exists, add `writable_roots` to that
existing table instead of creating a duplicate TOML table.

Restart the Codex instance after changing its sandbox configuration so the new
workspace policy is applied.

This writable-root rule exists only to allow canonical evidence publication to the
approved sibling clone. It does not authorize source changes, arbitrary filesystem
writes, or changes to `REVIEW_STATE.md`.

Git metadata writes and network access may still be separate sandbox/approval
boundaries. Do not weaken global sandbox/network policy merely to avoid those
prompts.

## 3. One long-lived SerialTerminal agent per hardware run

A hardware run should normally use one long-lived process:

```bash
python3 serialterminal.py agent --log /tmp/<run-topic>.log
```

Start it once before discovery and keep it alive through:

```text
discover
-> open sessions
-> preflight
-> measured scenarios
-> cleanup
-> close sessions
-> terminate agent
```

Send JSONL requests to the stdin of the same process and correlate responses by
request id.

Do not use per-command pipelines such as:

```bash
printf '%s\n' ... | python3 serialterminal.py agent
```

as the normal hardware-run workflow. Repeated short-lived agent processes cause
unnecessary transport reconnects and may also trigger repeated sandbox approvals.

`/tmp` is suitable for the temporary exact SerialTerminal run logs unless the
current sandbox explicitly says otherwise. The canonical published copy still
belongs in the sibling evidence clone according to
`NODE_OBSERVATION_RECORDING_POLICY.md`.

## 4. LoRa-Chatter transport default

For LoRa-Chatter hardware runs, the coordinator should use this default when
constructing the run-specific executor prompt:

```text
default transport = BLE
```

Use USB only when the operator explicitly requests USB or the concrete scenario
explicitly requires it.

Do not silently fall back from BLE to USB when the run contract did not authorize
that fallback. Report the appropriate BLOCKED/INCONCLUSIVE boundary instead.

When BLE is used, follow the Bluetooth/audio preflight in
`.agents/skills/node-agent/SKILL.md`.

## 5. Separation of responsibilities

Machine setup:

```text
operator / coordinator
    prepares independent evidence clone
    configures Codex writable root
    starts the hardware task with the intended transport contract
```

Hardware executor:

```text
uses one long-lived SerialTerminal agent
interacts with physical nodes
collects exact evidence
publishes append-only RUN/OBS
does not modify source
does not flash unless explicitly authorized
does not modify REVIEW_STATE.md
```

Run-specific acceptance criteria still belong in the delegated hardware-test prompt.
Do not turn this setup document into a scenario-specific test script.
