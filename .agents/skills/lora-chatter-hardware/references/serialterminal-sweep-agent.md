# SerialTerminal generic sweep agent workflow

Read this only when a physical-node task uses the maintained SerialTerminal generic
sweep job API:

```text
sweep_start
sweep_observe
sweep_cancel
sweep_close
```

This reference is an executor guide for the existing host-side sweep facility. It does
not redefine the RF/protocol acceptance rules in `phy-payload-sweep.md` or the
campaign policy in `radio-characterization-program.md`.

The corrected source/API implementation is validated at:

```text
dreamworkerln/serialterminal/dev@bce891f74a435307303333911cff2107a7317899
GitHub Actions 36315186620 SUCCESS
224 tests PASS
```

The validated Chatter firmware checkpoint implementing the required local
`/sweep on|off` mode is:

```text
dreamworkerln/lora-sack-protocol/dev_chat_ack@020ebe39288681cc58b8a5109717f6b55fbf675c
Chatter CI 36315420318 SUCCESS
```

A later firmware/source checkpoint may also be compatible, but the hardware executor
must establish deployed support from maintained task/provenance facts or physical-node
evidence; it must not inspect firmware source during the hardware task.

Later source-branch commits may move documentation/handoff state. During a hardware
task do not inspect SerialTerminal source merely to rediscover this API. If the runtime
returns a structured API error that contradicts this reference, stop at that
source/runtime boundary and report it.

## Current semantic boundary

The maintained sweep has **two coordinated layers**:

```text
SerialTerminal host sweep job
    mutation ownership + pre-sweep TX fence + deterministic plan

Chatter local firmware sweep mode
    /sweep on -> local RF isolation for the participating node
    /sweep off or cancellation -> normal local mode
```

A successful host lease now captures every participating session's pre-existing TX
fence. Adapter preparation does not begin until every externally accepted TX through
that fence has reached a known terminal transport outcome. An ambiguous
`tx_state:"unknown"` fails the job with `session_tx_unknown`; it is never silently
discarded as though the queue were clean.

The Chatter adapter then enters `/sweep on` on both nodes. That local firmware mode:

- clears/settles ordinary reliable USER backlog at entry;
- blocks ordinary local USER from non-owner input sources;
- disables heartbeat, diagnostic heartbeat, echo-loop and manual echo generation;
- suppresses other unrelated self-generated local RF;
- permits the sweep owner to submit the serialized measured USER/config work;
- exits on normal `/sweep off` cleanup or controller cancellation.

This is **local node isolation**, not global RF ownership. Measured packets still use
the normal USER/ACK wire protocol with no sweep flag/token. A third node on the same
frequency cannot be distinguished as "ordinary" versus "sweep" by frame semantics.
The operator/coordinator must therefore choose a quiet measurement frequency/environment;
unrelated third-party RF is contamination.

## Required companion references

For an SF/BW/payload measurement run, read this reference together with:

```text
references/phy-payload-sweep.md
```

For a multi-stage characterization campaign, also read:

```text
references/radio-characterization-program.md
```

The generic sweep job only executes the requested plan. It does not classify
CRC/HDR/retry/ACK quality and does not automatically extend 3 repetitions to 10.

## Process and session bootstrap

Use one long-lived interactive SerialTerminal agent process exactly as defined by the
main hardware skill.

Normal bootstrap:

```text
discover
-> open node A with profile "chatter"
-> open node B with profile "chatter"
-> sweep_start
```

Both participating sessions must already be connected and must use
`profile:"chatter"`.

Save the returned session IDs. Direction values in the sweep plan use those exact IDs,
for example:

```text
s1>s2
s2>s1
```

Do not launch a second SerialTerminal agent to run the sweep.

## Pre-start mutation fence

The pre-sweep host TX race is enforced by SerialTerminal itself.

At atomic sweep ownership acquisition, each participating `ManagedSession` records the
last externally accepted TX. Before the Chatter adapter can run `prepare`, the job
waits until all such pre-lease TX have known terminal transport outcome.

Executor implications:

1. do not deliberately pre-submit future USER/control batches before `sweep_start`;
2. do not treat `queued` or queue depth as delivery/side-effect proof;
3. `session_fence_timeout` means the pre-sweep ownership boundary did not settle;
4. `session_tx_unknown` means an accepted pre-sweep write has ambiguous side effects;
   do not retry it blindly or start measurement from that session state;
5. for `session_tx_unknown`, close/reopen/re-establish the session according to the
   task evidence policy before a new sweep attempt.

The executor must not manually purge arbitrary SerialTerminal TX queue entries as a
workaround. The fence exists specifically to avoid silent loss of already accepted
control operations.

## Plan schema

Generic plan shape:

```json
{
  "constants": {},
  "axes": [
    {"name":"axis_name","values":[1,2,3]}
  ],
  "repetitions": 3,
  "options": {}
}
```

For `chatter.reliable_user`, the complete coordinate must contain:

```text
frequency_hz
power_dbm
bandwidth_hz
sf
payload_bytes
direction
```

Current accepted Chatter values:

```text
frequency_hz   470000000..510000000, 1 kHz steps
power_dbm      2..17 or 20
bandwidth_hz   7800, 10400, 15600, 20800, 31250, 41700,
               62500, 125000, 250000, 500000
sf             7..12
payload_bytes  1..200
direction      "sA>sB" or "sB>sA" for the two declared sessions
options        {}
```

Use constants for values fixed across the run and ordered axes for the requested
matrix. Axis order defines deterministic traversal order.

Example:

```json
{
  "id":100,
  "op":"sweep_start",
  "adapter":"chatter.reliable_user",
  "sessions":["s1","s2"],
  "plan":{
    "constants":{
      "frequency_hz":470000000,
      "power_dbm":2,
      "bandwidth_hz":500000
    },
    "axes":[
      {"name":"sf","values":[7,8]},
      {"name":"payload_bytes","values":[8,32]},
      {"name":"direction","values":["s1>s2","s2>s1"]}
    ],
    "repetitions":3
  }
}
```

A successful start returns promptly with a `sweep_id`; it is not measurement PASS.

Record at least:

```text
sweep_id
initial events.cursor
events.max_window
events.retention
total_samples
```

## Progress with sweep_observe

Use the sweep-local cursor. It is separate from ordinary session `observe.cursors`.

Example:

```json
{
  "id":101,
  "op":"sweep_observe",
  "sweep_id":"sw1",
  "cursor":0,
  "window":100,
  "timeout_ms":30000
}
```

Cursor rule:

```text
request cursor = last sweep event already consumed
return events where seq > cursor
response.cursor = last event returned
head_cursor = current producer head
```

If:

```text
response.cursor < head_cursor
```

retained backlog remains. Drain it with the returned cursor.

A terminal job is determined from `state`, not merely from seeing a terminal event.

Job execution failure is returned as a successful API observation with:

```text
ok=true
result.state=failed
result.failure=...
```

An API/request error instead uses top-level `ok=false`.

Do not interpret sweep progress events as RF-quality results. They are mechanical
execution events only.

## Session ownership while active

While a sweep is `running` or `cancelling`, ordinary external mutations on its
participating sessions are expected to fail with `session_busy`, including:

```text
send_line
send_bytes
close
```

Do not fight this by retrying those commands.

Read-only operations may remain available, but avoid unnecessary parallel ordinary
`observe` traffic during a canonical sweep. The normal evidence path is:

```text
sweep_observe
+ finalized forensic log
```

Non-participating sessions are not blocked by the generic lease. The hardware executor
must still keep them physically quiet when they could affect RF evidence.

## Chatter adapter behavior

The maintained `chatter.reliable_user` adapter currently:

- requires exactly two distinct connected Chatter sessions;
- requires deployed Chatter firmware with the maintained local `/sweep on|off` mode;
- enters `/sweep on` only after the generic pre-sweep TX fence has settled;
- relies on that firmware transition to clear ordinary reliable USER work and suppress
  local heartbeat/diagnostic/echo background RF;
- makes delivery telemetry visible;
- verifies distinct node identities;
- applies and verifies frequency/power/BW/SF;
- sends one reliable USER sample at a time;
- waits for operational terminal ACK/FAILED settlement before the next sample/config
  transition;
- uses cooperative finite phase deadlines;
- performs bounded cleanup with `/sweep off`.

