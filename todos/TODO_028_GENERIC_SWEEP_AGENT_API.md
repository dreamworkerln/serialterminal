# Generic long-running sweep API TODO

TODO-ID: TODO_028
Status: OPEN

## Purpose

Implement a maintained **generic, deliberately dumb sweep executor** inside the existing `serialterminal agent` JSONL API.

The sweep executor exists to run long deterministic measurement plans locally without one LLM/tool turn per sample. It must execute exactly the plan it was given, report mechanical execution progress, and leave interpretation of the resulting radio/protocol evidence to the caller/reviewer.

The immediate motivating workload is the LoRa-Chatter PHY/payload sweep, but the sweep engine and machine API must not be designed as a Chatter functional test.

## Current behavior

Today a hardware executor drives repeated measurements through low-level operations such as:

```text
send_line
-> observe
-> model/tool orchestration
-> next send_line
-> observe
...
```

For long sweeps this introduces large avoidable gaps between samples and makes timing-sensitive orchestration depend on model/tool turns.

Two recent physical runs also demonstrated why the repeated orchestration loop should move into maintained local code:

```text
node_observations@707bfc07ddeaddb1a778bc87ebe90df2e129e8b6
node_observations@7fdfc328fa70e200d40ee6636dc5de2523bc816c
```

Those runs are historical evidence only. This TODO must not modify `node_observations`.

The existing agent API already has the right process model for long waits:

- one long-lived `python3 serialterminal.py agent` process;
- correlated JSONL request/response by `id`;
- no unsolicited JSON messages;
- asynchronous `observe` long-poll with cursor + timeout;
- ordinary requests may complete while an `observe` request remains pending.

The sweep API should extend that model rather than create a second process/protocol.

Current TX semantics are intentionally weaker than device-operation completion:

```text
send_line
    -> queued

later tx event
    -> written
```

`queued` means only that the SerialTerminal TX queue accepted the item. `written` means only that the transport write completed; it does not prove peer receipt, firmware command completion, RF completion, ACK completion, or that it is safe to mutate radio configuration.

Therefore a deterministic sweep must add a higher-level operational settlement barrier through its adapter. The generic session core must not learn controller/radio semantics in order to provide that barrier.

## Target behavior

Add a generic long-running sweep-job facility to the existing agent API.

Conceptual operations:

```text
sweep_start
sweep_observe
sweep_cancel
sweep_close
```

Exact final names may change during implementation if repository conventions strongly justify it, but the semantics below are the acceptance contract.

A sweep:

- executes a caller-supplied traversal plan;
- executes exactly the requested repetition count;
- applies and verifies each requested coordinate through a measurement adapter;
- performs samples sequentially according to the plan;
- exposes bounded cursor-based execution events and progress;
- can be cancelled;
- reaches an explicit terminal state;
- does not interpret measurement quality;
- does not autonomously alter the requested traversal or repetition count.

## Core abstraction boundary

The intended dependency direction is:

```text
serialterminal agent JSONL frontend
              |
              v
      generic sweep-job API
              |
              v
       generic sweep engine
              |
              v
    measurement adapter contract
              |
              +--> first adapter/use case: Chatter reliable USER
              +--> future adapters/use cases
```

### Generic sweep engine owns

- axes / coordinates / traversal order;
- exact repetition count;
- job lifecycle;
- current coordinate and repetition index;
- cancellation;
- bounded event retention;
- long-poll wakeup;
- mechanical progress accounting;
- explicit execution failure state.

### Measurement adapter owns

- how a requested coordinate is applied to the target;
- how the applied coordinate is verified;
- how one sample is initiated;
- how the adapter knows that one sample is settled enough for the next sample to begin;
- adapter-specific control/setup/cleanup needed to perform the measurement safely.

For the first Chatter use case this may internally involve commands such as `/sf`, `/config`, reliable-USER settlement, or other profile-specific mechanics. Those details are **not generic sweep semantics**.

### Caller/reviewer owns

- interpreting ACK/CRC/HDR/retry/RSSI/SNR evidence;
- deciding whether a point was good/bad/interesting;
- deciding whether another sweep should be run;
- deciding whether a later sweep should use a different repetition count.

### Adapter registry / dependency boundary

The generic sweep engine and generic agent dispatch must not branch on concrete adapter names.

Forbidden shape:

```python
if adapter == "chatter.reliable_user":
    ...
```

Required shape:

```text
adapter name
    -> generic registry/factory lookup
    -> SweepAdapter implementation
```

The generic engine knows only the adapter interface. Concrete controller adapters live on the controller/profile/scenario side of the dependency boundary and register through the composition layer.

This is required by `ARCHITECTURE.md`: the generic core must not learn concrete controller commands, names, protocol outcomes or one-off compatibility behavior.

## Session ownership and concurrency

### Already-open sessions only

`sweep_start` operates only on **already-open SerialTerminal sessions**.

The caller remains responsible for:

```text
discover
open
sweep_start
```

The sweep facility does not discover devices, open transports or take ownership of connection creation.

The adapter validates that participating sessions exist and satisfy its requirements, for example selected profile, distinct identities or other adapter-specific prerequisites.

### One active sweep per agent process

The first maintained API supports at most one active sweep job per `serialterminal agent` process:

