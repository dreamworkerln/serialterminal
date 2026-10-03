# FT1 local-controller reset recovery TODO

TODO-ID: TODO_032
Status: OPEN

## Purpose

Close the physical gap where an active FT1 sender can remain stuck after its local
Chatter firmware hits a fatal radio error, reboots, and reconnects/returns READY.

The broader reconnect/repair architecture already exists in TODO_029, and current
host-side unit tests explicitly model controller reboot. A real 2026-10-03 run showed
that the physical path can still leave the transfer non-terminal instead of recovering
or failing cleanly. This TODO owns that concrete gap.

The rare firmware trigger (`RX_RESTART after TX (-16)`) is **not** required to validate
this host-side task: Chatter `/reboot` provides a deterministic controller-reset
injection for repeatable SerialTerminal tests.

## Current finding

Observed sender behavior during a file transfer:

```text
[SYS] CHATTER NODE LoRa-Chatter-1B44
[SYS] RADIO FATAL RX_RESTART after TX (-16), rebooting
[disconnected: ble:LoRa-Chatter-1B44 ...]
[waiting for selected device...]
[connected: ble:LoRa-Chatter-1B44 ...]
```

The node reconnects, but the active file transfer can remain stuck instead of reaching
one of:

```text
continued transfer
completed
failed
cancelled
```

This is a host-side correctness defect even if the underlying radio failure is rare.
An active transfer must never remain indefinitely non-terminal solely because the local
controller rebooted.

Physical finding provenance:

```text
Date: 2026-10-03
SerialTerminal branch examined: dev_tui@222b951bac2a3a0919c9dd07348ca98f3e4a397b
Immutable node_observations RUN: not yet recorded for this finding
```

Do not upgrade the finding to an immutable hardware PASS/FAIL checkpoint until a
published run exists.

## Existing implementation that must be preserved

Current Chatter binary adapter already treats these as controller-reset markers:

```text
[SYS] RADIO FATAL ...
ESP-ROM:
rst:0x
```

It keeps a controller epoch separate from physical transport generation, waits for:

```text
[SYS] CHATTER READY
```

and can raise:

```text
local_controller_reset
```

when a reset invalidates an in-flight local BINARY presentation.

`FileTransferManager` already treats these local outcomes as bounded replay candidates:

```text
local_tx_unknown
local_disconnect
local_controller_reset
```

Current source also contains host-side tests for:

```text
controller reboot while waiting for exact BINARY presentation
FT1 replay of the same application message after controller reboot + READY
```

Therefore this TODO is not a redesign of FT1. It must identify and close the lifecycle
or state-machine gap between the modeled path and the real ManagedSession/TUI transport
path.

## Relationship to TODO_029 and TODO_030

TODO_029 remains the broad FT1 same-process reconnect/MISSING/RESULT repair contract.
TODO_030 remains the Chatter rule that ordinary FT1 must not depend on TELEMETRY or
mutate the operator's CHAT/TELEMETRY/BOTH mode.

TODO_032 is a focused follow-up discovered during physical validation:

```text
local Chatter controller resets during an active FT1 operation
same SerialTerminal process remains alive
transport may disconnect/reconnect (BLE)
or may remain physically open while ESP restarts (USB)
```

Required outcome: bounded recovery or explicit terminal failure, never an indefinite
hang.

## Target behavior

### Transfer lifecycle

When the local controller resets during an active transfer:

```text
sending / waiting local BINARY settlement
        |
        v
controller reset detected
        |
        v
recovering_local_node
        |
        +--> stop issuing new FT1 application messages
        +--> preserve transfer record + prepared source
        +--> preserve transfer_id/chunk identity
        +--> wait for usable local transport/controller
        |
        v
[SYS] CHATTER READY + usable session
        |
        v
replay the current ambiguous idempotent FT1 message
        |
        +--> success -> continue transfer
        |
        +--> bounded recovery exhausted
                  -> terminal FAILED with stable code/phase
```

The same logical FT1 application identity must be preserved. Do **not** silently create
a new transfer ID after a local controller reboot.

