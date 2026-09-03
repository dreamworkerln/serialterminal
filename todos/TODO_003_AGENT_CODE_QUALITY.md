# TODO_003 — Agent code-quality refactor

Status: OPEN

## Purpose

Reduce accidental complexity in the machine-facing agent implementation without changing the documented JSONL contract or transport/session semantics.

Baseline:

```text
dev@b6133990e020a64e59ecf76236b6c1de9f59ce5a
GitHub Actions 33783101850 SUCCESS
```

Baseline Lizard hotspots relevant to this task:

```text
SessionManager.wait_events   CCN 28  length 116
AgentProtocol._dispatch      CCN 33  length 108
run_agent                    CCN 14  length 110
```

## Scope

Implementation:

- [ ] split `SessionManager.wait_events` validation/snapshot/filter/result helpers from its wait loop;
- [ ] split per-operation JSON validation/dispatch out of `AgentProtocol._dispatch`;
- [ ] move JSONL runner lifecycle/pending-wait/stdout synchronization out of the top-level `run_agent` function;
- [ ] remove obvious dead imports encountered by Ruff where behavior is unaffected;
- [ ] explicitly review `AGENT_API.md` for consistency; do not change it unless behavior changes.

Non-goals:

- no API schema changes;
- no changes to `wait_events` cursor/filter/timeout semantics;
- no changes to response ordering guarantees or `request_id_busy` behavior;
- no new unsolicited stdout push;
- no BLE/Serial/SPP transport redesign;
- no mechanical refactor of accepted Lizard warnings solely to satisfy a number.

## Accepted Lizard warnings outside this task

The following are not refactor targets unless implementation uncovers a correctness issue:

- parameter-count warnings in constructors/cache helpers;
- `ManagedSession.events_after` filter-expression complexity;
- `DeviceSelector.choose_initial` startup/TTY state machine;
- CLI `main` explicit subcommand dispatch.

## Validation

- [ ] `python -m compileall -q src serialterminal.py tools` PASS in GitHub Actions;
- [ ] Ruff static-analysis gate PASS;
- [ ] Lizard runs and the three target hotspot metrics materially improve;
- [ ] full pytest suite PASS;
- [ ] existing agent concurrency/wait/cursor/error tests remain unchanged in observable behavior;
- [ ] `AGENT_API.md` consistency review recorded;
- [ ] exact implementation and validation checkpoints recorded here and in `TODO_INVENTORY.md`.

## Findings

None yet.

## Exact checkpoints

Implementation: OPEN
Validation: OPEN