```text
max_active_sweeps = 1
```

A second `sweep_start` while another sweep is `running` or `cancelling` must fail mechanically with a stable busy error.

This intentionally avoids pretending that different session sets are independent measurement domains. In particular, two disjoint session pairs may still share the same physical RF environment.

Parallel active sweeps are out of scope until a future generic resource-domain ownership model is explicitly designed.

### Exclusive mutation ownership of participating sessions

A successful `sweep_start` atomically acquires exclusive **mutation ownership** of all participating sessions for the lifetime of the active sweep.

Acquisition is all-or-nothing:

```text
check all participating sessions
-> acquire all
OR
-> acquire none
```

No partial ownership may remain after a failed start.

While a sweep owns a session, external read-only operations may remain available, including where safe:

```text
status
observe
list_sessions
sweep_observe
```

External mutating operations on an owned session must be rejected before side effects occur, including at least:

```text
send_line
send_bytes
close
another sweep using the session
future mutating session operations
```

Use one generic busy/ownership error model rather than controller-specific command filtering. Conceptually:

```json
{
  "code": "session_busy",
  "details": {
    "session": "s1",
    "owner": {
      "kind": "sweep",
      "sweep_id": "sw1"
    }
  }
}
```

The generic layer must not inspect `send_line` text to decide whether a command is dangerous. During ownership, all external mutation is blocked consistently.

Mutation ownership is released on terminal sweep transition:

```text
completed
failed
cancelled
agent shutdown / worker fatal cleanup
```

It is **not** held until `sweep_close`. `sweep_close` releases retained job metadata/events, whereas session mutation becomes available again once the active operation is terminal.

Release must be guaranteed through failure-safe/finally-style cleanup so an exception cannot leave a session permanently busy.

### Agent concurrency contract

TODO_028 changes the current concurrency model materially.

Today only `observe` is asynchronous at the JSONL frontend while ordinary commands are handled by the main request reader. A running sweep introduces a background worker that actively mutates participating sessions.

Therefore implementation must define one explicit ownership/concurrency gate shared by:

- background sweep mutation;
- ordinary `send_line` / `send_bytes`;
- `close`;
- future session mutations.

Do not protect only sweep code with a private lock while leaving other mutation paths unaware of ownership.

The ownership check and mutation admission must be centralized at the session-management boundary so new mutating operations cannot accidentally bypass sweep ownership.

Read-only observation of owned sessions remains separate from mutation admission.

### Non-participating sessions and physical-environment isolation

Sweep mutation ownership applies only to the sessions explicitly declared as participating/owned by the sweep plan.

A sweep does **not** claim that the surrounding physical measurement environment is isolated from unrelated sessions, processes or external devices.

For example, while `sw1` owns `s1` and `s2`, an unrelated `send_line(s3, ...)` is not blocked merely because `s3` might transmit in the same RF environment.

Therefore the caller/measurement coordinator is responsible for keeping all non-participating sessions/devices that could affect the experiment quiescent.

This is a documented boundary, not a hidden guarantee of the generic sweeper.

If future workloads require stronger isolation, the plan/API may be extended with additional generic owned resources such as:

```text
owned_sessions
resource domains
measurement-environment leases
```

Those resources may be owned without directly participating in samples, but such a resource model is outside this TODO.

## Dumb repetition semantics

`repetitions=N` means exactly:

```text
perform N samples for every requested coordinate/direction in the plan
```

Examples:

```text
repetitions=3
    -> exactly 3 samples

repetitions=10
    -> exactly 10 samples
```

There is no built-in policy:

```text
3 samples
-> inspect anomaly
-> automatically extend to 10
```

That adaptive policy is explicitly out of scope for the generic sweeper.

If a caller first requests 3 repetitions, later analyzes the logs, and decides it wants 7 additional samples or a fresh 10-sample sweep, it issues another explicit sweep request.

The generic engine must never change `repetitions` based on observed protocol/radio content.

## No measurement analytics in the sweeper

The generic sweep engine must not classify samples or points as:

```text
CLEAN
DEGRADED
anomalous
CRC problem
HDR problem
ACK timeout
retry
good/bad RF point
```

The engine may only report execution facts such as:

```text
job running/completed/failed/cancelled
coordinate applied
sample completed
sample could not be executed
completed_samples / total_samples
current coordinate
current repetition
```

A legitimate measured radio/protocol failure may still be a successfully executed sample if the adapter reached its defined settled boundary. Detailed meaning remains in the normal SerialTerminal logs and is analyzed afterward.

An **execution failure** is different: for example, the requested coordinate cannot be applied/verified, the target/session is unavailable, or the adapter cannot establish a safe sample boundary. Such failure may terminate the sweep with a mechanical reason.

## Plan model

The API must not be hard-coded to BW500, specific SF values, payload lengths, or a fixed Chatter experiment.

The generic plan should represent:

- adapter identifier / measurement kind;
- participating session(s);
- constant parameters;
- ordered sweep axes and values;
- exact repetitions;
- deterministic traversal order;
- adapter-specific options only within an adapter-owned namespace.

Prefer an ordered axis representation rather than relying on JSON object member order for traversal semantics.

Conceptual example only:

```json
{
  "id": 100,
  "op": "sweep_start",
  "adapter": "chatter.reliable_user",
  "sessions": ["s1", "s2"],
  "plan": {
    "constants": {
      "frequency_hz": 470000000,
      "power_dbm": 2,
      "bandwidth_hz": 500000
    },
    "axes": [
      {"name": "sf", "values": [7, 8, 9, 10, 11, 12]},
      {"name": "payload_bytes", "values": [1, 8, 16, 32, 64, 96, 128, 160, 180, 200]},
      {"name": "direction", "values": ["s1>s2", "s2>s1"]}
    ],
    "repetitions": 3
  }
}
```

The exact adapter and plan schema must be designed so the generic engine treats coordinates opaquely and adapter-specific validation remains in the adapter.

## Parameter application and verification

Verification exists to prove that the requested sweep coordinate was actually applied before samples at that coordinate begin.

It is **not** a functional test of a particular command.

Generic contract:

```text
requested coordinate
-> adapter applies coordinate
-> adapter verifies actual coordinate
-> samples for that coordinate may begin
```

For the first Chatter adapter, applying/verifying an SF may happen to require:

```text
send /sf N
-> observe saved acknowledgement
-> send /config
-> observe configuration
-> verify requested values
```

That sequence is an implementation detail of the Chatter adapter. The generic sweep engine knows only whether the requested coordinate was successfully applied and verified.

The previous orchestration bug where code waited for configuration output before sending the command that produces it must be covered in adapter tests, but must not shape the generic sweep abstraction.

## Sample serialization

The first Chatter reliable-USER adapter requires one measured USER transaction in flight across both participating nodes at a time.

That is an adapter-level measurement invariant, not a universal sweep rule.

The generic engine must nevertheless provide a sequential sample lifecycle suitable for adapters that require:

```text
start one sample
-> wait until adapter reports sample settled
-> record mechanical completion
-> start next sample
```

Do not pre-submit future samples in a way that violates the adapter's declared sample boundary.

### Operational settlement barrier

Generic traversal must never advance merely because a host TX reached `queued` or `written`.

For every sample/coordinate transition:

```text
adapter apply requested coordinate
-> adapter verify requested coordinate
-> adapter start one sample
-> adapter wait until that sample is operationally settled
-> generic engine records mechanical sample completion
-> only then next sample or next coordinate mutation may begin
```

The adapter defines operational settlement using controller/protocol semantics needed only for synchronization.

For the first Chatter reliable-USER adapter this prevents cases such as:

```text
USER queued/written
-> radio transaction still active
-> host changes SF/BW/frequency/power
```

The next radio/config mutation is forbidden until the adapter reports the active sample settled.

This is synchronization/control, not analytics. The adapter may need to observe ACK/terminal protocol state to know that it is safe to proceed, but the generic sweep result must not classify the quality of that ACK/outcome.

### Bounded adapter phases and cancellation-aware waits

Every adapter phase that may block must have an explicit finite deadline and must observe sweep cancellation.

This applies at least to:

```text
prepare
apply coordinate
verify coordinate
start/sample operation where blocking is possible
wait for sample settlement
cleanup
```

No adapter wait may depend on an unbounded firmware/protocol/event wait.

Cancellation contract:

```text
cancel requested
-> currently running adapter wait is awakened/cooperatively cancelled
   OR reaches its explicit bounded deadline
-> adapter reaches the safest available bounded boundary
-> cleanup runs with its own finite deadline
-> job reaches cancelled or failed
```

A physical operation such as an RF transmission does not have to be interrupted unsafely in the middle merely to make cancellation instantaneous. Safe operational settlement takes priority over immediate abort.

However, `state="cancelling"` must itself be bounded: a missing event, stalled device or buggy adapter may not leave the job cancelling indefinitely.

If cancellation-aware settlement or cleanup cannot complete before its defined deadline, the job must terminate as a bounded failure with a mechanical reason rather than remain permanently active.

The generic engine must provide the cancellation signal/deadline plumbing; each adapter is responsible for honoring it in every blocking phase.

## Existing agent process and logs

Do not create a separate `run-chatter-sweep` child API process as the primary machine interface.

The machine-facing entry point remains:

```bash
python3 serialterminal.py agent
```

The existing process remains owner of:

- sessions;
- transports;
- reconnect behavior;
- `.log` forensic record;
- `.console.log` human-console record.

The sweep facility must not reconstruct, rewrite or append its own versions of those logs.

No additional `sweep-results.jsonl` durable evidence file is required by this TODO.

### Mechanical sweep records in the existing forensic log

Sweep lifecycle/progress events are first-class actions of SerialTerminal and must also be written by the existing `RunLog` into the normal forensic `.log`.

Use a dedicated record category such as:

```text
[SWEEP]
```

with mechanical fields such as:

```text
sweep_id
event_seq
event kind
coordinate
repetition
opaque sample id where applicable
execution state/reason
```

The in-memory sweep event sequence and the forensic `[SWEEP]` event sequence must use the same job-local identifier so an API progress event can be located precisely in the durable forensic timeline.

These records must not add RF/protocol analytics such as CLEAN/DEGRADED, CRC interpretation or ACK quality.

`sweep_close` may discard bounded in-memory job history, but it must not remove or rewrite already persisted `[SWEEP]` records.

