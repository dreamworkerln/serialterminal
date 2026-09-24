---
name: lora-chatter-hardware
description: Lightweight operating skill for physical LoRa-Chatter execution through the sibling SerialTerminal runtime, with progressive disclosure for evidence, provenance, reliability and diagnostics.
---

# LoRa-Chatter hardware executor

Use this skill only for physical-node execution from the serialterminal-observations workspace.

The runtime/source repository is the read-only sibling:

```text
../serialterminal
```

Firmware source/docs are outside this executor's evidence boundary. During a hardware task, do **not** inspect, search, open or locate any firmware source checkout, including `dreamworkerln/lora-sack-protocol`, even read-only.

Use firmware implementation facts only when they are already present in this maintained skill/references, explicitly supplied by the operator/source-development task, or directly observable from the physical node. If a required implementation fact is missing, report the missing fact/evidence boundary and stop or return `INCONCLUSIVE` as appropriate. Do not resolve sibling Git repositories, search the filesystem, infer usernames or consult firmware source/docs.

Do not modify source, tests, docs, TODOs, CI, branches, this skill, repository policies or REVIEW_STATE.md. Do not flash unless explicitly authorized.

## Sandbox / permission elevation

A sandbox/access-control failure is an environment boundary to recover from, not an immediate hardware, transport, Git or test outcome.

When an operation that is both necessary for the task and already allowed by this skill fails with an access error such as `Operation not permitted`, `Permission denied`, `EACCES`, `EPERM`, a read-only sandbox path, inability to create a Git `*.lock`, blocked Bluetooth/D-Bus/device access, or blocked network access:

1. identify the smallest concrete operation or command class that needs additional access;
2. request elevated permission for that operation through the execution environment;
3. retry the same operation after approval instead of immediately returning `BLOCKED`;
4. preserve the existing long-lived SerialTerminal process/session state when the environment permits it; if the permission boundary necessarily requires a fresh process, record that executor fact and establish a fresh run identity when evidence continuity requires it;
5. classify the step as `BLOCKED` only when elevation is unavailable, explicitly denied, or the approved retry still cannot perform the required operation.

Different operation types may require separate approvals. A successful or failed approval for BLE discovery does not replace a later required approval for a guarded Git helper, Git metadata lock, remote verification, serial-device access, or another independently sandboxed operation. Request the minimum permission for each required class as it is encountered.

When the execution environment supports a persistent command-prefix approval, do not request an "always allow" rule that includes run-unique arguments such as `--log /tmp/<timestamp>.log`. For the SerialTerminal agent, the reusable approval prefix is exactly:

```text
python3 ../serialterminal/serialterminal.py agent
```

The unique `--log ...` argument belongs to the invocation, not to the persistent approval identity. If the environment cannot express a prefix rule separately and offers only approval for the exact full command, request/run it as a one-time approval rather than presenting that timestamp-specific command as a useful persistent rule.

For Git/publication work, elevate the guarded publication helper or the exact required Git/read-only remote-verification command. Do not use elevated access to bypass the guarded publication workflow with raw `git add/commit/push`.

Privilege elevation never expands task scope. It does not authorize firmware source/docs inspection, source modification, flashing, host Bluetooth stack mutation, destructive Git operations, or any action otherwise forbidden by this skill.

## Task classes

Choose the lightest class that satisfies the operator request.

### QUICK

Examples: RSSI/SNR probe, calibration, discovery check, short local command check.

For QUICK:

- do not create RUN/OBS unless explicitly requested;
- do not read NODE_OBSERVATION_RECORDING_POLICY.md;
- do not pre-emptively read or search ../serialterminal/AGENT_API.md, README.md, scripts/, helper source or unrelated repository files;
- do not use rg/grep/repository exploration merely to rediscover normal happy-path operation syntax already stated in this skill;
- read ../serialterminal/AGENT_API.md only after an actual structured API error or when the requested operation/semantic is not covered by this skill;
- do not load provenance/reliability/diagnostic references unless the task actually depends on them;
- use the normal safety/identity rules below;
- return only the requested compact result.

### CANONICAL_RUN

For durable validation/evidence, keep bootstrap compact:

- do **not** read `NODE_OBSERVATION_RECORDING_POLICY.md` at startup on the normal happy path; the publication contract below is sufficient for an ordinary canonical RUN;
- read a targeted policy section only when the task has an evidence/layout ambiguity or the guarded helper reports a policy/publication error; do not dump the whole policy into model context;
- read only the task-specific reference actually needed below;
- when exact deployed firmware identity is needed, prefer the node's `/version` result; if it reports a clean source SHA plus valid image metadata, do not read `references/provenance.md` merely to restate that result;
- read `references/provenance.md` only for provenance ambiguity, source/image mismatch, unknown/dirty state, or an acceptance gate that requires deeper provenance reasoning;
- read `NODE_RUN_AUXILIARY_ARTIFACTS.md` only when the task explicitly requests an auxiliary diagnostic capture.

