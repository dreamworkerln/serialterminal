# Chatter controller lifecycle recovery TODO

TODO-ID: TODO_034
Status: IMPLEMENTED / PHYSICAL VALIDATION OPEN
Parent: `TODO_033_FT1_RESUMABLE_TRANSFER_AND_CONTROLLER_RECOVERY`

## Current implementation status

Automated implementation is complete on the current TODO_033 workstream. The controller lifecycle now has a Chatter-owned controller epoch/state distinct from transport `connection_generation`; reset/fatal evidence invalidates controller-owned state, repeated evidence for one reboot is deduplicated, READY establishes usability, bounded wait/cancel behavior is available to FT1, and agent/TUI surfaces expose controller lifecycle state.

Implementation and hardening are included in the validated checkpoint documented by `FT1_RESUME.md`:

```text
SerialTerminal: dev_tui@2952d1e09ad550a60b25418dd10bb49e4aa73a4c
GitHub Actions: 37158286307 SUCCESS
pytest:         400 passed
```

Host tests cover reset/READY epoch behavior, repeated markers, cancellation/timeout, reset without transport-generation change, and the negative case where transport reconnecting without reset evidence does not manufacture a new controller epoch.

**Physical validation has NOT been run for this TODO.** In particular, the required real BLE reboot/disconnect/reconnect and USB reboot-with-tty-open cases remain OPEN. Therefore this TODO is not CLOSED.

## Purpose

Make local Chatter controller reboot/reset a first-class, bounded SerialTerminal lifecycle event instead of an implicit transport/application error.

This TODO is the foundation for later FT1 recovery work. It is intentionally broader than file transfer and intentionally stops before implementing FT1 pause/resume or persistence.

The required model must distinguish:

```text
transport generation
    physical BLE/USB/SPP connection instance

controller epoch
    firmware lifetime running behind that transport
```

A USB serial device can remain physically open while the ESP controller reboots, so a stable transport connection does not prove a stable controller epoch.

## Motivation

A physical node can currently hit a firmware fatal condition, reboot and later become usable again while SerialTerminal still has an operation waiting on state that belonged to the previous controller epoch.

The immediate observed trigger is a rare RadioLib/SX1278 failure such as `-16`, but this TODO must not be tied to that firmware defect. The same host lifecycle problem exists for:

```text
operator /reboot
watchdog reset
brownout / power interruption
fatal firmware recovery policy
BLE disconnect/reconnect around reboot
USB controller reboot while tty remains open
future firmware changes
```

SerialTerminal must either recover an operation according to that operation's explicit semantics or terminate it with a bounded stable failure. It must never wait forever merely because the controller restarted.

## Source/design checkpoint

Umbrella design was recorded from:

```text
dreamworkerln/serialterminal
dev_tui@47c67de17492435b0320f4a26d063cdd8230aab6
```

Relevant current components include:

```text
src/serialterminal/session.py
src/serialterminal/profiles/chatter/binary_user.py
src/serialterminal/tui.py
src/serialterminal/agent.py
AGENT_API.md
ARCHITECTURE.md
```

The Chatter BINARY adapter already has useful partial machinery:

```text
controller epoch distinct from connection generation
reset/fatal marker recognition
[SYS] CHATTER READY recognition
controller-owned output-mode cache invalidation
local_controller_reset error
```

TODO_034 must turn that partial behavior into a coherent lifecycle contract usable by higher-level operations.

## Architecture boundary

### Controller lifecycle is profile/controller state

Do not encode controller reboot as merely:

```text
BLE disconnected
```

because USB may stay connected.

Do not make generic `ManagedSession` infer Chatter boot strings itself. Chatter-specific reset/READY parsing remains profile-owned, while generic session infrastructure may expose neutral lifecycle hooks/events if required.

### Generic writes remain conservative

Do not weaken existing ambiguous-write semantics.

After a reset/disconnect, an arbitrary command may already have partially or fully taken effect. Therefore SerialTerminal must not introduce a global rule equivalent to:

```text
reset happened -> repeat last command
```

Replay authority belongs to the higher-level operation that can prove the operation is idempotent.

TODO_034 supplies lifecycle state and wakeups. It does not make arbitrary commands replay-safe.

## Target lifecycle

The implementation should expose semantics equivalent to:

```text
controller_state = ready
                 | resetting
                 | reconnecting
                 | unavailable

controller_epoch = monotonically changing local epoch
```

Exact names may differ, but these events must be observable/testable:

```text
controller_reset_detected
controller_unavailable
controller_ready
controller_recovery_exhausted   # if owned at this layer
```

A controller epoch change invalidates all controller-owned cached assumptions, including any state that is only valid for one firmware lifetime.

## Required behavior

### Reset detection

Recognize the existing authoritative Chatter reset/fatal/boot evidence without depending on TELEMETRY mode.

The exact list remains source-owned, but current classes include fatal/reset markers and the later `[SYS] CHATTER READY` marker.

Do not use absence of output as proof of reboot.

### BLE form

Support:

```text
controller reset
-> BLE disconnect
-> ManagedSession reconnect
-> new controller epoch becomes usable
-> CHATTER READY observed
```

The selected logical node must remain the same. Recovery must not silently migrate an owned operation to another discovered node.

### USB form

Support:

```text
controller reset
-> /dev/tty* stays open
-> boot/reset markers arrive on same transport generation
-> controller epoch changes
-> CHATTER READY observed
```

This case is mandatory and is the main reason transport generation cannot substitute for controller epoch.

### Bounded recovery

