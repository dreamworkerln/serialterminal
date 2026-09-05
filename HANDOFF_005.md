# Handoff snapshot 005

```text
Snapshot: HANDOFF_005.md
Previous: HANDOFF_004.md
Created: 2026-09-05T10:15:00Z
Handoff authority: dreamworkerln/serialterminal/dev_handoff@20893774c60171d6d27d61f42031dcd67aae7951
Source checkpoints:
  Active SerialTerminal source/docs: dreamworkerln/serialterminal/dev@e6e74a45237abaf488cb815c2bba185810215c9d
  Node observation evidence: dreamworkerln/serialterminal/node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198
Knowledge base:
  dreamworkerln/serialterminal/dev@e6e74a45237abaf488cb815c2bba185810215c9d:
    AGENTS.md
    AGENT_API.md
    .agents/skills/serialterminal-agent/SKILL.md
    .agents/skills/node-agent/SKILL.md
    TODO_INVENTORY.md
    todos/TODO_004_NODE_RUN_BUNDLES.md
    NODE_OBSERVATION_RECORDING_POLICY.md
    NODE_SKILL_LEARNING_POLICY.md
    source/tests/CI configuration
  dreamworkerln/serialterminal/node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198:
    REVIEW_STATE.md
    observations/*.md
Transfer / promotion boundary:
  dev is SerialTerminal source/docs authority; node_observations is append-only run evidence; dev_handoff is recovery-only; firmware/protocol truth remains the actual relevant lora-sack-protocol source/docs checkpoint
```

This snapshot becomes immutable after publication through `HANDOFF_INDEX.md`.

## 1. Recovery / authority

- Read the applicable `AGENTS.md` first.
- `dreamworkerln/serialterminal:dev` is current SerialTerminal source/docs authority.
- `dev_handoff` is recovery-only authority and must not become production source.
- `node_observations` is a separate evidence branch, not source-code authority and not merged into `dev`.
- `AGENT_API.md` is the canonical generic SerialTerminal JSONL contract.
- `.agents/skills/serialterminal-agent/SKILL.md` is the concise operational skill and defers to `AGENT_API.md`.
- `.agents/skills/node-agent/SKILL.md` contains reusable class-level LoRa-Chatter behavior/validation rules only; instance/run facts remain evidence.
- `TODO_INVENTORY.md` is authoritative for TODO status.
- Firmware/protocol semantics remain authoritative in the actual relevant `lora-sack-protocol` source/docs revision; this snapshot does not invent a firmware SHA that was not established.

## 2. Material changes since snapshot 004

Snapshot 004 recorded:

```text
dev@0da242eb9c67bf82d59fbfbbcb0bca3ced92a942
```

Current source is:

```text
dev@e6e74a45237abaf488cb815c2bba185810215c9d
```

The current branch is 8 commits ahead of the snapshot-004 source checkpoint. Material current-tree changes affect:

```text
.agents/skills/node-agent/SKILL.md
.agents/skills/serialterminal-agent/SKILL.md
AGENT_API.md
README.md
TODO_INVENTORY.md
todos/TODO_004_NODE_RUN_BUNDLES.md
src/serialterminal/agent.py
src/serialterminal/runlog.py
src/serialterminal/session.py
tests/test_agent.py
tests/test_agent_console_log.py
tests/test_runlog_lines.py
tests/test_session.py
```

An intermediate line-oriented RunLog implementation was introduced first, then superseded by the accepted refactor below. Current source must be read from `e6e74a4...`; do not infer final architecture from the intermediate commits.

## 3. Breaking machine receive API: `observe`

Current machine operations are:

```text
discover
open
list_sessions
status
send_line
send_bytes
observe
close
```

`observe` is the only receive/cursor operation.

Former machine operations:

```text
events
wait_events
```

are removed. Requests using them now fall through normal dispatch as `unknown_operation`; there is no compatibility alias/layer in the accepted implementation.

The canonical request shape always uses a per-session `cursors` object, including for one session:

```json
{"id":20,"op":"observe","cursors":{"s1":42},"timeout_ms":15000}
```

Important invariants:

- `observe` requires a non-null request `id` at the JSONL frontend;
- a pending `observe` does not block later ordinary JSONL commands;
- a request ID owned by a pending `observe` cannot be reused and yields `request_id_busy`;
- stdout remains request/response JSONL only, with no unsolicited event push;
- responses may arrive out of request order and must be correlated by `id`;
- positive timeout with no raw event returns `timed_out:true`, not an error;
- `timeout_ms:0` is an immediate snapshot and returns `timed_out:false`;
- unknown session and expired/invalid cursor remain structured errors.