It uses ordinary USER/ACK wire frames. The adapter does not create a protocol-level
sweep identity and does not classify RF quality.

Before a canonical physical sweep, deployed firmware compatibility must be known. If
the task did not provide compatible provenance and node output cannot establish the
`/sweep` capability without ambiguity, report that precondition boundary rather than
silently falling back to a hand-written low-level USER loop.

## Cancellation

Do not send ordinary firmware `/cancel` or `/cancel all` through external
`send_line` while the sweep owns the sessions; those external mutations are expected
to be rejected as `session_busy`.

Cancel the host-side job with:

```json
{"id":102,"op":"sweep_cancel","sweep_id":"sw1"}
```

The immediate response normally reports `state:"cancelling"`; this is only
acknowledgement of the request.

For an active Chatter sample, the adapter sends controller `/cancel all`. Current
firmware defines `/cancel` and `/cancel all` during local sweep mode as also exiting
that mode. The adapter uses a separate short cancellation-settlement budget rather than
waiting through the original potentially long slow-PHY sample budget.

Continue `sweep_observe` until terminal:

```text
cancelled
OR
failed
```

Normal final cleanup sends idempotent `/sweep off`; if cancellation already exited
local mode, `[SYS] SWEEP already OFF` is acceptable.

Only after terminal transition is SerialTerminal session mutation ownership released.
Cancellation after a physical USER TX still does not prove that USER was not received.

## Closing retained job state

After a terminal state has been observed and no more sweep progress history is needed:

```json
{"id":103,"op":"sweep_close","sweep_id":"sw1"}
```

`sweep_close` releases retained in-memory sweep metadata/events. It does not delete
forensic log records.

Then perform normal node/session cleanup required by the task and close sessions.

## Repetition and anomaly follow-up

The generic engine executes **exactly** the requested `repetitions`. It performs no
adaptive anomaly extension.

For a normal 3-repetition characterization point:

```text
repetitions = 3
```

After that job is terminal, analyze only the evidence needed by
`phy-payload-sweep.md`.

If that reference requires extending an anomalous point from 3 total samples to 10
total samples per direction, schedule a separate focused sweep for the remaining
required repetitions while preserving the first samples as evidence. Do not pretend
the first sweep dynamically changed its plan.

If a new job is used for extension, record clearly which samples came from the initial
job and which came from the extension job.

## Forensic evidence

The normal SerialTerminal forensic log remains authoritative.

Sweep mechanics appear as:

```text
[SWEEP]
```

with the same job-local event sequence exposed through `sweep_observe`.

Use targeted finalized-log inspection for:

```text
ACK/retry/failure
CRC/HDR
RSSI/SNR
transport ambiguity
forensic_gap
exact ordering around an anomaly
```

Do not ingest the whole forensic log into model context for a normal PASS.

A `sweep_completed` mechanical state proves that the requested execution loop
completed; it does not prove that every RF sample was CLEAN.

## Structured-error handling

Examples that require stopping/reasoning rather than blind retry:

```text
unknown_operation
unknown_sweep_adapter
invalid_sweep_plan
session_busy
session_not_connected
sweep_busy
sweep_cursor_expired
invalid_sweep_cursor
adapter_failed / cleanup_timeout in terminal job failure
```

If `sweep_start` itself is unknown at runtime, treat that as a SerialTerminal
runtime/source mismatch. Do not silently replace a requested maintained sweep with a
large hand-written `send_line` loop.

## Current isolation boundary

The implemented boundary is now:

```text
host session ownership + pre-sweep TX fence
-> firmware local /sweep on mode on both participating nodes
-> only owner-driven local measured USER/config work is generated
-> ordinary USER/ACK wire protocol remains unchanged
-> operator keeps the measurement frequency/environment quiet
-> /sweep off or cancellation returns normal local operation
```

Do **not** claim stronger protocol-level RF isolation. There is no sweep frame
flag/session/token in this version. Incoming ordinary USER/ACK on the same frequency
cannot be identified as third-party versus intended sweep traffic by wire semantics.

Therefore any unrelated third-node RF observed in the measurement environment is
contamination/evidence to preserve. Do not invent protocol classification or attempt to
repair it inside the hardware run.


