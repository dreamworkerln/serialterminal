# AGENTS.md

## Branch

Work on `dev` unless the task explicitly says otherwise.

Do not switch branches, merge, rebase, reset, or pull unless the task explicitly requires it.

Do not force-push.

Normal commit and push to the current development branch are allowed only when the user's task explicitly requests commit/push or explicitly requests completing the change through GitHub.

## Scope

Implement only the requested change.

Do not invent architecture, APIs, abstractions, cleanup, transport behavior, BLE behavior, or CLI behavior beyond the task.

If the task requires an architectural or semantic decision that was not specified, report the ambiguity instead of silently inventing behavior.

Do not make unrelated refactors, formatting changes, renames, or cleanup.

Keep untouched source sections unchanged whenever practical.

The related firmware repository is:

`/home/dream/coding/c++/lora-sack`

Inspect or modify that repository only when the task explicitly involves it.

When working there, follow its own `AGENTS.md` if present.

## Existing code and comments

Treat existing source comments as maintained project documentation.

Preserve existing comments unless the code or semantics they describe actually changed and the requested task requires the comment to be updated.

Do not delete, shorten, rewrite, simplify, relocate, or reformat comments merely for style, conciseness, cleanup, or because the comment appears obvious.

When code is moved or extracted into a helper, preserve its associated comments when applicable.

Before finishing an edit, review the diff specifically for unintended removed or modified comment lines.

Any change to an existing comment should be justified by a semantic change in the requested task.

## New source comments

Write new explanatory source comments in Russian while preserving established Python identifiers, BLE terminology, UUIDs, transport names, API names, protocol terms, and other technical terminology where translating them would reduce clarity.

Prefer comments that explain:

* why a non-obvious implementation exists;
* a contract or invariant that future changes must preserve;
* transport ownership, lifecycle, concurrency, buffering, ordering, or cleanup assumptions;
* BLE subscription or notification behavior;
* non-obvious failure modes;
* why a simpler-looking implementation would be incorrect.

Do not add comments that merely narrate obvious adjacent code.

Do not put temporary task names, branch names, Codex instructions, review-round labels, or development-history notes into long-lived source comments unless that historical information represents a permanent compatibility constraint.

New comments should read as maintained engineering documentation, not as notes from the current coding session.

## Local changes

Before editing, check:

`git branch --show-current`

`git status --short`

If the working tree contains unexpected local changes, do not overwrite or discard them. Report them.

Do not modify, stage, delete, or clean unrelated untracked files.

Only stage files intentionally changed by the current task.

Never use broad cleanup commands such as `git clean` unless explicitly requested.

## Project structure

This repository contains the host-side serial/BLE terminal and transport code used with the LoRa SACK Chatter firmware.

Important transport concepts include:

* the common `Transport` abstraction;
* USB serial transport;
* BLE transport;
* chat and telemetry streams;
* background telemetry handling.

Preserve the transport abstraction unless the task explicitly requires changing it.

Do not couple UI behavior directly to transport-specific implementation when the existing abstraction can express the behavior.

Do not silently change BLE UUIDs, stream semantics, connection behavior, or transport contracts.

## Agent interface documentation

[AGENT_API.md](AGENT_API.md) is the canonical repository documentation for the machine-facing SerialTerminal JSONL interface. It owns the API schema, operations, request/response semantics, errors, session/cursor behavior, concurrency guarantees, logging contract, and CLI invocation.

The active generic SerialTerminal agent skill is [.agents/skills/serialterminal-agent/SKILL.md](.agents/skills/serialterminal-agent/SKILL.md).

It is a concise operational entry point for an agent. From its location it links back to `../../../AGENT_API.md` and must not duplicate or redefine the full JSONL contract. If the skill and `AGENT_API.md` ever disagree about SerialTerminal behavior, `AGENT_API.md` is the source of truth and the skill must be corrected.

The active project-specific LoRa-Chatter node skill is [.agents/skills/node-agent/SKILL.md](.agents/skills/node-agent/SKILL.md).

Keep this node skill in the `serialterminal` repository so it remains available independently of which branch or worktree of `lora-sack-protocol` is currently selected. It contains class-level Chatter commands, LoRa/echo/reboot behavior, radio diagnostics, reusable fault/recovery guidance, and node-level acceptance rules. It must not store concrete node IDs, MAC/BLE addresses, USB device paths, current measurements, current lab topology, or other instance-specific run state. It must use the generic SerialTerminal API through `AGENT_API.md`/the SerialTerminal skill rather than redefining that API.