Detailed ACK/retry/CRC/HDR/RSSI/SNR evidence is read from the existing logs after/during the run by the caller/reviewer as needed.

## Long-running job API

### Request/response invariant

Preserve the current JSONL rule:

```text
one request id
-> exactly one correlated response
```

The server emits no unsolicited sweep JSON messages.

Do not introduce a second push protocol.

### `sweep_start`

`sweep_start` validates the request, creates the job and returns promptly.

Conceptual response:

```json
{
  "id": 100,
  "ok": true,
  "result": {
    "sweep_id": "sw1",
    "state": "running",
    "total_samples": 360,
    "events": {
      "cursor": 0,
      "max_window": 100,
      "retention": 4096
    }
  }
}
```

The server must advertise at job creation:

- initial event cursor;
- maximum event window it will return in one `sweep_observe`;
- bounded event retention capacity;
- mechanically known total sample count when it is determinable from the plan.

If asynchronous adapter preparation later fails, that is a sweep job failure reported through job state/events, not a failure of the already successful `sweep_start` request.

### Event cursor semantics

Sweep execution events use a monotonically increasing gap-free job-local sequence.

Request cursor semantics are strictly:

```text
cursor = last event sequence already consumed by this client
return events with seq > cursor
```

The cursor belongs to the reader. Reading or not reading events must not control or throttle sweep execution.

If retained events are:

```text
101 .. 500
```

then:

```text
head_cursor = 500
oldest_retained_event_seq = 101
oldest_valid_cursor = 100
```

Validation is exact:

```text
cursor < oldest_valid_cursor
    -> sweep_cursor_expired

cursor == oldest_valid_cursor
    -> valid, first returned event may be oldest_retained_event_seq

oldest_valid_cursor <= cursor <= head_cursor
    -> valid

cursor > head_cursor
    -> invalid_sweep_cursor
```

Negative, boolean, floating-point and string cursors are invalid. Duplicate reads using the same valid cursor are allowed and return the same retained range subject to the requested window.

Use the unambiguous API term `oldest_valid_cursor` rather than `oldest_cursor`.

The tuple:

```text
events
response.cursor
head_cursor
state
progress
```

must be captured from one coherent job snapshot under the same synchronization boundary. Do not compose these fields from independently changing state.

### `sweep_observe`

Conceptual request:

```json
{
  "id": 101,
  "op": "sweep_observe",
  "sweep_id": "sw1",
  "cursor": 200,
  "window": 1000000,
  "timeout_ms": 30000
}
```

The caller requests its desired window size.

The server returns at most:

```text
min(requested window, advertised max_window)
```

There is no separate `more` flag.

Conceptual response:

```json
{
  "id": 101,
  "ok": true,
  "result": {
    "events": [
      {
        "seq": 201,
        "kind": "sample_completed",
        "coordinate": {
          "sf": 8,
          "payload_bytes": 64,
          "direction": "s1>s2"
        },
        "repetition": 2
      }
    ],
    "cursor": 201,
    "head_cursor": 587,
    "state": "running",
    "progress": {
      "completed_samples": 580,
      "total_samples": 900,
      "current": {
        "coordinate": {
          "sf": 9,
          "payload_bytes": 16,
          "direction": "s2>s1"
        },
        "repetition": 2
      }
    },
    "timed_out": false
  }
}
```

Meaning:

```text
response.cursor
    last event returned to this reader

head_cursor
    newest job event existing at the response snapshot

response.cursor < head_cursor
    more retained events currently exist; caller may immediately read the next window
```

No `more` boolean is needed.

### Long-poll wakeup

`sweep_observe` mirrors the established `observe` long-poll model.

A pending request wakes and returns when the first applicable condition occurs:

- at least one event with `seq > cursor` is available;
- the sweep changes to a terminal state;
- `timeout_ms` expires;
- the request is otherwise cancelled by process shutdown/error semantics.

If no event arrives before timeout:

```json
{
  "events": [],
  "cursor": 201,
  "head_cursor": 201,
  "state": "running",
  "progress": {
    "completed_samples": 200,
    "total_samples": 900
  },
  "timed_out": true
}
```

The caller obtains reactive completion by keeping a `sweep_observe` long-poll outstanding. The server does not push completion spontaneously.

While `sweep_observe` is pending, unrelated ordinary JSONL requests must remain serviceable, consistent with current asynchronous `observe` behavior.

### State snapshot vs event history

Every `sweep_observe` response carries both:

```text
events
    retained ordered changes after caller cursor

state/progress
    current job snapshot at response time
```

A caller must not need to replay the entire event history to know current progress or terminal state.

Terminal completion is determined from `state`, not solely from seeing a `sweep_completed` event.

Expected states:

```text
running
cancelling
completed
failed
cancelled
```

### Bounded retention and expired cursors

Sweep events are retained in bounded memory.

If a caller falls behind beyond retained history, the server must never silently skip the gap.

Return a structured API error such as:

```json
{
  "id": 500,
  "ok": false,
  "error": {
    "code": "sweep_cursor_expired",
    "message": "requested sweep cursor is older than retained event history",
    "requested_cursor": 120,
    "oldest_valid_cursor": 946,
    "oldest_retained_event_seq": 947,
    "head_cursor": 5042
  }
}
```

