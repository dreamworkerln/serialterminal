# TODO inventory

This file is the authoritative current-state index for engineering TODOs in this project.

## Active

None.

## Closed

### TODO_003 — `todos/TODO_003_AGENT_CODE_QUALITY.md`

Status: CLOSED

Goal: reduce accidental complexity in agent `wait_events`, JSON operation dispatch, and JSONL runner lifecycle without changing the documented machine API.

Current state:

```text
wait_events decomposition                 CLOSED
per-operation protocol handlers           CLOSED
JSONL runner lifecycle extraction         CLOSED
dead-import/local cleanup                  CLOSED
Ruff F401/F841 hard gate                   CLOSED
AGENT_API.md consistency review            CLOSED / no content change required
GitHub Actions validation                  CLOSED / PASS
```

Complexity change:

```text
SessionManager.wait_events   CCN 28 -> 10   length 116 -> 53
AgentProtocol._dispatch      CCN 33 -> 3    length 108 -> 20
run_agent                    CCN 14 -> 3    length 110 -> 21
project Lizard warnings      15 -> 13
```

Exact checkpoints:

```text
Baseline:
  dev@b6133990e020a64e59ecf76236b6c1de9f59ce5a
  GitHub Actions 33783101850 SUCCESS

Agent orchestration refactor:
  dev@741b1d926c68ba2e8d811a201b01c235616687c8
  GitHub Actions 33785313698 SUCCESS

Accepted implementation/static-analysis checkpoint:
  dev@a74b46585b3f2c0e032b6b444b2d1089b4fde1e9
  GitHub Actions 33785730259 SUCCESS
```

### TODO_002 — `todos/TODO_002_AGENT_EVENT_WAIT.md`

Status: CLOSED

Goal: add multi-session long-poll `wait_events`, then allow ordinary JSONL commands to proceed while waits are pending, without unsolicited stdout push.

Current state:

```text
Stage 1 multi-session wait_events                 CLOSED
Stage 1 AGENT_API.md + deterministic tests        CLOSED
Stage 1 GitHub Actions validation                  CLOSED / PASS
Stage 2 concurrent pending wait requests           CLOSED
Stage 2 request-id correlation/duplicate handling  CLOSED
Stage 2 AGENT_API.md + deterministic tests         CLOSED
README agent summary synchronization               CLOSED
final implementation CI validation                 CLOSED / PASS
hardware/Codex concurrency smoke                   NOT RUN / follow-up, not closure gate
```

Exact checkpoints:

```text
Baseline:
  dev@33f9719f0dd048084a4423de83babd1ab2d76ee7
  GitHub Actions 33775808413 SUCCESS

Stage 1 accepted checkpoint:
  dev@faf42369ef58660189608ecc16befdcee59c488a
  GitHub Actions 33781308586 SUCCESS

Stage 2 implementation + AGENT_API checkpoint:
  dev@c2167099ad6b6fb9aa8ee07cdba9c724b5b368c4
  GitHub Actions 33782053409 SUCCESS

Accepted implementation/documentation checkpoint:
  dev@aaeab3002e60bd1e85595d73e3248d42c3141c1f
  GitHub Actions 33782252791 SUCCESS
```

### TODO_001 — `todos/TODO_001_AGENT_INTERFACE.md`

Status: CLOSED

Goal: provide a generic Codex/agent interface over shared SerialTerminal session logic without duplicating Serial/BLE/SPP transports or changing normal human-console behavior.

Current state:

```text
ManagedSession shared reconnect/RX/TX core       CLOSED
human TerminalSession migration                  CLOSED / regression CI PASS
SessionManager multi-device ownership            CLOSED
JSONL agent frontend                             CLOSED
cursor-based RX/wait + line/raw TX               CLOSED
unique default run logs + agent/session logging  CLOSED
API documentation                                CLOSED
hardware smoke                                   NOT RUN / follow-up, not closure gate
```

Exact checkpoints:

```text
Baseline:
  dev@1e2f7632e7ea6d0cd20283ef713d811ca32dd178

Human session-core regression checkpoint:
  dev@b9cebddfad326dc902d3adc94b773d39c0407605
  GitHub Actions 33763211529 SUCCESS

Agent implementation/tests checkpoint:
  dev@f9fae4c9ab0ae169fa44a29d6343f7425a5655a3
  GitHub Actions 33763807326 SUCCESS

Accepted documented implementation checkpoint:
  dev@396f499305c7ab1c425483b5a5f10e8521125f4f
  GitHub Actions 33764159009 SUCCESS
```

Next work is intentionally outside TODO_001 closure:

1. live Codex/JSONL smoke with actual Serial/BLE hardware and log inspection;
2. LoRa/Chatter-specific Codex skills and acceptance scenarios in `lora-sack-protocol`;
3. future MCP adapter only if required, wrapping the same `SessionManager` API.