For DATA, preserve the same file-level:

```text
transfer_id
chunk_index
payload
```

The underlying Chatter USER session/sequence may change after controller reboot; FT1
application identity remains authoritative for duplicate safety and final repair.

### BLE and USB reset distinction

Both reset shapes must work:

```text
BLE:
controller reset -> physical BLE disconnect -> reconnect -> READY

USB:
USB serial device may remain open while ESP reboots
-> controller epoch changes without a transport-generation change
-> READY appears on the same physical session
```

Do not solve only the BLE generation-change case.

### Bounded recovery

Recovery must be finite.

Current source already has bounded controller-ready timeout/local message replay
concepts. The exact constants may be adjusted, but the contract is:

```text
no infinite wait
no infinite replay
no automatic whole-file restart loop
```

If the local controller never becomes usable, or repeated local resets exhaust the
bounded policy, terminate the transfer with a stable machine-readable failure such as:

```text
code=local_controller_recovery_failed
phase=local_recovery
```

Exact naming may follow existing error conventions, but TUI and agent API must expose
a deterministic terminal reason.

### TUI behavior

During recovery, show an explicit state equivalent to:

```text
recovering local node
```

Do not leave the operator looking at a frozen ordinary progress percentage with no
explanation.

After recovery:

```text
recovering local node -> sending/repairing/waiting verification
```

or:

```text
recovering local node -> failed: <stable reason>
```

`Ctrl+C` remains the reliable escape/cancel path during recovery. Recovery state must
not create a transfer lock that prevents operator cancellation.

### Agent API behavior

`file_transfer_observe` must expose enough structured state/events to distinguish:

```text
normal sending
local controller reset detected
recovering local node
local controller ready
application message replayed
recovery exhausted / failed
completed / cancelled
```

The JSONL request loop must remain responsive while recovery waits.

## Message replay rules

Replay is owned by FT1/application semantics, not by blind generic transport retry.

Allowed after ambiguous local controller reset:

```text
same META + same transfer_id
same DATA + same transfer_id/chunk_index/payload
same END + same transfer_id
```

These messages are already required to be idempotent by TODO_029.

Do not change generic `tx_state=unknown` semantics so arbitrary Serial/SPP/BLE writes
are blindly repeated.

## Interaction with firmware radio recovery

Firmware-side `RX_RESTART -16` diagnostics and bounded SX1278 recovery are tracked in
`lora-sack-protocol/dev_chat_binary` TODO_012.

If firmware recovers the radio without rebooting, SerialTerminal should not need a
controller-reset recovery cycle; ordinary Chatter ACK timeout/retry and FT1 processing
continue.

If firmware recovery ultimately fails and the ESP reboots, TODO_032 owns the host-side
reaction described here.

The host task must remain correct for any other deliberate/unexpected Chatter controller
reboot, not only `RX_RESTART -16`.

## Scope

- reproduce the physical hang deterministically with `/reboot` injection;
- trace the actual ManagedSession -> ChatterBinaryUserAdapter -> FileTransferManager ->
  TUI lifecycle around controller epoch/reset/reconnect;
- fix the state/lifecycle gap without changing FT1 wire format;
- explicit recovery state/events for TUI and agent API;
- bounded replay/failure behavior;
- preserve operator cancellation;
- BLE and USB controller-reset coverage;
- physical revalidation and exact checkpoint recording.

## Non-goals

- no firmware source changes from this SerialTerminal TODO;
- no attempt to reproduce or diagnose the SX1278 `-16` root cause;
- no persistent resume after SerialTerminal process death/restart;
- no new FT1 per-chunk application ACK;
- no LoRa SACK design or implementation;
- no automatic new-transfer/full-file resend loop;
- no blind generic retry of ambiguous physical writes;
- no requirement that one SerialTerminal instance control both LoRa nodes.

## Implementation checklist

- [ ] create a deterministic regression reproducer using local controller `/reboot`;
- [ ] identify whether the physical hang is in ManagedSession reconnect/epoch handling,
      binary presentation settlement, FileTransferManager replay wait, TUI ownership,
      or a combination;
