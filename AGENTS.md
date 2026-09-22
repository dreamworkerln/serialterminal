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

## Architecture and profile segregation

[ARCHITECTURE.md](ARCHITECTURE.md) is the durable architecture document for ownership boundaries between generic discovery/session/transport code, controller profiles, frontends, and project-specific consuming skills.

Treat profile segregation as an architectural invariant:

* generic discovery and physical identity must remain controller-agnostic and capability-based;
* generic transports must not import concrete controller profiles, recognize controller aliases/commands, or re-export controller constants;
* `ManagedSession` and generic agent/session mechanics must not branch on concrete profile names;
* controller-specific preamble, command classification, human actions/hotkeys, presentation, console-stream selection, and BLE characteristic-to-stream layout belong to the selected `TerminalProfile`;
* profile selection is explicit and per session; do not introduce one-off generic API flags that override isolated pieces of profile behavior;
* project/protocol acceptance semantics belong in consuming skills and authoritative firmware/docs, not in generic transport/session behavior.

When a change touches discovery, profiles, transport construction, session lifecycle, human presentation, or the agent `open` path, explicitly review the dependency direction in `ARCHITECTURE.md`. If the generic core would need to know a controller advertised-name prefix, alias, command, application identity, or protocol result, first move that behavior to a profile or consuming project-specific layer unless the task explicitly changes the architecture.

## Agent interface documentation

[AGENT_API.md](AGENT_API.md) is the canonical repository documentation for the machine-facing SerialTerminal JSONL interface. It owns the API schema, operations, request/response semantics, errors, session/cursor behavior, concurrency guarantees, logging contract, and CLI invocation.

The active generic SerialTerminal source/runtime skill is [.agents/skills/serialterminal-agent/SKILL.md](.agents/skills/serialterminal-agent/SKILL.md). Keep it concise and consistent with AGENT_API.md; AGENT_API.md remains the generic API source of truth.

Physical LoRa-Chatter execution no longer bootstraps from this source workspace. Its lightweight executor instructions, evidence policy and project-specific hardware skill live on branch node_observations in the independent sibling clone serialterminal-observations.

Do not copy the full hardware executor policy back into dev. Source/runtime documentation owns API implementation truth; the observation workspace owns physical-executor operating context and evidence rules.

## Delegating hardware work to the node agent

Keep source-development and physical execution as separate Codex workspaces.

The source-development agent runs from:

```text
serialterminal/                 branch dev
```

The physical hardware executor runs from:

```text
serialterminal-observations/    branch node_observations
```

Start the hardware Codex session with serialterminal-observations as its working directory. This intentionally prevents serialterminal/AGENTS.md from entering the hardware executor's automatic project-instruction chain.

The observation workspace supplies its own short AGENTS.md plus the lora-chatter-hardware skill. The hardware executor uses ../serialterminal only as read-only runtime/API source and uses ../lora-sack-protocol as read-only firmware/protocol authority.

When preparing a hardware prompt:

* state the concrete scenario and acceptance criteria;
* identify QUICK vs canonical evidence work when useful;
* default LoRa-Chatter transport to BLE unless the operator/scenario requires another transport;
* do not paste the full AGENT_API.md, source AGENTS.md, publication policy or large scripts into the prompt;
* let the observation-workspace skill load only the task-specific references it needs;
* do not authorize source/docs/tests/TODO/CI edits or flashing unless the operator explicitly starts a separate task;
* require factual PASS | FAIL | BLOCKED | INCONCLUSIVE outcomes and evidence-boundary behavior.

The full generic API remains here in AGENT_API.md and should be read by the hardware executor only when the lightweight hardware skill cannot resolve a direct JSONL/API semantic question or structured API error.

For every SerialTerminal source-code change, explicitly review both AGENT_API.md and .agents/skills/serialterminal-agent/SKILL.md for consistency with changed generic behavior.

If a source change materially changes how physical LoRa-Chatter execution must operate or validate behavior, review the sibling observation-workspace hardware skill/policies for consistency. Updating those files is an explicit executor-infrastructure maintenance change on node_observations, not a hidden side effect of a normal hardware run.

## BLE behavior

The Chatter firmware exposes separate BLE streams for human chat output and machine telemetry.

Preserve independent stream handling and subscription behavior.

Do not merge chat and telemetry streams merely for implementation convenience.

When changing BLE receive, notification, scanner, or connection behavior, preserve existing transport contracts unless the task explicitly changes it.

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