Exact field placement should follow existing agent error-envelope conventions, but the semantic requirement is mandatory: lost event ranges are explicit.

### Job failure vs API request failure

Do not conflate these layers.

A valid `sweep_observe` request for a sweep that later failed is still:

```json
{"ok": true, "result": {"state": "failed", "...": "..."}}
```

Use `ok:false` for request/API errors such as:

- unknown `sweep_id`;
- invalid cursor/window/timeout type or range;
- expired cursor;
- invalid operation state for the requested control.

A sweep execution failure is job state, not JSONL transport/request failure.

### `sweep_cancel`

Cancellation is a request, not proof that cancellation has completed.

Conceptual response:

```json
{
  "id": 300,
  "ok": true,
  "result": {
    "sweep_id": "sw1",
    "state": "cancelling"
  }
}
```

The adapter/engine reaches a safe sample boundary as defined by its contract, performs required cleanup, then publishes terminal `cancelled` state.

All waits on that path are cancellation-aware and deadline-bounded. Cancellation must therefore converge to a terminal `cancelled` or `failed` state within the adapter's documented finite bounds; it may not remain indefinitely in `cancelling`.

The caller observes the terminal transition through `sweep_observe`.

### `sweep_close` and bounded terminal-job lifetime

Completed/failed/cancelled jobs must have an explicit bounded lifecycle so a long-lived agent process does not retain job state forever.

Prefer an explicit close/release operation analogous to session `close`.

`sweep_close`:

- succeeds only for terminal jobs;
- releases retained sweep events/result/progress state;
- makes later operations on that `sweep_id` return `unknown_sweep`;
- must not delete or alter SerialTerminal log files.

Do not auto-destroy a job merely because one reader observed its terminal event; reads may be retried and callers may need to drain retained windows.

Explicit close alone is not a sufficient memory bound because clients can forget to call it.

The agent must enforce a hard global bound on retained terminal jobs, for example a fixed `max_retained_terminal_sweeps`. When the bound is exceeded, evict the oldest terminal job state/events deterministically. Already persisted forensic `[SWEEP]` records remain available.

The exact limit is an implementation choice, but it must be:

- finite;
- documented;
- tested;
- independent from whether a caller behaves correctly.

A terminal TTL may be added later if justified, but a deterministic count bound is required for this TODO.

## Progress event model

Keep the generic event vocabulary small and execution-oriented.

Candidate event kinds:

```text
sweep_started
coordinate_started
sample_completed
coordinate_completed
sweep_completed
sweep_failed
sweep_cancelled
```

Avoid protocol-analysis events in the generic stream.

The exact event set may be reduced further during implementation if state/progress snapshots make some entries redundant.

A `sample_completed` event should contain enough mechanical identity to locate the corresponding activity in logs:

- coordinate;
- repetition index;
- participating session/direction identity where part of the coordinate;
- optional adapter-owned opaque sample identifier if needed for log correlation.

It should not contain an interpretation of whether that sample was RF-good or RF-bad.

## Progress semantics

Progress is mechanical:

```text
completed_samples
total_samples
current coordinate
current repetition
current generic phase when useful
```

If the plan contains 6 SF values × 10 payload values × 2 directions × 3 repetitions:

```text
total_samples = 360
```

The caller can therefore display exact progress without reading or interpreting radio logs.

Reading progress/events must not slow, pace, or otherwise control the measurement loop.

## First adapter/use case: Chatter reliable USER

The first maintained adapter should prove that the generic API can support the current LoRa-Chatter need.

It must accept sweep coordinates/options sufficient for at least:

- two already-open target sessions;
- frequency;
- TX power;
- bandwidth;
- spreading factor;
- USER payload byte length;
- direction;
- exact repetitions from the generic plan.

The Chatter adapter may perform controller-specific preparation such as establishing a known state before measurement. That preparation exists solely to make the requested measurement well-defined.

It must not introduce generic sweep semantics for:

- heartbeat;
- diagnostic mode;
- echo mode;
- Chatter command strings;
- ACK interpretation;
- CRC/HDR classification;
- retry analysis.

Where the adapter must observe protocol output to know that a control change or sample has reached its operational boundary, it may do so internally. This is synchronization/control, not measurement analytics.

## Non-goals

- no automatic anomaly detection policy in the generic engine;
- no automatic 3-to-10 repetition extension;
- no CLEAN/DEGRADED/FAILED RF classification;
- no CRC/HDR/retry/ACK analytics in generic sweep results;
- no separate primary `run-chatter-sweep` JSONL process;
- no unsolicited server push protocol;
- no direct Bleak/pyserial bypass;
- no duplicate transport/session implementation;
- no new durable sweep evidence file required;
- no firmware changes;
- no `node_observations` changes;
- no physical sweep during this source-development task unless separately requested.

## Implementation

