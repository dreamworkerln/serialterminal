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

Sweep execution events use a monotonically increasing job-local sequence.

Request cursor semantics are strictly:

```text
cursor = last event sequence already consumed by this client
return events with seq > cursor
```

The cursor belongs to the reader. Reading or not reading events must not control or throttle sweep execution.

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
    "oldest_cursor": 947,
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

The caller observes the terminal transition through `sweep_observe`.

### `sweep_close`

Completed/failed/cancelled jobs must have an explicit bounded lifecycle so a long-lived agent process does not retain job state forever.

Prefer an explicit close/release operation analogous to session `close`.

`sweep_close`:

- succeeds only for terminal jobs;
- releases retained sweep events/result/progress state;
- makes later operations on that `sweep_id` return `unknown_sweep`;
- must not delete or alter SerialTerminal log files.

Do not auto-destroy a job merely because one reader observed its terminal event; reads may be retried and callers may need to drain retained windows.

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

- two already/openable target sessions/nodes;
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

- [ ] inspect current agent async request/observe architecture and reuse its request/response conventions;
- [ ] inspect `scripts/run-chatter-scenario` only for reusable orchestration mechanics, not as the sweep abstraction;
- [ ] define generic sweep plan/job/event data model;
- [ ] define measurement-adapter interface;
- [ ] implement generic sweep engine independent of Chatter semantics;
- [ ] add agent API dispatch/validation for `sweep_start`;
- [ ] implement bounded per-job event history with monotonic cursor;
- [ ] implement `sweep_observe` long-poll with requested `window`, advertised `max_window`, `head_cursor`, timeout and progress snapshot;
- [ ] implement explicit expired-cursor error without silent event loss;
- [ ] preserve one-request/one-response and no-unsolicited-JSON rules;
- [ ] keep unrelated agent requests serviceable while `sweep_observe` waits;
- [ ] implement `sweep_cancel` request/terminal-state separation;
- [ ] implement explicit terminal-job `sweep_close` resource release;
- [ ] implement exact fixed repetition semantics;
- [ ] implement first Chatter reliable-USER measurement adapter without leaking its semantics into the generic engine;
- [ ] verify adapter applies and verifies requested coordinates before sampling;
- [ ] ensure sequential sample boundary for the first adapter;
- [ ] ensure existing forensic and console logs remain owned by normal SerialTerminal logging;
- [ ] update `AGENT_API.md` with final exact schema and semantics;
- [ ] update architecture docs if the new sweep/adapter dependency boundary requires it.

## Validation

Generic API/engine tests:

- [ ] `sweep_start` returns promptly with unique sweep id;
- [ ] advertised `max_window` and retention are stable and enforced;
- [ ] `repetitions=3` executes exactly 3 samples per requested coordinate;
- [ ] `repetitions=10` executes exactly 10 samples per requested coordinate;
- [ ] no runtime condition changes the requested repetition count;
- [ ] traversal follows the declared ordered axes deterministically;
- [ ] progress totals and current coordinate/repetition are mechanically correct;
- [ ] requested window larger than `max_window` returns only `max_window` events;
- [ ] `response.cursor` is the last returned event sequence;
- [ ] `head_cursor` reports producer head independently of reader position;
- [ ] caller can drain backlog over multiple windows without a `more` flag;
- [ ] long-poll wakes on new event;
- [ ] long-poll wakes on terminal transition;
- [ ] long-poll returns `timed_out:true` when no wake condition occurs;
- [ ] unrelated agent request can complete while `sweep_observe` is pending;
- [ ] expired cursor returns explicit structured error;
- [ ] job execution failure is returned as terminal job state with `ok:true` observe response;
- [ ] malformed/unknown sweep request is returned as API `ok:false`;
- [ ] cancellation first returns/enters cancelling and later reaches terminal cancelled;
- [ ] `sweep_close` rejects non-terminal jobs and releases terminal jobs;
- [ ] closed sweep ids become unknown and retained memory is released;
- [ ] no unsolicited JSON is emitted.

Adapter boundary tests:

- [ ] generic engine tests contain no Chatter command/parser knowledge;
- [ ] Chatter adapter applies/verifies requested sweep coordinates;
- [ ] adapter never waits for a response to a command it has not actually issued;
- [ ] first adapter does not pre-submit the next sample before the previous sample reaches its operational settle boundary;
- [ ] protocol content used only for operational synchronization does not become generic point analytics;
- [ ] existing `scripts/run-chatter-scenario` behavior remains passing if any reusable mechanics are extracted.

Repository gates:

- [ ] relevant targeted tests PASS;
- [ ] full repository validation required by `AGENTS.md` PASS;
- [ ] final BASE..HEAD diff reviewed, especially deletions/refactors;
- [ ] GitHub Actions for the resulting implementation checkpoint PASS.

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
- Final plan/adapter JSON schema is not yet implemented and may be refined while preserving the abstraction and API semantics in this TODO.
- Job event history is operational progress, not a replacement for forensic logs.
- This TODO does not define cross-process persistence/resume of a sweep job after the agent process exits.
- This TODO does not define adaptive experiment orchestration above the sweeper.

## Result

Implemented: not yet

Validated: not yet

Status: OPEN
