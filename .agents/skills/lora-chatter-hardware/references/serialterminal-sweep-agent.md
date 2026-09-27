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

The maintained source/API implementation was accepted at:

```text
dreamworkerln/serialterminal/dev@d868d026c05dac9373a47c0935673836432f9073
```

Later source-branch commits may move documentation/handoff state. During a hardware
task do not inspect SerialTerminal source merely to rediscover this API. If the runtime
returns a structured API error that contradicts this reference, stop at that
source/runtime boundary and report it.

## Current semantic boundary

The current sweep is a **host-side SerialTerminal job**, not a firmware-wide exclusive
radio mode.

It provides:

- one active sweep per SerialTerminal agent process;
- mutation ownership of the declared SerialTerminal sessions;
- deterministic ordered coordinates;
- exact caller-specified repetitions;
- a profile-owned `chatter.reliable_user` adapter;
- bounded sweep-event history and progress;
- cancellation and terminal job state;
- mechanical `[SWEEP]` records in the normal forensic log.

It does **not** currently prove that a Chatter node has entered a firmware mode in
which all non-sweep LoRa RX/TX is disabled. In particular, physical RF activity from
unrelated nodes/processes/devices remains outside the SerialTerminal session lease.

Therefore, until a later firmware/source task explicitly implements an exclusive
firmware sweep mode:

```text
SerialTerminal sweep ownership
    !=
exclusive RF-environment ownership
```

Keep all non-participating transmitters quiet. Incoming unrelated USER/ACK/heartbeat
traffic can contaminate a physical measurement and must not be silently treated as
part of the sweep.

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

A successful sweep lease blocks **new** external `send_line`, `send_bytes` and
`close` mutations on participating sessions. It does not retroactively cancel an
ordinary TX that was accepted before the lease and is still queued/in flight.

Therefore the executor must not enter a sweep with unresolved ordinary session
mutation.

Safe operational rule:

1. do not pre-submit USER traffic or a batch of future control commands before
   `sweep_start`;
2. if an ordinary pre-sweep control command was necessary, wait for its explicit node
   response proving that command was processed;
3. require the relevant setup state to be confirmed before starting the sweep;
4. do not issue another ordinary `send_line`/`send_bytes` between the final
   confirmed setup observation and `sweep_start`;
5. if a pre-sweep TX has `tx_state:"unknown"`, or its side effect is otherwise
   ambiguous, do not start measured sweep traffic from that session state. Establish a
   fresh known state according to the task/evidence rules.

Do not treat `queued_tx == 0` alone as proof that an ambiguous transport write had no
side effect.

The bundled Chatter sweep adapter performs its own preparation after ownership,
including reliable-work cancellation and measurement-state setup. Do not duplicate
those commands immediately before `sweep_start` merely out of habit.

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
- settles prior reliable USER work;
- disables diagnostic/heartbeat/echo-loop activity;
- makes delivery telemetry visible;
- verifies distinct node identities;
- applies and verifies frequency/power/BW/SF;
- sends one reliable USER sample at a time;
- waits for operational terminal ACK/FAILED settlement before the next sample/config
  transition;
- uses finite phase deadlines;
- performs bounded cleanup.

It uses delivery telemetry for synchronization only. RF-quality interpretation still
belongs to the hardware measurement/reporting rules.

## Cancellation

Do not send ordinary firmware `/cancel` or `/cancel all` from outside while the
sweep owns the sessions; those external `send_line` calls are expected to be rejected
as `session_busy`.

Cancel the host-side job with:

```json
{"id":102,"op":"sweep_cancel","sweep_id":"sw1"}
```

The immediate response normally means:

```text
state = cancelling
```

That is only acknowledgement of the cancel request.

The Chatter adapter cooperatively settles/cancels the active reliable transaction and
its cleanup path issues the controller cancellation needed to leave reliable USER work
settled. Continue `sweep_observe` until terminal:

```text
cancelled
OR
failed
```

Only after the terminal transition is session mutation ownership released.

Current host-side semantics do **not** mean that an arbitrary incoming RF frame is
disabled during cancellation or during the sweep. That stronger behavior requires a
separate firmware/source design.

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

## Current isolation limitation

The desired stronger architecture for a future source/firmware task may be:

```text
enter firmware sweep mode
-> only explicitly designated sweep RF traffic is serviced
-> ordinary USER / heartbeat / unrelated ACK obligations cannot interfere
-> /cancel or /cancel all exits sweep mode
-> return to normal radio operation
```

That is **not** the current maintained implementation described by this executor
reference.

The existing Chatter sweep uses ordinary reliable USER/ACK protocol traffic. A future
exclusive firmware sweep mode therefore needs an explicit way to distinguish sweep
traffic from unrelated ordinary traffic (for example a dedicated protocol marker,
session/token, or other source-defined mechanism). The hardware executor must not
invent that distinction.

Until such a source change is explicitly supplied and validated, enforce isolation at
the experiment/coordinator level and report any unrelated RF activity as contamination
or an evidence boundary.