Recovery waits must have a finite overall deadline/policy suitable for a real reboot, not merely a rapid fixed retry loop.

The contract is:

```text
reset detected
-> operation can observe controller recovery state
-> wait for usable local controller within bounded policy
-> controller READY -> operation may continue according to its own semantics
-> deadline exhausted -> stable failure
```

No infinite wait and no infinite reconnect/replay loop.

### Cancellation and UI responsiveness

While controller recovery is in progress:

- TUI remains responsive;
- `Ctrl+C` retains ordinary quit/cancel semantics;
- agent JSONL command loop remains responsive;
- status/observe can distinguish recovery from normal idle/waiting;
- recovery ownership must not create a deadlock with session close/cancel.

## TUI / agent observability

Expose enough state to show a human message equivalent to:

```text
recovering local node
```

rather than leaving an apparently frozen operation.

Machine-facing state/events must allow an agent to distinguish at least:

```text
controller reset detected
transport reconnecting, if applicable
controller ready
recovery timeout/failure
```

Do not require TELEMETRY output mode to observe these events.

## Scope

TODO_034 includes:

- define the controller epoch/lifecycle contract;
- map/reset current controller-owned caches on epoch change;
- unify BLE and USB reboot behavior at the Chatter/session boundary;
- expose lifecycle state/events to interested higher layers;
- bounded controller recovery wait primitives/state;
- cancellation and close safety during recovery;
- TUI and agent visibility sufficient for later operation-specific recovery;
- deterministic host tests using `/reboot`/synthetic boot sequences;
- physical lifecycle validation with BLE and USB reset forms;
- documentation of exact lifecycle ownership.

## Non-goals

TODO_034 does **not** include:

- firmware source changes;
- diagnosing RadioLib/SX1278 `-16`;
- changing Chatter RF ACK;
- FT1-specific replay state machine;
- persistent `.part` state;
- sender file journals;
- FT1 resume wire messages;
- automatic whole-file restart;
- blind retry of arbitrary commands;
- LoRa SACK.

Those belong to later child TODOs or firmware work.

## Recommended implementation slices

Keep commits reviewable. A likely order is:

```text
1. deterministic lifecycle tests/reproducer
2. explicit controller epoch/state model and events
3. USB reset-with-port-open integration
4. BLE reset/disconnect/reconnect integration
5. TUI/agent lifecycle visibility
6. docs + final regression/cleanup
```

Each semantic checkpoint must receive targeted tests plus full CI before moving on.

## Implementation checklist

- [ ] inventory every current controller reset/fatal/READY marker and consumer;
- [ ] define one controller epoch/state authority;
- [ ] guarantee one reboot increments/changes epoch exactly once under repeated boot lines;
- [ ] invalidate controller-owned profile caches on epoch change;
- [ ] separate transport-generation changes from controller-epoch changes;
- [ ] expose lifecycle wakeup/state to higher-level operations without Chatter parsing duplication;
- [ ] implement bounded wait-for-controller-ready semantics;
- [ ] ensure BLE reconnect to the selected logical node is enforced;
- [ ] handle USB reboot with tty continuously open;
- [ ] ensure transport disconnect without reboot remains distinguishable where evidence allows;
- [ ] keep generic ambiguous TX outcome semantics unchanged;
- [ ] keep cancellation/close responsive during recovery;
- [ ] expose recovery state/events in TUI/agent surfaces;
- [ ] update architecture/API docs describing ownership;
- [ ] record exact implementation and validation checkpoints.

## Automated validation

At minimum cover:

- [ ] reset marker while no operation is active;
- [ ] reset marker while an operation waits on controller-derived state;
- [ ] repeated fatal/boot markers for one reboot do not create uncontrolled epoch churn;
- [ ] READY completes the new controller epoch;
- [ ] timeout when READY never returns;
- [ ] cancellation while waiting for READY;
- [ ] session close while waiting for READY;
- [ ] BLE reset -> disconnect -> reconnect -> READY;
- [ ] USB reset -> same transport generation -> READY;
- [ ] transport disconnect with no reset marker;
- [ ] controller reset with no transport disconnect;
- [ ] cached output/controller state is not reused across epoch;
- [ ] generic arbitrary queued command is not silently replayed solely due to reset;
- [ ] agent command loop continues servicing read-only requests during recovery;
- [ ] TUI does not display an unexplained frozen state.

## Physical validation

Use deterministic `/reboot` or equivalent intentional controller reset; do not depend on reproducing rare `-16`.

Required physical cases:

```text
BLE node:
active SerialTerminal session
-> deliberate reboot
-> disconnect/reconnect if firmware/controller causes it
-> READY
-> lifecycle becomes usable without restarting SerialTerminal

USB node:
active serial session
-> deliberate reboot
-> tty remains open if hardware behaves that way
-> boot/READY observed
-> new controller epoch recognized
```

Record exact SerialTerminal SHA, firmware SHA, transport and node identity.

## Acceptance criteria

TODO_034 is CLOSED only when:

- controller epoch is a documented first-class concept distinct from transport generation;
- BLE and USB reboot forms are deterministic and bounded;
- higher-level operations can wait for controller recovery without implementing their own reset parser;
- arbitrary ambiguous commands are not globally replayed;
- TUI and agent expose recovery state;
- cancel/close remain responsive;
- targeted tests and full CI pass;
- required physical BLE and USB reboot lifecycle cases pass at exact recorded checkpoints.

Completion of TODO_034 unblocks operation-specific same-process FT1 recovery in TODO_035.