Normal canonical publication contract after the hardware evidence is finalized:

1. create exactly one unique `runs/RUN_<UTC>_<topic>/`;
2. copy the exact finalized forensic `serialterminal.log` and companion `serialterminal.console.log`;
3. write `REPORT.md`; create a matching OBS only for a reusable/material finding;
4. write `MANIFEST.json` last;
5. validate only the intended RUN/OBS files and JSON/diff hygiene;
6. publish only with `python3 -I ../serialterminal/scripts/commit-node-run`;
7. independently verify `git ls-remote origin refs/heads/node_observations` matches the helper commit.

Do not read helper source, full policy text, or repository history when this happy path succeeds.

### DIAGNOSTIC

Load only the relevant diagnostic/reference file. Do not automatically expand into a canonical RUN unless the task requests durable evidence or the result must be published.

## Normal SerialTerminal happy path

Use one long-lived **interactive** process for one hardware interaction. The `agent`
subcommand is a JSONL stdin/stdout protocol and must keep stdin open for the whole
hardware task.

Launch it only through a terminal/session API that allocates a persistent PTY or
equivalent interactive process handle and lets later tool calls write additional
JSONL requests to the same stdin:

```bash
python3 ../serialterminal/serialterminal.py agent --log /tmp/<unique-log-name>.log
```

A one-shot command execution without a persistent stdin/PTY is **not** a valid
SerialTerminal agent launch. If stdin closes immediately, the process may log
`ready` and then `stop` before discovery. Treat that as a bootstrap/executor
error, not as hardware evidence.

Before sending `discover`, verify that the interactive process is still alive and
that its stdin remains writable. Do not proceed merely because the forensic log
contains an `AGENT ready` line.

The log path is unique for every run/probe. Never reuse a fixed forensic /tmp filename.

Immediately before launching SerialTerminal, obtain the real current UTC timestamp with a separate command:

```bash
date -u +%Y%m%dT%H%M%SZ
```

Use the exact returned value in the basename. The timestamp is run identity, not decoration:

- do not invent, round, normalize or approximate it;
- do not use placeholder-looking values such as `T000000Z` unless that is literally what the preceding `date -u` command returned;
- do not reuse a timestamp copied from an example, prompt, previous run or earlier terminal output;
- before launch, verify that neither the chosen `.log` nor its companion `.console.log` already exists; on collision, obtain a fresh timestamp/name rather than overwriting or appending to old evidence.

The SerialTerminal launch command must remain a direct argv-style command so host approval rules can match it reliably.

Do not use shell wrappers or shell expansion in the launch command:

```text
forbidden:
    bash -lc "python3 ..."
    sh -c "python3 ..."
    $(date ...)
    \`date ...\`
```

After the standalone timestamp command, construct the log filename as a literal string and pass that literal path to `--log`. Example shape only:

```text
date -u +%Y%m%dT%H%M%SZ
    -> 20260923T142137Z

python3 ../serialterminal/serialterminal.py agent --log /tmp/chatter-probe-20260923T142137Z.log
```

The stable executable prefix is:

```text
python3 ../serialterminal/serialterminal.py agent
```

Do not vary that prefix merely to generate a unique logfile name.

### Interaction efficiency

Minimize model/terminal round-trips without overflowing a node's bounded input queue or hiding evidence:

- do not treat SerialTerminal's ability to submit many `send_line` requests in one host interaction as permission to burst an arbitrary number of local commands at one node;
- for routine bootstrap, configuration and cleanup, send at most **3 local-control commands per session** before an `observe` checkpoint confirms that the batch was consumed; this conservative bound applies even when the currently tested firmware is known to have a deeper input queue;
- independent commands for different sessions may share one host interaction, but the per-session batch limit still applies;
- after each local-control batch, consume the resulting lines/cursors and confirm the intended state before sending the next batch;
- send state transitions whose result controls the next step individually or in the smallest independent batch, then confirm them before proceeding. This includes `/heartbeat on|off`, `/diag on|off`, and PHY/config changes immediately before a measured phase;
- never rely on queue depth as normal flow control. `INPUT QUEUE FULL`, a dropped local command, or a missing expected acknowledgement means the affected setup/cleanup state must be re-established and confirmed before measurement or exit;
- do not batch commands whose ordering depends on an earlier result;
- use returned cursors directly rather than re-querying status/history to rediscover position;
- do not re-read repository documentation between normal happy-path phases;
- keep terminal output consumed incrementally; do not intentionally replay the entire accumulated SerialTerminal stdout back into model context after the same responses were already processed;
- after the final `close` responses are consumed, perform only the control action required to end stdin/process ownership; do **not** issue a separate terminal wait, rerun, history read, transcript fetch or other follow-up whose purpose is merely to prove that the already-closed agent exited;
- never launch the same SerialTerminal agent command a second time to "finish", "collect", or "confirm" a completed hardware interaction; post-run facts come from the finalized logs, not from replaying process stdout;
- some terminal UIs emit a collapsed completion card for the original background command when it exits, for example `… +113 lines`. That automatic card is not evidence of a second SerialTerminal launch, but it is still repeated transcript presentation: leave it collapsed and do not expand, quote, search or otherwise re-ingest it;
- reporting must distinguish these cases accurately. Say `no explicit stdout/history replay was requested` only when true. If an automatic collapsed completion transcript appeared, state that fact; never claim simply `agent completed without replay`;
- inspect finalized `.log` / `.console.log` with targeted search/count/summary commands; do not read a large forensic log wholesale into model context unless a bounded forensic question requires it;
- use specialized helpers only when timing/correctness requires local orchestration, not merely to save a few model turns.