- [x] inspect current agent async request/observe architecture and reuse its request/response conventions;
- [x] inspect `scripts/run-chatter-scenario` only for reusable orchestration mechanics, not as the sweep abstraction;
- [x] define generic sweep plan/job/event data model;
- [x] define measurement-adapter interface;
- [x] define generic adapter registry/factory with no concrete-adapter branching in the engine/dispatch;
- [x] implement generic sweep engine independent of Chatter semantics;
- [x] require already-open participating sessions;
- [x] implement one-active-sweep-per-agent-process admission;
- [x] implement atomic all-or-nothing mutation ownership for participating sessions;
- [x] centralize ownership checks for all session mutation paths;
- [x] release ownership on every terminal/error/shutdown path;
- [x] define cancellation signal/deadline plumbing shared by engine and adapters;
- [x] require finite deadlines for every blocking adapter phase, including settlement and cleanup;
- [x] document that physical-environment isolation beyond declared owned sessions is caller responsibility;
- [x] add agent API dispatch/validation for `sweep_start`;
- [x] implement bounded per-job event history with monotonic gap-free cursor;
- [x] implement exact `oldest_valid_cursor` / future-cursor validation and coherent event/progress snapshots;
- [x] implement `sweep_observe` long-poll with requested `window`, advertised `max_window`, `head_cursor`, timeout and progress snapshot;
- [x] implement explicit expired-cursor error without silent event loss;
- [x] preserve one-request/one-response and no-unsolicited-JSON rules;
- [x] keep unrelated agent requests serviceable while `sweep_observe` waits;
- [x] implement `sweep_cancel` request/terminal-state separation;
- [x] implement explicit terminal-job `sweep_close` resource release;
- [x] enforce a finite global retained-terminal-job bound even when callers never close jobs;
- [x] implement exact fixed repetition semantics;
- [x] implement first Chatter reliable-USER measurement adapter without leaking its semantics into the generic engine;
- [x] verify adapter applies and verifies requested coordinates before sampling;
- [x] ensure sequential sample boundary for the first adapter;
- [x] ensure existing forensic and console logs remain owned by normal SerialTerminal logging;
- [x] persist mechanical sweep events through existing RunLog `[SWEEP]` records using the same job-local event sequence as the API ring;
- [x] update `AGENT_API.md` with final exact schema and semantics;
- [x] update architecture docs if the new sweep/adapter dependency boundary requires it.

## Validation

Generic API/engine tests:

- [x] `sweep_start` returns promptly with unique sweep id;
- [x] only one active sweep is allowed per agent process;
- [x] second concurrent `sweep_start` fails without disturbing the active job;
- [x] ownership acquisition for participating sessions is atomic all-or-nothing;
- [x] external `send_line`, `send_bytes` and `close` on owned sessions fail before side effects;
- [x] read-only `status` / ordinary `observe` remain usable for owned sessions where documented;
- [x] ownership is released on completed/failed/cancelled/shutdown/error paths;
- [x] cancellation wakes or otherwise bounds an adapter blocked in apply/verify/sample-settlement wait;
- [x] missing firmware/protocol events cannot leave a sweep permanently running/cancelling;
- [x] cleanup is deadline-bounded and cleanup timeout produces terminal mechanical failure;
- [x] non-participating session mutation is not implicitly blocked by sweep ownership;
- [x] documented tests make clear that RF/environment isolation outside declared ownership remains caller responsibility;
- [x] advertised `max_window` and retention are stable and enforced;
- [x] `repetitions=3` executes exactly 3 samples per requested coordinate;
- [x] `repetitions=10` executes exactly 10 samples per requested coordinate;
- [x] no runtime condition changes the requested repetition count;
- [x] traversal follows the declared ordered axes deterministically;
- [x] progress totals and current coordinate/repetition are mechanically correct;
- [x] requested window larger than `max_window` returns only `max_window` events;
- [x] `response.cursor` is the last returned event sequence;
- [x] `head_cursor` reports producer head independently of reader position;
- [x] caller can drain backlog over multiple windows without a `more` flag;
- [x] long-poll wakes on new event;
- [x] long-poll wakes on terminal transition;
- [x] long-poll returns `timed_out:true` when no wake condition occurs;
- [x] unrelated agent request can complete while `sweep_observe` is pending;
- [x] `oldest_valid_cursor` boundary is exact and off-by-one safe;
- [x] cursor greater than `head_cursor` returns explicit invalid-cursor error;
- [x] negative/bool/float/string sweep cursors are rejected;
- [x] duplicate valid cursor reads are deterministic;
- [x] events/cursor/head/state/progress come from one coherent snapshot;
- [x] expired cursor returns explicit structured error;
- [x] job execution failure is returned as terminal job state with `ok:true` observe response;
- [x] malformed/unknown sweep request is returned as API `ok:false`;
- [x] cancellation first returns/enters cancelling and later reaches terminal cancelled;
- [x] `sweep_close` rejects non-terminal jobs and releases terminal jobs;
- [x] closed sweep ids become unknown and retained memory is released;
- [x] forgotten terminal jobs cannot grow memory without bound; oldest terminal retention is evicted at the configured cap;
- [x] no unsolicited JSON is emitted;
- [x] generic agent/sweep engine contains no concrete `chatter.reliable_user` branch or Chatter command knowledge;
- [x] mechanical sweep events are present in the existing forensic log and correlate 1:1 by sweep event sequence.

Adapter boundary tests:

- [x] generic engine tests contain no Chatter command/parser knowledge;
- [x] Chatter adapter accepts already-open compatible sessions and does not perform discover/open;
- [x] Chatter adapter applies/verifies requested sweep coordinates;
- [x] adapter never waits for a response to a command it has not actually issued;
- [x] `queued`/`written` alone never satisfy the sample settlement barrier;
- [x] every blocking Chatter adapter phase has an explicit finite deadline;
- [x] Chatter adapter waits observe cancellation and converge to terminal state within documented bounds;
- [x] first adapter does not pre-submit the next sample before the previous sample reaches its operational settle boundary;
- [x] no SF/BW/frequency/power mutation begins while the preceding reliable USER sample is still operationally active;
- [x] protocol content used only for operational synchronization does not become generic point analytics;
- [x] existing `scripts/run-chatter-scenario` behavior remains passing if any reusable mechanics are extracted.

Repository gates:

- [x] relevant targeted tests PASS;
- [x] full repository validation required by `AGENTS.md` PASS;
- [x] final BASE..HEAD diff reviewed, especially deletions/refactors;
- [x] GitHub Actions for the resulting implementation checkpoint PASS.

No real hardware sweep is required to close the source implementation/automated-validation portion unless a later task explicitly adds that gate.

## Findings

### Design correction after initial TODO creation

The original TODO text mixed three separate concerns:

1. generic long-running sweep execution;
2. Chatter-specific sample/control synchronization;
3. experiment analysis/adaptive repetition policy.

That boundary is rejected.

The maintained design is now:

```text
generic sweeper
    executes exactly requested plan

measurement adapter
    makes one requested measurement operationally possible

caller/reviewer
    interprets evidence and chooses future plans
```

### Reactive completion without push

Existing agent `observe` already establishes the desired pattern:

```text
cursor + timeout long-poll
one request -> one response
no unsolicited JSON
```

Sweep progress/completion should reuse that pattern through `sweep_observe`.

## Known limitations

- The first adapter/use case is Chatter reliable USER because that is the immediate hardware need.
- The first API version deliberately supports only one active sweep job per agent process; parallel measurement domains require a separate future resource-ownership design.
- Exclusive mutation ownership covers only declared participating sessions. Isolation of unrelated sessions/devices and the surrounding physical RF environment remains caller/coordinator responsibility.
- Plan/adapter schema is now implemented and documented in `AGENT_API.md`; future schema evolution must preserve the generic-vs-adapter boundary.
- Job event history is operational progress, not a replacement for forensic logs.
- This TODO does not define cross-process persistence/resume of a sweep job after the agent process exits.
- This TODO does not define adaptive experiment orchestration above the sweeper.

## Historical interrupted implementation checkpoint

Source implementation stopped on operator request at:

```text
dev@a131ac14ea5956d4511c0695aeff10f1760482db
```

This checkpoint contains a **partial implementation**, not an accepted/validated TODO closure.

Implemented so far:

- generic sweep plan normalization and schema hygiene for duplicate/colliding axes, empty axis values, invalid repetitions, serialized plan size, axis count and total Cartesian sample bound;
- generic `SweepJob` / `SweepJobManager` with fixed deterministic repetitions/traversal, bounded event retention/window, job-local cursors, terminal retention bound, cancellation state and explicit close;
- profile-owned sweep-adapter registry boundary;
- agent integration for `sweep_start`, `sweep_observe`, `sweep_cancel`, `sweep_close`;
- capability-limited adapter context for declared sessions;
- session mutation ownership gates for external `send_line`, `send_bytes` and `close`;
- async runner treatment of `sweep_observe` alongside existing `observe`;
- first `chatter.reliable_user` adapter draft with preparation, radio apply/verify, sequential reliable-USER settlement, cancellation cleanup and airtime-aware settlement timeout;
- initial generic, ownership/async and Chatter adapter regression tests;
- firmware-format review caught that Chatter `formatMilli()` canonicalizes values such as `470.000 -> 470` and `500.000 -> 500`; the adapter was changed to parse/compare numeric SAVED values instead of matching padded strings.

Important implementation commits on the interrupted path:

```text
c87e200d4d4ef3d43b265fb1365554084934ed00  sweep: add generic job engine
665404041dd19901a0a87802954d9a42e1611064  sweep: add Chatter reliable-user adapter
7fb27bd0e49c4efe39471cfd51f85d2a25fdebd8  sweep: expose profile adapter registry
87f5eaee7604a8e69451ad85ea9ef6f42b188cbc  sweep: keep generic profile adapter-free
d49af2f4253308af8c16ddff8ed48ef4918c118b  sweep: register Chatter adapter through profile
2dfaf0410b3784f141ac377f70190ed9e1971f6a  sweep: scope adapter context per job
508783a33610e8ba052c14effe16eb867fe806d4  sweep: integrate jobs with agent session ownership
5eb1f2c9dbcdfbf00a83181ee53042f090374bb4  sweep: join retained workers on shutdown
e4ab9ff95da04dba22356f62a6ee75a1ae324343  test: cover generic sweep job semantics
f5c88f079f391969570b87719e276c1b74f40d77  test: cover sweep ownership and async observe
73daf7d31c40fb9f5187f9a48404aaa49c068b1a  test: cover Chatter sweep settlement boundary
eaca564106be36788e20cff2072c013243d9883d  test: fix sweep lint imports
027a8045415d6ce904c6e31e44a8efc95cd5e0f2  test: fix sweep lint imports
ec05bfd5b068eef5a465397325fa6ab678a3970b  test: align agent shutdown fake with sweep hooks
f942ff927ed540fbe34e40bd63ed60eb518adbef  sweep: parse canonical Chatter saved values
a131ac14ea5956d4511c0695aeff10f1760482db  test: mirror firmware canonical radio formatting
```

