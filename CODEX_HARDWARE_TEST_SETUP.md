# Codex hardware-test workspace setup

This is the operator/coordinator setup for the dedicated physical-node executor.

It is not part of the per-run bootstrap. The executor normally receives AGENTS.md automatically and loads the lora-chatter-hardware skill only when a hardware task selects it.

## Repository layout

Use two independent sibling clones:

```text
~/coding/python/serialterminal
    branch: dev
    source/runtime

~/coding/python/serialterminal-observations
    branch: node_observations
    hardware executor workspace + evidence
```

Do not use a linked worktree for serialterminal-observations.

Start the hardware Codex session with:

```text
cwd = ~/coding/python/serialterminal-observations
```

Source-development sessions continue to start from serialterminal/.

This separation keeps serialterminal/AGENTS.md out of the automatic instruction chain for the hardware executor while preserving it as the automatic source-development contract.

## Sandbox

Use workspace-write for the hardware executor workspace.

The old configuration:

```toml
[sandbox_workspace_write]
writable_roots = [
    "~/coding/python/serialterminal-observations",
]
```

is no longer needed when the Codex working directory itself is serialterminal-observations.

If that writable_roots entry exists only for this old sibling-write arrangement, remove it. If the same table contains other deliberately authorized writable roots, keep those unrelated entries.

Do not replace it with a writable root for `../serialterminal` or for any firmware checkout. The SerialTerminal source/runtime remains read-only; firmware source is outside the hardware-executor boundary and must not be granted or sought merely for a hardware run.

Do not encode a username, absolute `/home/...` path, firmware repository location or assumed firmware sibling dirname in sandbox setup. The hardware executor must not resolve or inspect a firmware checkout.

With workspace-write, Codex can normally read outside the workspace while writes remain scoped to the workspace. If the local installation uses explicitly restricted read access, add only the minimum read permission required for the SerialTerminal sibling runtime/source; do not make it writable.

The workspace .git directory remains a protected path under the normal sandbox policy. Therefore direct Git publication can still require separate approval for metadata writes and network operations even though runs/ and observations/ are inside the writable workspace.

## Runtime invocation

SerialTerminal remains owned by the dev clone. Run it from the hardware workspace through the sibling path, for example:

```bash
python3 ../serialterminal/serialterminal.py agent --log /tmp/<unique-run-log>.log
```

Use one long-lived process from discovery through cleanup.

A log path must be unique for each hardware run/probe. Do not reuse a fixed /tmp filename across runs.

The full machine API remains:

```text
../serialterminal/AGENT_API.md
```

Do not read that entire file by default. The hardware skill contains the normal happy-path contract and points to AGENT_API.md only for direct JSONL/API questions, unusual errors or semantics not covered by the skill.

## Publication

Canonical evidence is created and published directly from this workspace:

```text
runs/RUN_<stamp>_<topic>/
observations/OBS_<stamp>_<topic>.md
```

The hardware executor does not use sibling publication scripts.

Publication uses exact-path append-only Git in the current `node_observations` clone:

```text
preflight/fetch
-> exact-path git add
-> verify staged A-only paths + diff hygiene
-> git commit
-> normal git push
-> independent git ls-remote verification
```

The detailed contract is in `NODE_OBSERVATION_RECORDING_POLICY.md`; unusual states use the skill's `references/evidence-recovery.md`.

Git metadata and network approval may still be required separately.

## Transport default

For LoRa-Chatter hardware work:

```text
default transport = BLE
```

Use USB only when the operator explicitly requests it or the concrete scenario requires it. Do not silently fall back from BLE to USB.