## 4. One raw cursor, two receive views

Each watched session has one raw SessionEvent cursor. The same cursor governs both views returned by `observe`:

```text
observe.result.events
observe.result.lines
```

`result.events` is forensic source of truth:

- raw retained `SessionEvent` records;
- real transport/session chunk boundaries;
- event `seq` and timestamp;
- byte-accurate `data_b64` for RX;
- chunk-level incremental UTF-8 `text`;
- state/TX/error metadata.

`result.lines` is a convenience/protocol view containing only completed LF-terminated logical firmware lines:

```json
{
  "session":"s1",
  "stream":"chat",
  "text":"complete firmware line",
  "seq_first":282,
  "seq_last":284,
  "timestamp":...
}
```

The cursor advances according to raw events, not according to logical-line count.

A completed line is returned when its terminating raw event is newer than the input cursor. Therefore a line may legitimately have:

```text
seq_first <= input cursor < seq_last
```

This is intentional: callers can receive the whole logical line even when its first bytes were observed in an earlier call. Callers should not manually concatenate chunks when the required completed line is already present in `result.lines`.

For multi-session observation, raw events and lines are each ordered chronologically with stable session/sequence tie-breaks. The returned `cursors` object is the canonical continuation state.

## 5. Canonical logical-line assembly lives in `ManagedSession`

Line assembly was moved out of RunLog into the session model.

Current pipeline:

```text
transport raw RX chunk
    -> SessionEvent ring
    -> per-stream canonical logical-line assembler in ManagedSession
       -> observe.result.events
       -> observe.result.lines
       -> console logger callback for human-console streams
```

The assembler is independent per stream. `chat`/human-console and `telemetry` must not be cross-concatenated.

Current logical-line behavior:

- uses the existing incremental UTF-8 decoded `SessionEvent.text`, so a multibyte character split across transport chunks is reconstructed correctly;
- preserves raw bytes/chunks unchanged in `result.events`;
- treats LF as logical line completion;
- strips only a trailing `\r` from completed line text so CRLF appears as one boundary in the convenience view;
- preserves empty logical lines;
- records `seq_first` and `seq_last` so the line can be correlated to raw chunks;
- stores only completed logical lines as first-class `SessionLine` records;
- incomplete text is not emitted as a logical partial line; its bytes remain available in raw events;
- incomplete line state is cleared at connection lifecycle boundaries so text is never silently joined across a disconnect/reconnect boundary.

`ManagedSession.observation_after()` returns raw events and logical lines under the same session lock, preventing a terminating raw event from being returned without the line that it completed in the same snapshot.

## 6. Paired forensic and human-console run logs

Each agent run now owns a paired logfile set with the same timestamp/PID prefix:

```text
logs/serialterminal-<stamp>-pPID.log
logs/serialterminal-<stamp>-pPID.console.log
```

### Main `.log`

The main logfile remains forensic/API/transport truth. It continues to contain records such as:

```text
[RUN]
[AGENT]
[AGENT REQUEST]
[AGENT RESPONSE]
[STATE]
[TX]
[RX <stream>]
[ERROR]
```

Raw RX records keep real chunk boundaries, event `seq`, timestamps, incremental chunk text and `data_b64`.

The old convenience records are no longer a separate RunLog line stream:

```text
[RX LINE ...]
[RX PARTIAL ...]
```

Current forensic RunLog does not emit them. Logical lines are first-class session/API data and may also appear inside the corresponding `[AGENT RESPONSE]` payload when returned by `observe`.

### Companion `.console.log`

The companion log is human-oriented presentation/audit only, approximating what a person would type and see in normal SerialTerminal UI.

TX accepted through `send_line` is rendered as:

```text
2026-... [s1] > /id
2026-... [s1] > hello
```

A completed logical line from a human-console RX stream is rendered as:

```text
2026-... [s1] < [SYS] OUTPUT BOTH
2026-... [s2] < < [-33/+10 Q100] hello
```

Rules:

- one chronological companion file is shared by all sessions in the agent run;
- every record carries the session ID;
- `send_line` is audit/presentation evidence only, not delivery evidence;
- `send_bytes` is not rendered as ordinary human input in the first version;
- BLE machine telemetry stream is intentionally excluded merely because SerialTerminal is subscribed to it;
- if telemetry semantics actually arrive through the BLE human-console/chat stream, for example because firmware is in `/both`, those lines naturally appear in `.console.log`;
- no second line assembler exists in logging; completed RX lines come from the same canonical `ManagedSession` line model used by `observe.result.lines`.

The forensic startup `[AGENT]` ready metadata contains both:

```text
log_path
console_log_path
```

There is still no unsolicited stdout "ready" event; this metadata is written to the forensic log.

## 7. TX/delivery semantics remain unchanged

The refactor did not change the meaning of send acknowledgement:

```text
send_line/send_bytes state=queued
    = accepted by SerialTerminal reconnect-safe TX queue

tx_state=written
    = transport write() completed
```

Neither proves RF/peer/application delivery.

Protocol/application success still requires relevant RX/telemetry/application evidence. For line-oriented firmware reasoning use `observe.result.lines`; for exact chunk/byte proof use `observe.result.events`.

The Chatter oversized-text boundary remains firmware-specific:

```text
1..200 UTF-8 bytes for current USER/ECHO guidance
```

Generic SerialTerminal still does not hard-code this application limit. An oversized `send_line` can be queued/written generically, after which firmware rejection such as:

```text
[SYS] INPUT TOO LONG: max 200 bytes
```

arrives later through RX and is observed through `observe`, not as synchronous `send_line ok:false`.

## 8. TODO state and next substantial work

`TODO_INVENTORY.md` now has an active entry:

```text
TODO_004 — Automated node run bundles
Status: DEFERRED
```

Its stated return condition was: resume only after an accepted SerialTerminal checkpoint provides both:

1. one canonical observation API returning raw events plus completed logical firmware lines;
2. one companion human-console logfile generated from the same canonical line/session model.

That dependency condition is now satisfied by the accepted checkpoint:

```text
dreamworkerln/serialterminal/dev@e6e74a45237abaf488cb815c2bba185810215c9d
GitHub Actions run 33959407933 SUCCESS
```

However, TODO status has **not** been changed by this handoff. It remains `DEFERRED` until a separate task explicitly resumes implementation. When resumed, record `e6e74a4...` (or a newer explicitly accepted compatible checkpoint) as the exact dependency checkpoint before implementation begins.

TODO_004 target is to publish immutable node run bundles containing the short observation, full executor report, exact forensic log, exact companion console log and manifest via a guarded helper, while keeping reviewer/learning responsibilities separate.

## 9. Observation/reviewer evidence state

Current evidence ref is unchanged from snapshot 004:

```text
dreamworkerln/serialterminal/node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198
```

`REVIEW_STATE.md` remains:

```text
last_reviewed_observation: none
last_reviewed_observation_commit: none
reviewed_against_dev: none
reviewed_by_commit: none
reviewed_at: none
unresolved: []
```

Therefore the three existing observations remain factual evidence but the reviewer cursor/range has still not been advanced. Do not infer that the new terminal refactor reviewed or promoted those observations.

## 10. Validation evidence

Accepted source checkpoint:

```text
dreamworkerln/serialterminal/dev@e6e74a45237abaf488cb815c2bba185810215c9d
GitHub Actions run 33959407933: SUCCESS
```

The workflow completed cleanly overall. Recorded gates include:

```text
Compile           PASS
Static analysis   PASS
Tests             PASS (94 passed in the exact run)
Complexity        advisory/non-blocking; existing Lizard warnings remain
```

The current Lizard advisory still reports 13 project warnings; the new session line assembler is among warned functions. This is not a blocking CI failure under the current workflow and is not treated by this snapshot as an automatic refactor requirement.

No physical hardware test was run specifically for `e6e74a4...` as part of this host-side refactor/handoff sequence. Do not claim hardware validation of the new `observe`/console-log behavior unless a later exact hardware run records it.

## 11. Source-history publication quirk

During publication of the final refactor, two technical intermediate commits were created by an erroneous GitHub contents call:

```text
184c34fc7170bfd2a61039d74bf0d117d58bc645  noop
52362391b59d2b128b9a75706a77cd4ab00737ce  noop2
```

They temporarily carried an unintended empty file. History was not rewritten and no force push was used. The accepted final commit `e6e74a4...` restores the intended clean tree; comparison from the pre-publication source checkpoint contains only the expected project files and the stray file is absent from current `dev`.

Treat this as a history artifact only, not current project state.

## 12. Known limitations / open process state