Validation actually observed:

- GitHub Actions run `36283994197`: compile PASS; ruff FAILED only on two unused test imports; tests not run.
- GitHub Actions run `36284047762`: compile PASS; ruff PASS; complexity PASS; pytest **1 failed, 182 passed** because the existing shutdown test double lacked new `cancel_sweeps/join_sweeps` hooks. That test double was updated at `ec05bfd...`.
- GitHub Actions run `36284195278` on final interrupted implementation checkpoint `a131ac14...`: compile PASS; ruff PASS; complexity PASS; pytest **1 failed, 182 passed**.
- Remaining current failure: `tests/test_chatter_sweep_adapter.py::test_apply_then_verify_issues_config_only_after_saved_transitions` times out in adapter `apply`. The immediately preceding change intentionally made the fake transcript mirror firmware canonical numeric formatting; the implementation has **not** been debugged further because the operator requested a stop.
- No local pytest/compile run was executed in this ChatGPT environment.
- No hardware validation or real sweep was performed.

Do not call this checkpoint green, accepted, implemented-complete, or ready for hardware use.

### Resume point

Before any further implementation:

1. read the latest handoff snapshot/index;
2. refetch actual `dev`;
3. reproduce the single failing Chatter adapter test from GitHub Actions `36284195278`;
4. inspect the numeric SAVED parser/test fake interaction introduced at `f942ff9...` / `a131ac1...`;
5. do not change architecture while fixing that narrow failure unless a real contradiction is found;
6. after targeted tests pass, run the full repository gates and only then update API/architecture/logging/skill docs to the final exact contract;
7. perform the mandatory BASE..HEAD deletion/comment/function-definition review before declaring the source checkpoint accepted.

## Resumed implementation completion

Implementation resumed after the recorded interruption and was completed in small CI-gated checkpoints. Material post-handoff checkpoints include:

```text
0a4851fe6ec9546ae6c26bc6816b46e906e2effc  fix: stabilize Chatter radio value parsing
47c498d8be63f6d5593f5afeb786e02e9a1d194e  sweep: harden generic job publication
32ea573ef4abdd8fab5bfa8d04bf1884e3f1abe7  test: share sweep adapter factory identity
bb4786c5c97a66ebd780abbb379e0cec3c20796b  test: lock sweep JSONL error semantics
a90efdffdca9b35ba97922937dfa00734ccc4876  chatter: harden sweep settlement correlation
69bc5206e0b3526a1a319280db3d7109a1df32ec  test: fix forensic correlation lint
c4f0ae1eec8b097a37ea51c1ae0041a194940db1  chatter: guarantee sweep telemetry visibility
c0849a1e0cc481c8648072fb1a7dd143d98a1ca5  docs: document sweep agent API
907e6ee724efa3726838ef88f280eae7fd7ca6e9  docs: fix sweep direction example
a82f0c2b189c38c8a5baf0b6d87ab88c612963a7  docs: record sweep architecture and logging
999076af690fec2b8a134ba08e154704ccb918c3  docs: teach agent skill sweep workflow
73b4488e690994001008f790ba5f5cba279dc577  chatter: correlate sweep delivery by WAIT_ACK
d868d026c05dac9373a47c0935673836432f9073  test: lock sweep lifecycle deadlines
```

Important source-review findings resolved before closure:

- Chatter firmware `formatMilli()` canonicalizes trailing decimal zeroes; adapter parsing now compares numeric values rather than padded strings.
- Delivery telemetry is not guaranteed on the main human stream while output mode is CHAT and BLE telemetry 0004 is optional; the adapter now forces `BOTH` before measurement.
- Chatter `/id` identity is derived from eFuse MAC while reliable delivery `user=session/seq` uses a random boot protocol session ID. The adapter therefore binds a sample to the first new local `WAIT_ACK` after sample start and correlates later ACK/FAILED by that exact delivery ID; it does not compare delivery IDs to `/id`.

Final automated source checkpoint before this status update:

```text
dev@d868d026c05dac9373a47c0935673836432f9073
GitHub Actions: 36286979122 SUCCESS
compile: PASS
ruff: PASS
complexity: PASS
pytest: 209 passed
```

Final BASE..HEAD source review used design checkpoint:

```text
base: 5996a7eaa0275784cccc860199c1a69c0b8ef666
head: d868d026c05dac9373a47c0935673836432f9073
```

Review result:

- all pre-existing source deletions were inspected;
- no pre-existing function definition disappeared;
- `agent.py` deletions are replacements of old mutation/shutdown/async bodies by ownership-aware equivalents;
- generic `agent.py` and `sweep.py` contain no concrete Chatter/reliable-user semantics or adapter-name branch;
- controller-specific behavior remains under the Chatter profile adapter;
- no hardware execution was performed.

## Result

Implemented: YES — source + documented machine API

Automated validation: PASS — GitHub Actions `36286979122`, 209 tests

Hardware validation: NOT RUN / not required by this TODO's source closure gate

Status: CLOSED
