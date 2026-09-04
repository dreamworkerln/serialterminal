# Handoff snapshot 004

```text
Snapshot: HANDOFF_004.md
Previous: HANDOFF_003.md
Created: 2026-09-04T20:39:00Z
Handoff authority: dreamworkerln/serialterminal/dev_handoff@390ce4ebe138f9661b20603a37618a0edc15ba65
Source checkpoints:
  Active SerialTerminal source/docs: dreamworkerln/serialterminal/dev@0da242eb9c67bf82d59fbfbbcb0bca3ced92a942
  Node observation evidence: dreamworkerln/serialterminal/node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198
Knowledge base:
  dreamworkerln/serialterminal/dev@0da242eb9c67bf82d59fbfbbcb0bca3ced92a942:
    AGENTS.md
    AGENT_API.md
    .agents/skills/serialterminal-agent/SKILL.md
    .agents/skills/node-agent/SKILL.md
    NODE_OBSERVATION_RECORDING_POLICY.md
    NODE_SKILL_LEARNING_POLICY.md
    TODO_INVENTORY.md
    source/tests/CI configuration
  dreamworkerln/serialterminal/node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198:
    REVIEW_STATE.md
    observations/*.md
Transfer / promotion boundary:
  dev is SerialTerminal source/docs authority; node_observations is append-only run evidence; dev_handoff is recovery-only; Chatter firmware/protocol truth remains the actual relevant lora-sack-protocol source/docs checkpoint
```

This snapshot becomes immutable after publication through `HANDOFF_INDEX.md`.

## 1. Recovery / authority

- Read the applicable `AGENTS.md` first.
- `dreamworkerln/serialterminal:dev` is the active SerialTerminal source/docs authority.
- `dev_handoff` is recovery-only authority and must not become the production source branch.
- `node_observations` is a separate orphan evidence branch. It is not merged into `dev` and is not a source-code authority.
- `AGENT_API.md` is the canonical generic SerialTerminal JSONL contract.
- `.agents/skills/serialterminal-agent/SKILL.md` is the concise generic operational skill and must defer to `AGENT_API.md`.
- `.agents/skills/node-agent/SKILL.md` is class-level reusable LoRa-Chatter operating/validation guidance only.
- Run-specific IDs, MAC/BLE addresses, USB paths, measurements, topology and one-run state belong in observation records, not in the class skill.
- `NODE_OBSERVATION_RECORDING_POLICY.md` governs local executor evidence recording.
- `NODE_SKILL_LEARNING_POLICY.md` governs reviewer classification/generalization/promotion into the node skill.
- Firmware/protocol semantics remain authoritative in the relevant actual `lora-sack-protocol` source/docs revision. This snapshot does not guess or pin an ACK-capable firmware SHA that was not explicitly established here.

## 2. Material changes since snapshot 003

Snapshot 003 recorded `dev@30a084f6d726ccc0df19a3363dac129c3838f9b2`. Current `dev` is 22 commits ahead at `0da242eb9c67bf82d59fbfbbcb0bca3ced92a942`.

The changed files in that range are documentation/skill/policy/helper files:

```text
.agents/skills/node-agent/SKILL.md
AGENTS.md
AGENT_API.md
NODE_OBSERVATION_RECORDING_POLICY.md
NODE_SKILL_LEARNING_POLICY.md
scripts/commit-node-observation
```

No SerialTerminal Python transport/session/terminal implementation file changed in this range.

### Node knowledge/evidence split

The node-agent model was tightened from mixed notes into explicit layers:

```text
local executor hardware run
        -> raw factual observation
        -> node_observations orphan branch
        -> reviewer processing
        -> class-level promotion when justified
        -> .agents/skills/node-agent/SKILL.md
```

Current invariant:

```text
skill = reusable class behavior / operating rules
observation = run-specific evidence
```

`AGENTS.md` now explicitly forbids concrete node IDs, MAC/BLE addresses, USB paths, current measurements/topology and other instance-specific state in the active node skill.

### Observation storage and guarded publication

`NODE_OBSERVATION_RECORDING_POLICY.md` now defines:

- separate independent clone for `node_observations`, not a linked worktree;
- executor writes only new `observations/OBS_*.md` records;
- published observations are append-only evidence;
- executor does not modify `REVIEW_STATE.md`;
- guarded helper `python3 -I scripts/commit-node-observation` performs observation commit/push;
- helper invocation must be a standalone command and is expected to run elevated;
- raw `git add/commit/push` is not the executor fallback when helper guards fail;
- after helper success, remote `node_observations` ref must be independently verified using the documented standalone elevated `git ... ls-remote` command;
- exact helper diagnostic text must be preserved on failures.

`NODE_SKILL_LEARNING_POLICY.md` separately defines reviewer processing, class-level abstraction, conflict handling, promotion gates and `REVIEW_STATE.md` advancement order.

### Current observation evidence state

At snapshot creation:

```text
node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198
```

contains three factual observation records:

```text
observations/OBS_20260904T075106Z_max-text-payload.md
observations/OBS_20260904T085207Z_oversized-payload.md
observations/OBS_20260904T134143Z_empty-and-size-speed.md
```

`REVIEW_STATE.md` is still initial/unadvanced:

```text
last_reviewed_observation: none
last_reviewed_observation_commit: none
reviewed_against_dev: none
reviewed_by_commit: none
reviewed_at: none
unresolved: []
```

Therefore these observations exist as evidence but are not represented as a completed reviewer cursor range. Do not silently mark them reviewed during recovery.

### Generic agent launch instruction

`AGENT_API.md` now explicitly says to run:

```bash
python3 serialterminal.py agent
```

with elevated privileges in the intended hardware/Codex environment.

The JSONL schema/session/event semantics themselves were not changed by that documentation edit.

### Node skill: current reliable USER guidance

The active node skill now describes the current ACK-capable Chatter reliable USER model at class level, including:

- one reliable USER in flight plus a bounded queue;
- logical USER identity `(sender_session_id, user_seq)`;
- retry reuses the same identity and payload;
- matching ACK, not transport `queued`/`written` or local TX marker, is sender delivery evidence;
- current documented hardware-validation policy of maximum 5 physical USER attempts and reliable USER queue depth 8, explicitly treated as configurable implementation policy rather than eternal wire constants;
- duplicate USER suppression in peer CHAT while still repeating ACK;
- stale/wrong-session/wrong-seq/unrelated ACK handling;
- `/cancel` and `/cancel all` semantics;
- queue-full explicit rejection;
- collision/retry expectations for simultaneous USER transmission;
- ECHO remains an independent best-effort diagnostic path;
- focused two-node reliability scenarios for normal ACK, lost USER, lost ACK, simultaneous USER, peer-off/recovery, queueing/full/cancel and wrong/stale ACK cases.

The skill also retains the safe-final-state requirements: echo OFF, no unintended reliable retry left running, CHAT output mode, and test sessions closed when no longer needed.

## 3. Current generic SerialTerminal implementation state

The generic machine interface architecture remains as in snapshot 003:

```text
JSONL frontend
    -> SessionManager
    -> ManagedSession
    -> existing Transport abstraction
    -> SerialTransport / BleNusTransport / BluetoothSppTransport
```

Important unchanged semantics:

- one agent process can hold multiple independent sessions/devices;
- ordinary non-wait JSONL requests remain serialized in input order;
- `wait_events` may remain pending asynchronously while ordinary requests continue;
- responses are correlated by request `id` and may complete out of request order;
- stdout remains request-correlated response-only output; no unsolicited event push;
- each session owns its own reconnect-safe TX queue/worker;
- `send_line` and `send_bytes` return queue acceptance, not application/RF delivery;
- `tx_state=written` means transport `write()` completed, not peer delivery;
- peer/application outcomes arrive later through RX/events and must be interpreted by the consuming protocol/node layer.

No broad async mutation model, daemon/service layer or MCP has been added.

## 4. Chatter text-size / oversized-send boundary

Current node guidance uses:

```text
USER/ECHO payload length: 1..200 UTF-8 bytes inclusive
```

This is a Chatter firmware/application limit, not a generic SerialTerminal transport/API constant.

Generic SerialTerminal currently does **not** pre-reject `send_line` merely because its encoded payload exceeds the Chatter text limit. The generic flow is:

```text
agent send_line
    -> SerialTerminal queue accepts item
    -> transport write completes when possible
    -> Chatter firmware parses/rejects oversized line
    -> firmware SYSTEM response returns through normal RX
    -> agent observes that response via events / wait_events
```

For the currently inspected Chatter behavior, the firmware rejection text is:

```text
[SYS] INPUT TOO LONG: max 200 bytes
```

For the machine interface this is an asynchronous RX/SYSTEM outcome, not `send_line ok:false`.

For the human interface, the terminal presentation layer recognizes `[SYS] INPUT TOO LONG:` as a firmware failure outcome and reveals/resolves the pending human presentation accordingly.

Do not add a generic hard-coded `200` check to SerialTerminal without an explicit design decision: generic SerialTerminal is intentionally device-agnostic. If a future host-side limit is needed, it must be designed as a generic/configurable capability rather than silently baking in Chatter firmware policy.

The limit is byte-based. UTF-8 character count is not equivalent to encoded byte length.

## 5. TODO / current engineering state

`TODO_INVENTORY.md` remains authoritative and currently says:

```text
Active: None
```

The previously closed SerialTerminal tasks remain closed:

```text
TODO_001_AGENT_INTERFACE     CLOSED
TODO_002_AGENT_EVENT_WAIT    CLOSED
TODO_003_AGENT_CODE_QUALITY  CLOSED
```

The observation/reviewer infrastructure and node-skill updates did not reopen a generic terminal implementation TODO.

