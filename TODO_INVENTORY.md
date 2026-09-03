# TODO inventory

This file is the authoritative current-state index for engineering TODOs in this project.

## Active

### TODO_001 — `todos/TODO_001_AGENT_INTERFACE.md`

Status: OPEN

Goal: add a generic Codex/agent interface over shared SerialTerminal session logic without duplicating Serial/BLE/SPP transports or changing normal human-console behavior.

Current state:

```text
architecture/design decisions agreed
implementation OPEN
unit/regression validation OPEN
GitHub Actions validation OPEN
hardware validation not required for task closure unless separately requested
```

Baseline:

```text
dreamworkerln/serialterminal/dev@1e2f7632e7ea6d0cd20283ef713d811ca32dd178
```

Next order:

1. implement/test shared `ManagedSession` reconnect/I/O/event core;
2. adapt existing `TerminalSession` and verify human regression suite;
3. implement `SessionManager`, JSONL `agent` frontend and per-process logging;
4. run full automated validation and record exact implementation/validation checkpoints.

## Closed

None.
