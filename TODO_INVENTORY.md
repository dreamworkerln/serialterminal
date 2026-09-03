# TODO inventory

This file is the authoritative current-state index for engineering TODOs in this project.

## Active

None.

## Closed

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