1. `TODO_004` is still deferred even though its dependency gate is now satisfied; resumption is a separate explicit engineering task.
2. Current canonical line API emits only completed LF-terminated lines; incomplete fragments remain raw forensic events and are cleared from line-assembly state at lifecycle boundaries.
3. Generic SerialTerminal still does not enforce Chatter's 200-byte application payload limit.
4. `node_observations` remains unreviewed according to `REVIEW_STATE.md`.
5. Stable mapping of sandbox/Bluetooth permission failures and richer per-backend auto-discovery diagnostics remain optional future polish, not required work introduced by this snapshot.
6. MCP remains deferred unless a concrete consumer needs it; any future adapter should wrap the current session/manager model instead of duplicating transport logic.

## 13. Knowledge references

At `dev@e6e74a45237abaf488cb815c2bba185810215c9d`:

- `AGENTS.md` — repository operating rules and source/evidence/skill boundaries.
- `AGENT_API.md` — canonical generic JSONL contract, `observe` semantics and paired run logs.
- `.agents/skills/serialterminal-agent/SKILL.md` — operational `observe` workflow and raw-vs-line guidance.
- `.agents/skills/node-agent/SKILL.md` — reusable LoRa-Chatter validation guidance updated to consume `observe.result.lines/events`.
- `TODO_INVENTORY.md` — active/deferred TODO state.
- `todos/TODO_004_NODE_RUN_BUNDLES.md` — planned run-bundle automation and dependency gate.
- `src/serialterminal/session.py` — canonical raw event + logical line model.
- `src/serialterminal/agent.py` — machine operations, async observe, console-line hookup.
- `src/serialterminal/runlog.py` — forensic log plus paired companion console file.
- related tests — current deterministic regression contract.

At `node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198`:

- `REVIEW_STATE.md` — reviewer cursor/state, still `none`.
- `observations/*.md` — append-only run-specific evidence.

## 14. Transfer / promotion boundary

Preserve these separations:

```text
SerialTerminal generic API/session behavior
    -> Python source/tests + AGENT_API.md + generic skill

LoRa-Chatter reusable class guidance
    -> node-agent/SKILL.md

run-specific hardware evidence
    -> node_observations/observations/*.md

review cursor / unresolved knowledge state
    -> node_observations/REVIEW_STATE.md

future complete hardware run bundles
    -> TODO_004 design, eventually node_observations/runs/... when implemented

firmware/protocol implementation truth
    -> actual relevant lora-sack-protocol source/docs

recovery snapshots
    -> dev_handoff
```

Do not rebuild logical lines independently in a future run-bundle helper. Persist/copy the exact files produced by SerialTerminal and consume the canonical session/API line model.

## 15. Immediate continuation

For the next engineering task:

1. Read `AGENTS.md`, `CONTEXT.md`, `HANDOFF_INDEX.md`, then this snapshot.
2. Refetch moving `dev` and relevant evidence/protocol refs before claiming current state.
3. Treat `observe` as the only generic receive/cursor API; do not resurrect old `events`/`wait_events` unless explicitly designing a new breaking change.
4. Use `result.lines` for completed firmware-line reasoning and `result.events` for forensic raw/chunk/byte truth.
5. Preserve the one-assembler invariant: transport chunks stay raw; logical line assembly stays in the session layer; logging does not create a second assembler.
6. If resuming TODO_004, first record the exact accepted dependency checkpoint and then implement the bundle workflow without redesigning `observe` or reconstructing console logs.
7. If doing hardware execution, follow `NODE_OBSERVATION_RECORDING_POLICY.md`; if doing reviewer promotion, separately follow `NODE_SKILL_LEARNING_POLICY.md`.
8. Do not claim peer delivery from `queued`, `written`, local TX markers or console-log presentation alone.

## 16. Standing reminders

- Current recorded source: `dev@e6e74a45237abaf488cb815c2bba185810215c9d`.
- Current recorded source CI: run `33959407933` SUCCESS.
- Current evidence: `node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198`, reviewer state still `none`.
- Current active TODO inventory entry: TODO_004, status `DEFERRED`, dependency now satisfied.
- `events`/`wait_events` are no longer machine operations at this checkpoint.
- `.console.log` is presentation/audit, not delivery evidence; main `.log` remains forensic truth.
- Published snapshots remain immutable.
- Future snapshots continue the mandatory order: refetch exact state -> create snapshot -> read-back/verify -> advance index.