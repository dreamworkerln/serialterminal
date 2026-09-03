# Handoff snapshot 003

```text
Snapshot: HANDOFF_003.md
Previous: HANDOFF_002.md
Created: 2026-09-03T20:18:34Z
Handoff authority: dreamworkerln/serialterminal/dev_handoff@cee6f4e7251ee1b2cd891a76fa66a1ad59c89088 (checkpoint immediately before snapshot creation)
Source checkpoints:
  Active SerialTerminal source/docs: dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2
  Multi-session wait/concurrent JSONL accepted docs checkpoint: dreamworkerln/serialterminal/dev@aaeab3002e60bd1e85595d73e3248d42c3141c1f
  Agent quality/static-analysis accepted checkpoint: dreamworkerln/serialterminal/dev@a74b46585b3f2c0e032b6b444b2d1089b4fde1e9
  Related current protocol source: dreamworkerln/lora-sack-protocol/dev_chat@49fcd72a26efa7f9f7029735242fa62d4fe66c1e (NOT asserted to be the exact firmware flashed during manual hardware smoke)
Knowledge base: dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2:README.md, AGENT_API.md, AGENTS.md, .agents/skills/serialterminal-agent/SKILL.md, .agents/skills/node-agent/SKILL.md, TODO_INVENTORY.md, todos/TODO_001_AGENT_INTERFACE.md, todos/TODO_002_AGENT_EVENT_WAIT.md, todos/TODO_003_AGENT_CODE_QUALITY.md, source comments/tests
Transfer / promotion boundary: dev is SerialTerminal source authority; dev_handoff is recovery-only; the node skill is deliberately stored in serialterminal for stable availability, but Chatter firmware/protocol truth remains the actual lora-sack-protocol source state plus hardware evidence
```

This snapshot becomes immutable after publication through `HANDOFF_INDEX.md`.

## 1. Recovery / authority

- Read the applicable `AGENTS.md` operating instructions before using this recovery state.
- Active SerialTerminal implementation/documentation authority is `dreamworkerln/serialterminal` branch `dev`.
- Handoff/recovery authority is `dreamworkerln/serialterminal` branch `dev_handoff`.
- Before any new code work or claim about current implementation, refetch moving `dev`; this snapshot records exact source/docs state at `30a084f6d726ccc0df19a3363dac129c3838f9b2`.
- `dev_handoff` remains recovery-only. Do not implement production source changes there by default.
- `AGENT_API.md` is the canonical generic machine-facing SerialTerminal JSONL contract.
- `.agents/skills/serialterminal-agent/SKILL.md` is the concise generic agent workflow and must defer to `AGENT_API.md`.
- `.agents/skills/node-agent/SKILL.md` is the active project-specific LoRa-Chatter node/hardware skill. It is intentionally stored in `serialterminal` so it remains available when `lora-sack-protocol` branch/worktree selection changes.
- Storing the node skill here does not make SerialTerminal source authoritative for Chatter firmware semantics. Firmware/protocol truth remains the relevant actual `lora-sack-protocol` source revision and physical evidence.
- The exact firmware revision flashed on the physical nodes during the manual multi-session smoke is unknown in this recovery state. `lora-sack-protocol/dev_chat@49fcd72a...` is only the related current source checkpoint at snapshot creation, not a flashed-firmware claim.

## 2. Material changes since snapshot 002

Snapshot 002 recorded the first generic agent interface before the later event-wait/concurrency, quality, skill and physical-validation work. Since then:

### Multi-session event waiting and concurrent JSONL

- Added `wait_events` for one or many sessions with independent per-session cursors.
- A manager-level condition acts as a wakeup doorbell; retained per-session event rings remain authoritative.
- Matching events from watched sessions are drained as one deterministic batch and sorted by `(timestamp, session_id, seq)`.
- Returned cursors advance through inspected underlying events, including events excluded by filters.
- Positive timeout returns successful empty `events` with `timed_out=true`; `timeout_ms:0` remains an immediate snapshot with `timed_out=false` when empty.
- Cursor expiry remains fail-fast and session-specific.
- Pending `wait_events` requests execute asynchronously while ordinary JSONL requests continue on the input thread.
- Ordinary non-wait requests remain serialized in input order; broad concurrent mutation was deliberately not introduced.
- Responses may complete out of request order and are correlated by request `id`.
- Pending request IDs are unique; duplicate reuse returns `request_id_busy` without cancelling the original wait.
- JSONL stdout remains response-only; there is still no unsolicited event push.
- Shutdown cancels/wakes pending waits before sessions are closed.

