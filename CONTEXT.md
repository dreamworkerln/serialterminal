# Current work context

Status: COMPLETED

## Current operation

Record the completed SerialTerminal agent work, post-closure physical multi-node validation, current documentation/skills/TODO state, and publish a new verified handoff snapshot.

No production source-code change is part of this operation. The current `dev` changes are documentation/history/TODO synchronization after live hardware use.

## Exact baselines / result

Operation start source: dreamworkerln/serialterminal/dev@e0d7b5f91c88f91a0d426b8048803bc188614d5a
Operation start handoff authority: dreamworkerln/serialterminal/dev_handoff@bc17b841484a5cb704874c9bea3d27325fc8e7dd
Operating-instructions sync: dreamworkerln/serialterminal/dev_handoff@f0d564763739b1846aa69cd2bcf9d5d5f4f11797
Completed source/docs: dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2
Final source/docs CI: GitHub Actions run 33801154957 SUCCESS

Important earlier implementation checkpoints:

```text
multi-session wait/concurrent JSONL accepted docs checkpoint:
  dev@aaeab3002e60bd1e85595d73e3248d42c3141c1f
  GitHub Actions 33782252791 SUCCESS

agent quality/static-analysis accepted checkpoint:
  dev@a74b46585b3f2c0e032b6b444b2d1089b4fde1e9
  GitHub Actions 33785730259 SUCCESS

closed quality inventory checkpoint:
  dev@0346825648f4bb60c81b1b37c1aee240580583de
  GitHub Actions 33785862613 SUCCESS
```

## Completed scope since previous handoff snapshot

- Added multi-session `wait_events` with independent per-session cursors and deterministic merged batches.
- `wait_events` may remain pending while ordinary JSONL commands continue; responses are correlated by request `id` and may complete out of request order.
- Preserved response-only JSONL stdout; no unsolicited push events were introduced.
- Refactored `wait_events`, protocol dispatch and JSONL runner lifecycle to reduce accidental complexity without changing the documented machine contract.
- Added conservative Ruff hard gates including unused imports/locals and advisory Lizard complexity reporting in CI.
- Fixed initial-device-selection `Ctrl+T s` scanner handling so the startup scanner hotkey works while discovery is running without concurrent BLE discovery/scanner execution.
- Added the active generic `.agents/skills/serialterminal-agent/SKILL.md`, which points to canonical `AGENT_API.md`.
- Added the active project-specific `.agents/skills/node-agent/SKILL.md` and linked it from `AGENTS.md`.
- Decided to keep `node-agent/SKILL.md` in `serialterminal` so it remains stable when `lora-sack-protocol` branch/worktree selection changes. It does not redefine the generic SerialTerminal API.
- Synchronized generic handoff/TODO management policies with the related workstreams.
- Updated README, TODO_001, TODO_002 and TODO inventory after physical hardware/Codex validation.
- `TODO_INVENTORY.md` still has `Active: None`.

## Post-closure physical hardware findings

Observed on 2026-09-03 using physical LoRa-Chatter hardware:

- one `serialterminal agent` process opened two physical BLE nodes as independent sessions;
- Codex independently used node `/help` to learn the available node command surface;
- a multi-session `wait_events` request was used;
- ordinary commands continued while that wait was pending;
- TX was issued from both physical sessions close together, exercising independent per-session TX paths;
- earlier physical node-to-node transfer and Chatter echo behavior were also observed and are documented in `.agents/skills/node-agent/SKILL.md`;
- node `1B44` was additionally observed through USB with ESP32 powered while radio-module power was intentionally absent; boot reported `RADIO UNAVAILABLE bootTxSelfTest (-5); RF disabled` and USB/ESP32 remained available.

Do not overstate the close-together TX smoke: it proves host-side multi-session/concurrent-wait/per-session-TX usability, not successful peer reception of both simultaneous LoRa transmissions. Peer delivery requires RX/telemetry evidence.

The exact process log and exact flashed firmware revision for the manual smoke were not recorded here. Do not invent them during recovery.

## Current documentation authority

- `AGENT_API.md` — canonical generic SerialTerminal JSONL contract.
- `.agents/skills/serialterminal-agent/SKILL.md` — concise generic operational workflow that points to `AGENT_API.md`.
- `.agents/skills/node-agent/SKILL.md` — project-specific observed LoRa-Chatter node/hardware workflow and findings; deliberately stored in `serialterminal`.
- `README.md` — human/agent usage summary and the post-closure hardware smoke note.
- `TODO_INVENTORY.md` plus `todos/TODO_001_AGENT_INTERFACE.md`, `todos/TODO_002_AGENT_EVENT_WAIT.md`, `todos/TODO_003_AGENT_CODE_QUALITY.md` — engineering task/history state.

Firmware/protocol source truth remains the actual relevant `lora-sack-protocol` source revision and physical hardware behavior. The node skill location does not make SerialTerminal source authoritative for Chatter firmware semantics.

## Invariants / do not change

- `dev` is SerialTerminal source authority; `dev_handoff` is recovery-only.
- Existing Serial/BLE/SPP transports remain I/O authority; agent code must not duplicate them.
- Human and agent frontends share `ManagedSession` reconnect/RX/TX behavior.
- Sticky reconnect stays bound to the selected physical identity.
- BLE streams stay separate.
- `state=queued` is queue acceptance only; `tx_state=written` is transport-write evidence only; neither proves LoRa peer delivery.
- JSONL stdout remains request-correlated response-only output.
- Ordinary JSONL commands remain serialized; pending `wait_events` is the asynchronous request mechanism.
- Different `ManagedSession` instances retain independent TX workers/queues, allowing independent physical-device TX progress.
- Do not introduce broad concurrency or MCP merely to make architecture look more asynchronous; require a concrete need.

## Validation actually completed

Final current documentation checkpoint:

```text
dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2
GitHub Actions run 33801154957 SUCCESS
```

The run completed repository CI steps including compile, static analysis, advisory complexity execution, and tests.

Post-closure hardware validation is recorded above and in the active node skill/TODO history. The manual smoke does not have a retained exact process-log identifier in this recovery state.

## Current optional follow-ups

No required SerialTerminal code work is open.

Potential future polish only when there is concrete demand:

1. map host/sandbox BLE permission failures such as `Operation not permitted` to a stable agent-facing error such as `permission_denied` instead of generic/internal failure;
2. optionally expose per-backend discovery diagnostics for partial `scope:auto` success/failure;
3. add MCP only if a real consumer requires it, wrapping the existing `SessionManager` rather than creating a parallel transport/session stack.

These are not active TODOs at this checkpoint.

## Last completed action

README, node-agent skill, TODO_001, TODO_002 and TODO inventory were synchronized with the post-closure physical multi-session/Codex validation and current skill ownership decision. Final `dev` CI is green at the exact checkpoint above.

## Next action

1. Refetch `dev` and `dev_handoff`.
2. Create `HANDOFF_003.md` as the next immutable snapshot.
3. Read back and verify it before publication.
4. Only then advance `HANDOFF_INDEX.md` to snapshot 003.

## Blockers / findings

- No required SerialTerminal implementation blocker remains.
- No active TODO remains.
- Exact hardware smoke process-log ID and exact flashed Chatter firmware revision are unknown in this handoff state and must remain explicitly unknown.
