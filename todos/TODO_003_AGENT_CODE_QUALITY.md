# TODO_003 — Agent code-quality refactor

Status: CLOSED

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

- [x] split `SessionManager.wait_events` validation/snapshot/filter/result helpers from its wait loop;
- [x] split per-operation JSON validation/dispatch out of `AgentProtocol._dispatch`;
- [x] move JSONL runner lifecycle/pending-wait/stdout synchronization out of the top-level `run_agent` function;
- [x] remove obvious dead imports encountered by Ruff where behavior is unaffected;
- [x] explicitly review `AGENT_API.md` for consistency; no content change was needed because observable behavior did not change.

Non-goals:

- no API schema changes;
- no changes to `wait_events` cursor/filter/timeout semantics;
- no changes to response ordering guarantees or `request_id_busy` behavior;
- no new unsolicited stdout push;
- no BLE/Serial/SPP transport redesign;
- no mechanical refactor of accepted Lizard warnings solely to satisfy a number.

## Accepted Lizard warnings outside this task

The following remain intentionally outside this refactor:

- parameter-count warnings in constructors/cache helpers;
- `ManagedSession.events_after` filter-expression complexity;
- `DeviceSelector.choose_initial` startup/TTY state machine;
- CLI `main` explicit subcommand dispatch.

## Validation

- [x] `python -m compileall -q src serialterminal.py tools` PASS in GitHub Actions;
- [x] Ruff static-analysis gate PASS;
- [x] Lizard runs and the three target hotspot metrics materially improve;
- [x] full pytest suite PASS (84 tests);
- [x] existing agent concurrency/wait/cursor/error tests remain unchanged in observable behavior;
- [x] `AGENT_API.md` consistency review recorded;
- [x] exact implementation and validation checkpoints recorded here and in `TODO_INVENTORY.md`.

## Findings

The refactor reduced the target functions to:

```text
SessionManager.wait_events   CCN 10  length 53
AgentProtocol._dispatch      CCN 3   length 20
run_agent                    CCN 3   length 21
```

The project-wide Lizard warning count dropped from 15 to 13. The remaining warnings include intentionally accepted parameter-count/state-machine/filter-expression cases documented above.

The JSONL runner is now represented by the internal `_AgentJsonlRunner` object. This is an implementation boundary only: ordinary requests remain serialized by the reader, `wait_events` remains the only background request, stdout remains lock-serialized, and request/response correlation remains by `id`.

Ruff's hard gate was also extended narrowly to `F401` and `F841`, preventing unused imports and unused local variables from returning without adopting the broader style/typing/exception-policy rule set that was intentionally deferred.

## Exact checkpoints

```text
Agent orchestration refactor:
  dev@741b1d926c68ba2e8d811a201b01c235616687c8
  GitHub Actions 33785313698 SUCCESS

Dead CLI cleanup:
  dev@e18dad9b30e70d28e02d5f3726b712be08d25f6b
  GitHub Actions 33785582744 SUCCESS

Unused test import cleanup:
  dev@4930f97f5beb40c947209ca987f5fe2c7f5336a7
  GitHub Actions 33785686326 SUCCESS

Accepted implementation/static-analysis checkpoint:
  dev@a74b46585b3f2c0e032b6b444b2d1089b4fde1e9
  GitHub Actions 33785730259 SUCCESS
```

Remaining follow-ups: none required for TODO_003 closure.