[NODE_SKILL_LEARNING_POLICY.md](NODE_SKILL_LEARNING_POLICY.md) defines how hardware observations are collected and how a reviewer may promote reusable knowledge into the node skill. Local executor agents should report anomalies and collect evidence, but must not automatically rewrite the node skill from a single hardware run unless the task explicitly assigns them the reviewer role.

For every source-code change, explicitly review both `AGENT_API.md` and `.agents/skills/serialterminal-agent/SKILL.md` for consistency with the changed generic SerialTerminal behavior.

If the change affects the agent-facing API, session semantics, discovery/open/send/receive behavior, streams, errors, logging, CLI invocation, or the recommended generic agent workflow, update the affected generic documentation in the same task. Do not leave either active generic document describing behavior that no longer matches the code.

Review `.agents/skills/node-agent/SKILL.md` when a change affects how an agent should operate, observe, or validate LoRa-Chatter nodes. Do not update it mechanically for generic API changes unless its project-specific guidance actually became inaccurate.

## BLE behavior

The Chatter firmware exposes separate BLE streams for human chat output and machine telemetry.

Preserve independent stream handling and subscription behavior.

Do not merge chat and telemetry streams merely for implementation convenience.

When changing BLE receive, notification, scanner, or connection behavior, preserve existing transport contracts unless the task explicitly changes them.

Do not hard-code device-specific assumptions beyond what is already established by the project unless the task requires it.

## Validation

Use the fastest validation that reasonably covers the requested change before commit.

For routine Python changes, normally run the relevant pytest tests.

When the change affects broadly shared behavior, transport abstractions, BLE behavior, scanner behavior, terminal behavior, or multiple modules, run the full test suite:

`pytest -q`

For syntax/import validation when appropriate, use:

`python -m compileall -q src serialterminal.py tools`

Do not automatically run unrelated tests when a narrow targeted test is sufficient during development.

Before commit/push, ensure the relevant tests for the changed behavior pass.

GitHub Actions is the authoritative clean-environment validation after push.

Never claim a test, compile check, or other validation was executed if it was not actually run.

## Test expectations

When modifying behavior that already has tests, update or extend those tests as part of the task when needed.

Prefer deterministic tests.

Do not weaken, delete, skip, or broadly relax existing tests merely to make a change pass.

Do not replace meaningful assertions with weaker assertions unless the requested behavior explicitly changed.

When fixing a bug, add or update a regression test when practical.

When changing scanner, BLE, transport, or terminal behavior, verify both the changed path and relevant existing behavior.

## Hardware interaction

Do not assume physical hardware is available unless the task explicitly says it is.

Do not claim USB or BLE hardware behavior was tested if only mocks or unit tests were run.

Hardware smoke testing may involve the related firmware repository:

`/home/dream/coding/c++/lora-sack`

Only perform hardware-facing actions when explicitly requested.

Do not flash devices, open serial ports, connect to BLE devices, or run long-lived interactive hardware sessions unless the task explicitly requires it.

## Git operations

Before committing:

* inspect `git status --short`;
* review the relevant diff;
* confirm that only intended files are staged;
* run the relevant local validation.

When commit and push are explicitly requested:

* create a normal commit with a concise task-specific message;
* push normally to the current development branch.

Never use:

* `git push --force`;
* `git push --force-with-lease`;
* `git reset --hard`;
* history rewriting;

unless the user explicitly requests the specific destructive operation.

If a push is rejected because the remote branch changed, do not automatically rewrite, reset, merge, or rebase history.

Fetch and inspect the divergence first, then report the situation or follow explicit task instructions.

## GitHub Actions

GitHub Actions is the authoritative clean-environment validation after push.

The current CI performs clean-environment Python validation, including compile checks and pytest.

A successful local test does not imply that CI succeeded.

When the task includes completing a change through GitHub and the environment provides a way to inspect the resulting workflow, check the relevant GitHub Actions result when practical.

If CI fails:

* identify the failing step;
* distinguish failures introduced by the current change from unrelated infrastructure problems;
* do not make unrelated code changes merely to make CI green.

## Reporting

At the end of a task, report concisely:

* files changed;
* important implementation decisions;
* tests or validation commands actually executed;
* validation results;
* hardware validation performed, if any;
* commit SHA, if a commit was created;
* push result, if a push was performed;
* GitHub Actions result, if it was checked.

Do not claim work that was not performed.