- [ ] guarantee an active send observes controller reset even when USB transport remains
      physically connected;
- [ ] guarantee BLE disconnect/reconnect wakes the active FT1 local-message wait;
- [ ] enter an explicit local-recovery transfer state/event;
- [ ] stop issuing later chunks while local controller recovery is unresolved;
- [ ] after READY/session usability, replay only the current ambiguous idempotent FT1
      application message;
- [ ] preserve `transfer_id`, DATA `chunk_index`, prepared wire representation and
      progress accounting;
- [ ] return to the normal transfer state after successful replay;
- [ ] make controller-ready wait and local replay count/time bounded;
- [ ] convert recovery exhaustion to a deterministic terminal failure;
- [ ] keep Ctrl+C/file-transfer cancel responsive throughout recovery;
- [ ] expose recovery events/state through `file_transfer_observe`;
- [ ] ensure TUI does not display a silent frozen percentage during recovery;
- [ ] preserve TODO_030 no-TELEMETRY/no-output-mode-mutation contract;
- [ ] document final exact implementation and validation checkpoints.

## Automated validation

At minimum cover deterministic reset injection at these sender phases:

- [ ] reset after META local write but before exact local presentation;
- [ ] reset during an ordinary DATA message before local presentation settlement;
- [ ] reset after substantial DATA progress (not only at 0%);
- [ ] reset while END/final verification is active;
- [ ] BLE generation changes during reset/reconnect;
- [ ] USB controller epoch changes while transport remains physically open;
- [ ] same application message is replayed with stable FT1 identity;
- [ ] identical DATA replay does not double-count progress;
- [ ] repeated resets remain bounded and eventually recover or fail;
- [ ] missing READY / unusable controller becomes terminal FAILED, not an infinite
      wait;
- [ ] Ctrl+C cancellation during `recovering_local_node` terminates promptly;
- [ ] agent API remains responsive and exposes recovery events;
- [ ] TUI ownership/mute is released correctly on completed/failed/cancelled recovery;
- [ ] existing TODO_029 MISSING/selective-repair tests remain green;
- [ ] existing TODO_030 no-telemetry/output-mode tests remain green;
- [ ] broad repository pytest/static/complexity/compile gates pass.

## Physical validation

Do not wait for a natural `RX_RESTART -16`.

Use Chatter `/reboot` as a controlled fault injection while a real two-node transfer is
active.

Required physical matrix:

```text
sender local transport = BLE
    reboot near META/0%
    reboot during DATA after visible progress
    reboot near END/waiting verification

sender local transport = USB
    same representative controller-reset cases,
    specifically proving the open-USB/controller-epoch path
```

For each case require:

```text
no indefinite transfer hang
recovery state visible
same SerialTerminal process stays alive
Ctrl+C remains usable
transfer either resumes and verifies correctly
or terminates with explicit bounded failure
no silent new transfer_id/full resend
```

After deterministic `/reboot` validation passes, a future naturally occurring
`RX_RESTART -16` is useful corroboration but is not a closure prerequisite if the
observable controller-reset sequence is equivalent.

Record exact SerialTerminal revision, firmware identity, transport topology and
immutable run evidence before claiming physical PASS.

## Findings

- TODO_029 already defines same-process reconnect repair and idempotent FT1 control/data
  identities.
- Current Chatter adapter already recognizes firmware fatal/boot reset markers and
  `CHATTER READY`.
- Current FileTransferManager already has bounded replay handling for
  `local_controller_reset` in the modeled path.
- Current tests already simulate an exact
  `[SYS] RADIO FATAL RX_RESTART after TX (-16), rebooting` sequence and same-message
  FT1 replay.
- A real physical run nevertheless left file transfer stuck after BLE reconnect,
  proving that the modeled path is not sufficient evidence of end-to-end recovery.
- The rare radio failure is therefore unnecessary for host reproduction: `/reboot`
  can exercise the same controller lifecycle deterministically.

## Result

Implemented: `OPEN`
Validated: `OPEN`
Status: `OPEN`
