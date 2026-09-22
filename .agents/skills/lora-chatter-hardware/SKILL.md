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

Firmware source/docs are also read-only during a hardware task.

Do not modify source, tests, docs, TODOs, CI, branches, this skill, repository policies or REVIEW_STATE.md. Do not flash unless explicitly authorized.

## Task classes

Choose the lightest class that satisfies the operator request.

### QUICK

Examples: RSSI/SNR probe, calibration, discovery check, short local command check.

For QUICK:

- do not create RUN/OBS unless explicitly requested;
- do not read NODE_OBSERVATION_RECORDING_POLICY.md;
- do not read the full ../serialterminal/AGENT_API.md;
- do not load provenance/reliability/diagnostic references unless the task actually depends on them;
- use the normal safety/identity rules below;
- return only the requested compact result.

### CANONICAL_RUN

For durable validation/evidence:

- read NODE_OBSERVATION_RECORDING_POLICY.md before artifact creation/publication;
- read only the task-specific reference needed below;
- read provenance.md only when exact physical firmware/source/image identity is required by the task or acceptance gate;
- read NODE_RUN_AUXILIARY_ARTIFACTS.md only when the task explicitly requests an auxiliary diagnostic capture.

### DIAGNOSTIC

Load only the relevant diagnostic/reference file. Do not automatically expand into a canonical RUN unless the task requests durable evidence or the result must be published.

## Normal SerialTerminal happy path

Use one long-lived process for one hardware interaction:

```bash
python3 ../serialterminal/serialterminal.py agent --log /tmp/<unique-log-name>.log
```

The log path is unique for every run/probe. Never reuse a fixed forensic /tmp filename.

Normal JSONL sequence:

```text
discover
-> open
-> status/observe/send_line as needed
-> cleanup
-> close
-> terminate the same agent process
```

Important:

- discovery cache is process-local; run discover in the same agent process before open;
- for Chatter sessions open returned device_key with profile "chatter";
- save latest_seq/cursors and advance using observe-returned cursors;
- result.lines is the normal logical firmware view;
- result.events/data_b64 is forensic transport evidence;
- send_line queued or transport written is not peer delivery;
- tx_state unknown is ambiguous; do not blindly resend;
- forensic_gap means the affected evidence range is incomplete.

Do not read the entire AGENT_API.md for the normal path. Read ../serialterminal/AGENT_API.md only when the task directly depends on API semantics not stated here or a structured API error cannot be handled from this skill.

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

No host Bluetooth-audio/headset preflight is part of the normal hardware contract.

If expected BLE targets are absent or BLE repeatedly disconnects/reconnects, use the focused rules in references/bluetooth.md and treat unresolved transport instability as an environment/evidence boundary rather than automatically labeling it firmware FAIL.

## RF safety gate

After establishing participating node identities and before the first measured LoRa RF transmission:

```text
/heartbeat off
/diag off          when supported
/echo-loop stop    when supported
/cancel all        when appropriate for reliable USER work
/power 2
/config
```

Confirm power=2 dBm on every participating node before measured RF.

Local/controller commands such as /id, /version, stop commands, /power and /config are not themselves the measured LoRa RF phase.

If a stop command is not supported, establish capability from the task-specific firmware contract before sending it; do not accidentally transmit an unknown command as USER payload.

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

When command availability is uncertain, use the task-specific firmware docs or /help before sending an uncertain token that could become USER traffic.

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

For authoritative protocol behavior beyond these operating summaries, read the task-specific current lora-sack-protocol source/docs. Do not read unrelated firmware documents.

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

If cancellation occurs after physical USER TX, delivery status may remain unknown; cancellation is not proof of non-delivery.