The skill is an operational contract, not a catalog of test cases. Do not create scenario-specific skills or instructions for ordinary ad-hoc hardware requests.


Normal JSONL sequence:

```text
discover
-> open
-> status/observe/send_line as needed
-> cleanup
-> close
-> terminate process ownership without a post-close stdout/history read
```

Minimal happy-path request schemas are part of this skill. Do not guess field names and do not search AGENT_API.md for these operations:

```json
{"id":1,"op":"discover","scope":"ble"}
{"id":2,"op":"open","device_key":"<returned device_key>","profile":"chatter"}
{"id":3,"op":"send_line","session":"s1","text":"/id"}
{"id":4,"op":"observe","cursors":{"s1":42,"s2":75},"timeout_ms":1000}
{"id":5,"op":"close","session":"s1"}
```

For `send_line`, the payload field is exactly `text`, never `line`.
For `open`, use the exact `device_key` returned by same-process discovery.
Save each successful `open` result's `latest_seq` as the initial cursor when startup traffic should be ignored.

Important:

- keep one SerialTerminal agent process for the whole hardware task; do not restart it between phases merely for convenience;
- that process must be the same persistent interactive/PTY-backed process launched above; every JSONL request is written to its still-open stdin, and responses are consumed from that same process;
- never use a plain one-shot exec invocation for `serialterminal.py agent` when the execution API will close stdin after launch;
- discovery cache is process-local; run discover in the same agent process before open;
- for Chatter sessions open returned device_key with profile "chatter";
- save latest_seq/cursors and advance using observe-returned cursors;
- default `observe` returns `lines`, `cursors` and `timed_out`; it intentionally omits raw `events`;
- `result.lines` is the normal logical firmware view and the default input for ordinary protocol reasoning;
- request raw events only for a bounded forensic need by adding `"include_events":true` to that specific `observe`;
- `result.events/data_b64` with `include_events:true` remains the machine-facing raw transport view; the finalized forensic `.log` preserves raw event truth independently of response projection;
- send_line queued or transport written is not peer delivery;
- tx_state unknown is ambiguous; do not blindly resend;
- forensic_gap means the affected evidence range is incomplete.

### Observe timeout policy

Treat `observe.timeout_ms` as the maximum wait for one long-poll, not as the scenario deadline. An observe request returns immediately when any watched session produces a new raw event.

Use the smallest timeout appropriate to the expected response:

```text
local command / QUICK probe:
    timeout_ms = 1000
    if timed_out with no relevant event, retry once
    after the second empty 1 s poll, stop or report the local no-response boundary

ordinary measured RF/protocol step:
    choose a timeout from the expected airtime/protocol window
    do not use 15/20/30 s merely as a generic safety margin

known long retry/exhaustion scenario:
    use the task/protocol deadline, not an arbitrary observe timeout
```

A 1 s timeout is not a universal protocol deadline. At slow LoRa PHY settings a valid RF outcome can legitimately take longer than 1 s.

After every observe response, continue from the returned cursors. The cursor is still a raw event cursor even when `events` are omitted. If raw activity arrives without completing a logical line, `lines` may be empty while the cursor advances; issue the next observe immediately with those returned cursors.

For exact chunk/event inspection only:

```json
{"id":6,"op":"observe","cursors":{"s1":42,"s2":75},"timeout_ms":1000,"include_events":true}
```

Do not enable `include_events` globally for an ordinary hardware scenario.

Avoid repeated empty 15-30 second waits. Conversely, do not create dozens of 1-second LLM reasoning turns for a known long wait; when a scenario requires tight/long deterministic polling, use an existing scenario helper or a task-specific local orchestration path.