## 6. Validation evidence

Current SerialTerminal source/docs checkpoint:

```text
dreamworkerln/serialterminal/dev@0da242eb9c67bf82d59fbfbbcb0bca3ced92a942
GitHub Actions run 33909130096: SUCCESS
```

This handoff operation itself performs documentation/recovery publication only and does not claim any new physical hardware interaction.

The current `node_observations` branch is factual evidence from earlier hardware runs; its three records should be read directly when exact run details are required.

## 7. Known limitations / open process state

There is still no required generic SerialTerminal code task at this checkpoint.

Important non-blocking items/process state:

1. `node_observations` contains unreviewed evidence according to `REVIEW_STATE.md`; a reviewer pass is a separate knowledge-processing task, not automatically part of every handoff.
2. Generic SerialTerminal does not know/enforce Chatter's 200-byte application payload limit; oversized Chatter rejection is observed later through firmware RX.
3. Stable machine-facing mapping for sandbox/Bluetooth permission failures remains optional future polish.
4. Per-backend diagnostics for partial `discover scope:auto` failure remain optional future polish.
5. MCP remains deferred until a real consumer requires it; any adapter should wrap existing `SessionManager`.
6. Current node skill's ACK/retry parameters are explicitly implementation-policy values. Future recovery must check actual relevant firmware source/docs before treating them as immutable protocol constants.

## 8. Knowledge references

At `dev@0da242eb9c67bf82d59fbfbbcb0bca3ced92a942`:

- `AGENTS.md` — repository operating rules and skill/evidence boundaries.
- `AGENT_API.md` — canonical generic JSONL contract and elevated launch instruction.
- `.agents/skills/serialterminal-agent/SKILL.md` — generic operational workflow.
- `.agents/skills/node-agent/SKILL.md` — current reusable LoRa-Chatter class guidance including reliable USER/ACK semantics.
- `NODE_OBSERVATION_RECORDING_POLICY.md` — local executor raw-evidence contract.
- `NODE_SKILL_LEARNING_POLICY.md` — reviewer generalization/promotion contract.
- `scripts/commit-node-observation` — guarded observation publication helper.
- `TODO_INVENTORY.md` — current engineering TODO state.
- Python source/tests/CI configuration — actual generic terminal implementation and regression evidence.

At `node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198`:

- `REVIEW_STATE.md` — current reviewer cursor/state (`none` at this checkpoint).
- `observations/*.md` — append-only run-specific evidence.

## 9. Transfer / promotion boundary

Preserve these separations:

```text
SerialTerminal generic API/session behavior
    -> AGENT_API.md + generic skill + Python source/tests

LoRa-Chatter reusable operating/validation rules
    -> node-agent/SKILL.md

run-specific hardware evidence
    -> node_observations/observations/*.md

review cursor / unresolved knowledge state
    -> node_observations/REVIEW_STATE.md

firmware/protocol implementation truth
    -> actual relevant lora-sack-protocol source/docs

recovery snapshots
    -> dev_handoff
```

Do not merge `node_observations` into `dev`, do not copy raw run identifiers into the class skill, and do not treat copied node guidance as a substitute for inspecting firmware source when exact protocol semantics matter.

## 10. Immediate continuation

There is no mandatory SerialTerminal code task after this checkpoint.

For the next task:

1. Read `AGENTS.md`, `CONTEXT.md`, `HANDOFF_INDEX.md`, then this snapshot.
2. Refetch moving `dev` before source/docs edits.
3. If doing hardware execution, follow `NODE_OBSERVATION_RECORDING_POLICY.md` and record run-specific evidence in `node_observations` when required.
4. If doing knowledge review/promotion, follow `NODE_SKILL_LEARNING_POLICY.md`; current `REVIEW_STATE.md` means the existing observation range has not yet been advanced as reviewed.
5. If doing Chatter reliability validation, verify the actual relevant firmware source/docs checkpoint before relying on implementation-policy values such as retry count/queue depth.
6. For oversized text, remember that generic `send_line` queue success is not firmware acceptance; wait for RX/SYSTEM outcome.
7. Open new generic terminal implementation work only for a concrete defect or requirement.

## 11. Standing reminders

- `TODO_INVENTORY.md`: `Active: None`.
- Current recorded `dev` CI is green at run `33909130096`.
- No SerialTerminal Python core file changed between snapshots 003 and 004.
- `node_observations` is evidence, not source, and its current `REVIEW_STATE.md` is unadvanced.
- Do not place instance-specific hardware facts back into `.agents/skills/node-agent/SKILL.md`.
- Do not overclaim delivery from SerialTerminal `queued`, transport `written`, or a local TX marker.
- Chatter oversized text failure is a firmware RX/SYSTEM outcome for the agent, not a synchronous generic `send_line` rejection.
- Published snapshots remain immutable.
- Future snapshots continue the order: refetch exact state -> create snapshot -> read-back/verify -> advance index.