Accepted implementation/documentation checkpoint:

```text
dreamworkerln/serialterminal/dev@aaeab3002e60bd1e85595d73e3248d42c3141c1f
GitHub Actions run 33782252791: SUCCESS
```

### Agent code-quality / CI work

- Refactored `SessionManager.wait_events` into smaller collection/result helpers without changing cursor/wakeup semantics.
- Replaced the large protocol operation branch chain with per-operation handlers while preserving the JSONL contract and error behavior.
- Extracted the JSONL process orchestration into `_AgentJsonlRunner`, preserving serialized ordinary commands, async waits, response locking, request-ID tracking and shutdown ordering.
- Removed unused Python imports/locals found during the pass.
- CI now includes Ruff static analysis and advisory Lizard complexity analysis in addition to compile/tests.
- Conservative Ruff hard gate includes `E9`, `F401`, `F63`, `F7`, `F82`, `F841` rather than broad style/modernization churn.

Recorded complexity changes:

```text
SessionManager.wait_events   CCN 28 -> 10   length 116 -> 53
AgentProtocol._dispatch      CCN 33 -> 3    length 108 -> 20
run_agent                    CCN 14 -> 3    length 110 -> 21
project Lizard warnings      15 -> 13
```

Accepted quality/static-analysis checkpoint:

```text
dreamworkerln/serialterminal/dev@a74b46585b3f2c0e032b6b444b2d1089b4fde1e9
GitHub Actions run 33785730259: SUCCESS
```

Closed quality inventory checkpoint:

```text
dreamworkerln/serialterminal/dev@0346825648f4bb60c81b1b37c1aee240580583de
GitHub Actions run 33785862613: SUCCESS
```

### Human startup scanner fix

- Initial device selection now captures `Ctrl+T s` while discovery is in progress.
- The current discovery operation finishes before scanner execution; BLE discovery and scanner are not run concurrently.
- After scanner exit, discovery resumes and TTY state is restored.
- Startup no-device retry remains interruptible and keeps the scanner hotkey available.

Accepted checkpoint:

```text
dreamworkerln/serialterminal/dev@33f9719f0dd048084a4423de83babd1ab2d76ee7
GitHub Actions run 33775808413: SUCCESS
```

### Agent documentation and skills

- Added the active generic `.agents/skills/serialterminal-agent/SKILL.md` as a short operational entry point linking to canonical `AGENT_API.md` rather than duplicating the full contract.
- Added the active `.agents/skills/node-agent/SKILL.md` for observed LoRa-Chatter node behavior, commands, telemetry, echo/reboot behavior and physical test guidance.
- `AGENTS.md` now explicitly links both skills and records their authority boundary.
- The node skill is deliberately kept in `serialterminal` because `lora-sack-protocol` branches/worktrees may be switched independently.
- README now documents the live two-node agent smoke and the node-skill ownership decision.
- TODO_001, TODO_002 and TODO inventory now distinguish original closure gates from later post-closure physical validation.

### Management-policy synchronization

The generic management-policy copies were synchronized byte-for-byte across the intended workstreams at the time of this checkpoint:

```text
HANDOFF_MANAGEMENT_POLICY.md blob:
  f98fb6c475e1e890d7dedb962b06a57d2d72a016

TODO_MANAGEMENT_POLICY.md blob:
  c175d70073d9dc2b0c66ede9485d4ece8be3e050
```

The synchronized locations include SerialTerminal `dev`, `lora-sack-protocol/dev_chat/chatter`, and `lora-sack-protocol/dev_exp_sim_validation` as recorded during the synchronization task.

## 3. Current implementation state

### Shared session/transport model

`ManagedSession` remains the shared reconnect/RX/TX core for human and agent frontends. Existing concrete transports remain I/O authority:

```text
SerialTransport
BleNusTransport
BluetoothSppTransport
```

The agent layer does not independently instantiate serial/BLE/RFCOMM transport stacks.

Each managed session has its own reconnect lifecycle, RX worker and TX worker/queue. Multiple physical devices therefore have independent per-session TX progress after ordinary `send_line`/`send_bytes` requests enqueue work.

### JSONL frontend

Current operations include:

```text
discover
open
status
list_sessions
send_line
send_bytes
events
wait_events
close
```

Important concurrency model:

```text
ordinary JSONL requests       serialized on the input thread
wait_events                   may remain pending asynchronously
per-session physical TX       independent through each ManagedSession TX worker
stdout                         one complete request-correlated response per line
response order                 may differ from request order; correlate by id
```