Do not read the entire AGENT_API.md for the normal path. Read ../serialterminal/AGENT_API.md only when the task directly depends on API semantics not stated here or a structured API error cannot be handled from this skill.

If the agent process exits before the first `discover` response because stdin/PTY ownership was not preserved, do not classify the hardware as absent or failed. Do not publish RUN/OBS from that empty attempt unless the operator explicitly asks to preserve executor-failure evidence. Start a fresh run identity only after fixing the interactive launch mechanism.

If expected BLE targets are absent from discover, use the supported capability scanner/prober workflow before concluding absence. Do not treat an advertised name alone as NUS capability.

## Identity

Canonical node identity:

```text
LoRa-Chatter-XXXX
```

Establish identity through /id. Do not hard-code node IDs, MACs, device keys, USB paths, session IDs, RSSI/SNR/Q or topology into reusable skill/policy files.

Run-specific prompts may provide concrete endpoints. They remain run facts.

## BLE transport

Default Chatter transport is BLE unless the operator or scenario explicitly requires another transport. Do not silently fall back to USB.

If expected BLE targets are absent or BLE repeatedly disconnects/reconnects, use the focused rules in references/bluetooth.md and treat unresolved transport instability as an environment/evidence boundary rather than automatically labeling it firmware FAIL.

## RF safety gate

After establishing participating node identities and before the first measured LoRa RF transmission, establish the following state **without sending the whole block as one per-node burst**:

```text
/heartbeat off
/diag off          when supported
/echo-loop stop    when supported
/cancel all        when appropriate for reliable USER work
/power 2
/config
```

Use the bounded local-control batching rule above: small batches with `observe`/confirmation between them. A typical safe shape is stop/cancel controls first, confirm; then power/radio controls, confirm; then `/config` as the final state check.

Confirm power=2 dBm on every participating node before measured RF.

Local/controller commands such as /id, /version, stop commands, /power and /config are not themselves the measured LoRa RF phase.

If a stop command is not supported, establish capability from the task prompt, maintained hardware references or node `/help` before sending it; do not accidentally transmit an unknown command as USER payload. Do not consult firmware source/docs.

If power=2 cannot be applied/confirmed, do not start measured RF. Report the precondition boundary.

A task may later request a different TX power as part of a controlled scenario, but only after the 2 dBm baseline gate and any explicit operator authorization required by that scenario.

Do not remove an antenna/load or reconfigure an RF path while transmitting.

## Local controls

Common controls:

```text
/help
/id
/version
/power [N]
/freq [MHz]
/sf [N]
/bw [kHz]
/config
/heartbeat on|off
/diag on|off
/echo-loop ...
/cancel
/cancel all
/reboot
```

When command availability is uncertain, use the task prompt, maintained hardware references or `/help` before sending an uncertain token that could become USER traffic. Do not consult firmware source/docs.

## Task-specific references

Read only when needed:

```text
references/provenance.md
    exact physical firmware/source/image/build identity

references/reliable-user.md
    USER/ACK, retries, duplicates, queue, cancellation, lost-ACK gates

references/bluetooth.md
    BLE discovery, permissions and reconnect/flapping handling

references/diagnostic-and-faults.md
    ECHO, reboot, degraded/fatal radio semantics

references/evidence-recovery.md
    only after publication/helper/storage/Git failure
```

For protocol behavior beyond these operating summaries, use only explicit task facts, maintained hardware references and physical-node evidence. If those are insufficient, report the missing source-development fact; do not inspect firmware source/docs.

## Timing-sensitive scenarios

When correctness depends on reacting faster than an LLM/tool round-trip, prefer an existing repository helper in ../serialterminal/scripts/ when the task matches it.

A helper is orchestration, not independent evidence authority. It must still use SerialTerminal transport/session ownership and its result must be interpreted against the requested acceptance criteria.

Do not invent an ad-hoc helper merely for convenience unless the operator asks for it or the scenario cannot be executed correctly at model round-trip speed.

## Outcomes

Use:

```text
PASS
FAIL
BLOCKED
INCONCLUSIVE
```

Do not promote queued, written, local TxDone, a partial telemetry fragment or an assumption about fault injection into higher-level delivery PASS.

If expected behavior and actual evidence disagree, preserve the evidence and stop at the hardware boundary. Do not repair source.

## Safe final state

Unless the task says otherwise:

```text
heartbeat OFF
diagnostic mode OFF
echo/echo-loop OFF
reliable USER flow settled or explicitly cancelled
TX power restored to 2 dBm after temporary calibration/high-power work
test sessions closed
SerialTerminal process terminated
```

Apply cleanup controls with the same bounded per-session batching rule used for bootstrap; do not fire the entire cleanup sequence as one local-command burst. Confirm the final node state before closing the sessions.

If cancellation occurs after physical USER TX, delivery status may remain unknown; cancellation is not proof of non-delivery.
