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

The host-only source/API implementation is validated at:

```text
dreamworkerln/serialterminal/dev@ed685dc15b4ee2232c9e01d2379ce094bd796c26
GitHub Actions 36327209517 SUCCESS
225 tests PASS
```

This workflow has no firmware `/sweep` prerequisite. The hardware executor must use
the deployed-firmware provenance supplied by the task/operator when physical
compatibility matters; it must not inspect firmware source during the hardware task.

Later source-branch commits may move documentation/handoff state. During a hardware
task do not inspect SerialTerminal source merely to rediscover this API. If the runtime
returns a structured API error that contradicts this reference, stop at that
source/runtime boundary and report it.

## Current semantic boundary

The maintained sweep is a **host-side SerialTerminal diagnostic job**.

A successful lease atomically owns the participating sessions and captures each
session's pre-existing accepted-TX fence. Adapter preparation does not begin until
every fenced TX has reached a known terminal transport outcome. An ambiguous
`tx_state:"unknown"` fails the job with `session_tx_unknown`; it is never silently
discarded as though the queue were clean.

After the fence, the Chatter adapter uses only existing commands to establish a quiet
diagnostic baseline:

```text
/cancel all
/diag off
/heartbeat off
/echo-loop stop
/echo        only when /help reports echo=ON
/both
```

While the job is active, external `send_line`, `send_bytes` and `close` on the
participating sessions are rejected by SerialTerminal ownership. The profile adapter
alone submits control/config commands and measured USER samples through its restricted
context.

No firmware command or RF frame flag named "sweep" is required. SerialTerminal also
does not own the physical RF environment: the operator/coordinator must choose a quiet
measurement frequency/environment and keep unrelated nodes quiet. Third-party RF is
contamination.

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

The maintained `chatter.reliable_user` adapter:

- requires exactly two distinct connected Chatter sessions;
- settles prior reliable USER work with `/cancel all`;
- disables diagnostic/heartbeat/echo-loop/manual-echo activity using existing commands;
- enables `BOTH` so delivery telemetry is visible;
- verifies distinct node identities;
- applies and verifies frequency/power/BW/SF;
- sends one reliable USER sample at a time;
- waits for operational terminal ACK/FAILED settlement before the next sample/config
  transition;
- uses cooperative finite phase deadlines;
- performs bounded cleanup with `/cancel all` on both sessions.

It uses ordinary USER/ACK wire frames and does not classify RF quality. No firmware
`/sweep` capability is required.

## Cancellation

Do not send ordinary `/cancel` or `/cancel all` through external `send_line` while
the sweep owns the sessions; those external mutations are expected to be rejected as
`session_busy`.

Cancel the host-side job with:

```json
{"id":102,"op":"sweep_cancel","sweep_id":"sw1"}
```

The immediate response normally reports `state:"cancelling"`; this is only
acknowledgement of the request.

For an active Chatter sample, the adapter sends `/cancel all` itself and switches to a
separate short cancellation-settlement budget rather than waiting through the full
slow-PHY sample deadline.

Continue `sweep_observe` until terminal `cancelled` or `failed`. Cleanup also sends
`/cancel all` to every participating session before waiting for settlement evidence.
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

The implemented boundary is:

```text
host session ownership + pre-sweep TX fence
-> existing Chatter controls establish a quiet local baseline
-> profile adapter alone submits measured USER/config work through owned sessions
-> ordinary USER/ACK wire protocol remains unchanged
-> operator keeps the measurement frequency/environment quiet
-> bounded /cancel all cleanup
-> terminal job releases ordinary SerialTerminal control
```

Do **not** claim protocol-level RF isolation. Unrelated third-node RF on the same
frequency is contamination/evidence to preserve.