`send_line`/`send_bytes` returning `state=queued` means only queue acceptance. A later `tx_state=written` means transport `write()` completed. Neither is peer/radio/application delivery evidence.

### Documentation / skill model

```text
AGENT_API.md
    canonical generic JSONL/API contract

.agents/skills/serialterminal-agent/SKILL.md
    generic operational workflow

.agents/skills/node-agent/SKILL.md
    LoRa-Chatter-specific observed hardware/node guidance

AGENTS.md
    repository operating rules and authority boundaries
```

The generic API remains device-agnostic even though the repository is commonly used with Chatter hardware.

### TODO state

`TODO_INVENTORY.md` is authoritative and currently says:

```text
Active: None
```

Closed thematic TODOs remain:

```text
TODO_001_AGENT_INTERFACE     CLOSED
TODO_002_AGENT_EVENT_WAIT    CLOSED
TODO_003_AGENT_CODE_QUALITY  CLOSED
```

Post-closure hardware history is recorded without reopening those completed implementation tasks.

## 4. Architecture / invariants

Preserve these unless a future explicit task changes them:

- `dev` is source authority; `dev_handoff` is recovery authority.
- Existing transport implementations remain the only Serial/BLE/SPP transport authorities.
- Human and machine frontends share `ManagedSession` reconnect/RX/TX behavior.
- Sticky reconnect targets the same selected physical identity.
- Line/raw TX share reconnect-safe ordered queue semantics within a session.
- Different sessions keep independent TX workers/queues.
- BLE logical streams remain distinct and preserve stream tags/decode state.
- Human Chatter presentation is UI-level behavior and must not redefine generic machine RX semantics.
- `queued` is queue evidence only; `written` is transport-write evidence only.
- Peer/RF delivery must be demonstrated by peer RX, telemetry or higher-level protocol evidence.
- JSONL stdout remains request-correlated response-only output.
- `wait_events` is the asynchronous long-poll mechanism; ordinary commands intentionally remain serialized.
- Do not add generalized async mutation, daemon/service layers or MCP merely to reduce apparent serialization. Require a concrete use case.
- A future MCP adapter, if needed, should wrap `SessionManager` rather than bypass it.
- `AGENT_API.md` is generic API authority. Node skill content must not silently redefine it.
- Node skill storage in SerialTerminal is an availability decision, not a transfer of Chatter firmware source authority.

## 5. Validation evidence

### Automated validation

Final current SerialTerminal documentation/source checkpoint:

```text
dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2
GitHub Actions run 33801154957: SUCCESS
```

That run completed the repository CI steps including:

```text
Compile            PASS
Static analysis    PASS
Complexity         executed successfully / advisory policy retained
Tests              PASS
```

No production source code was changed by the documentation/history synchronization immediately preceding this snapshot.

### Physical hardware / Codex validation observed post-closure

Observed on 2026-09-03 with physical LoRa-Chatter hardware:

- one `serialterminal agent` process opened two physical BLE nodes as independent sessions;
- Codex independently invoked/read node `/help` and learned the available node command surface rather than relying on a fully pre-scripted workflow;
- a multi-session `wait_events` request was used;
- ordinary commands continued while that wait remained pending;
- TX was issued from both physical sessions close together, exercising independent per-session host TX paths;
- earlier physical node-to-node transfer and Chatter echo behavior were observed and are documented in `.agents/skills/node-agent/SKILL.md`;
- node `LoRa-Chatter-1B44` was additionally observed over USB with ESP32 powered while the radio module power was intentionally unavailable; boot reported `RADIO UNAVAILABLE bootTxSelfTest (-5); RF disabled` while USB/controller access remained available.

The physical multi-session smoke validates practical use of the generic host-side session/concurrent-wait model. It does **not** by itself prove that both close-together LoRa transmissions were successfully received by peers. That requires corresponding peer RX/telemetry evidence.

Exact manual-smoke process log ID: UNKNOWN / not recorded here.

Exact flashed firmware revision during that smoke: UNKNOWN / not recorded here.

Do not manufacture either identifier during recovery.

## 6. Known limitations / optional future polish

No required SerialTerminal implementation work is open at this checkpoint.

Potential future improvements only if a concrete need appears:

1. Map host/sandbox Bluetooth permission failures such as `Operation not permitted` to a stable machine-facing error (for example `permission_denied`) instead of a generic/internal failure.
2. Optionally expose per-backend discovery diagnostics when `scope:auto` partially succeeds and one backend fails.
3. Add MCP only for a real consumer, as a thin wrapper over the existing `SessionManager` API.
4. Do not mechanically refactor remaining Lizard warnings. Some are natural configuration/API boundaries or compact state-machine/filter expressions where splitting solely for metrics would reduce clarity.

These are not active TODOs and are not blockers.

## 7. Knowledge references

At current source/docs checkpoint `dreamworkerln/serialterminal/dev@30a084f6d726ccc0df19a3363dac129c3838f9b2`:

- `AGENTS.md` — repository operating rules and agent/node-skill authority boundaries.
- `AGENT_API.md` — canonical generic JSONL contract, event cursor semantics and concurrency rules.
- `.agents/skills/serialterminal-agent/SKILL.md` — generic operational agent workflow.
- `.agents/skills/node-agent/SKILL.md` — observed LoRa-Chatter node/hardware workflow and hardware findings.
- `README.md` — user-facing human/agent behavior and live hardware-smoke summary.
- `TODO_INVENTORY.md` — authoritative current TODO state and post-closure hardware validation history.
- `todos/TODO_001_AGENT_INTERFACE.md` — closed base agent-interface task plus post-closure hardware history.
- `todos/TODO_002_AGENT_EVENT_WAIT.md` — closed multi-session/concurrent-wait task plus post-closure physical smoke.
- `todos/TODO_003_AGENT_CODE_QUALITY.md` — closed complexity/static-analysis refactor record.
- `HANDOFF_MANAGEMENT_POLICY.md` — snapshot/recovery publication rules.
- `TODO_MANAGEMENT_POLICY.md` — TODO lifecycle rules.
- `src/serialterminal/session.py` — shared session core.
- `src/serialterminal/agent.py` — manager/protocol/JSONL runner.
- `src/serialterminal/cli.py`, `src/serialterminal/startup_controls.py` — CLI/startup scanner behavior.
- `.github/workflows/ci.yml`, `pyproject.toml` — compile/Ruff/Lizard/test validation configuration.
- tests — deterministic regression evidence for session/agent/terminal/CLI behavior.

Related current protocol source at snapshot time:

```text
dreamworkerln/lora-sack-protocol/dev_chat@49fcd72a26efa7f9f7029735242fa62d4fe66c1e
```

Again, this related moving-source checkpoint is not claimed to equal the exact physical node firmware used during manual smoke.

## 8. Transfer / promotion boundary

- No source merge/promotion is required: SerialTerminal implementation remains on `dev`.
- `dev_handoff` must not be merged wholesale back as a source tree; it is recovery documentation authority only.
- Keep generic SerialTerminal API/session semantics in `AGENT_API.md` and generic skill.
- Keep project-specific node observations in `.agents/skills/node-agent/SKILL.md` for stable agent availability.
- When node behavior depends on firmware implementation, inspect the actual relevant `lora-sack-protocol` source revision rather than treating the copied observation as source-code authority.
- Preserve dependency direction:

```text
node/project workflow
        -> SerialTerminal generic JSONL/API
        -> SessionManager
        -> ManagedSession
        -> existing Transport implementations
```

## 9. Immediate continuation

There is no mandatory SerialTerminal code task after this checkpoint.

For future work:

1. Read `AGENTS.md`, this index/snapshot, then refetch moving `dev` before editing.
2. If a concrete terminal bug/API need appears during Chatter work, open/update the appropriate TODO and change only the needed generic behavior.
3. Keep physical delivery claims tied to actual peer RX/telemetry rather than `queued`/`written` alone.
4. Keep the node skill current when new hardware facts materially affect how an agent should operate or validate nodes.
5. If permission/error diagnostics or MCP become necessary, treat them as explicit new work rather than assumed unfinished scope.

## 10. Standing reminders

- `TODO_INVENTORY.md` currently has no active TODO.
- Final current SerialTerminal CI is green at `dev@30a084f6d726ccc0df19a3363dac129c3838f9b2`, run `33801154957`.
- Physical multi-session agent use has now been observed post-closure; do not revert documentation to `hardware NOT RUN` without distinguishing closure-gate history from later validation.
- Do not overclaim simultaneous LoRa delivery from the close-together two-session TX smoke.
- Exact manual smoke log ID and flashed firmware revision remain unknown.
- Preserve source/recovery separation and immutable published snapshots.
- Future snapshots must continue: refetch exact state -> create snapshot -> read-back/verify -> advance index.
