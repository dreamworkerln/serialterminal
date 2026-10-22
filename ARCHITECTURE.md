# SerialTerminal architecture

This document records durable architecture boundaries for the host-side SerialTerminal code. Runtime/API details remain canonical in `AGENT_API.md`; project-specific LoRa-Chatter operating rules remain in `.agents/skills/node-agent/SKILL.md`.

## Core principle: profile segregation

Controller-specific behavior is isolated behind `TerminalProfile` implementations. The generic SerialTerminal core must remain usable without knowing which controller, firmware, project, advertised device name, command vocabulary, or application protocol is on the other side of a transport.

The architectural rule is:

```text
generic discovery / identity / session / transport mechanics
                         ↑ configured by
                 selected controller profile
                         ↑ consumed by
          human UI / agent / project-specific skill
```

A profile may configure generic mechanisms, but it must not become a second transport/session implementation.

## Ownership by layer

### Generic discovery and physical identity

Generic discovery owns:

- discovery of USB Serial, BLE NUS and Bluetooth SPP transport paths;
- prototype BLE visibility of all scan results plus connected BlueZ devices;
- capability probing/cache mechanics;
- sticky physical transport identity and reconnect target selection;
- generic chooser/scanner behavior.

The human device chooser and the capability scanner have different latency contracts.
The chooser reuses already discovered/cached physical identities and must not perform an
active Bluetooth scan before showing known targets. Explicit scanner/discovery paths
remain responsible for finding new devices. A known BLE address may still require a
bounded backend lookup before GATT connect, but that lookup should terminate when the
specific address is found rather than waiting for a full discovery window.

Generic discovery must not infer controller type from an advertised name and must not contain controller-specific aliases or trusted name prefixes. A profile does not whitelist a device into discovery.

Human chooser eligibility is supplied by `BleProfileConfig.chooser_requires_nus`:
Chatter requires an advertised NUS service or confirmed NUS cache capability;
generic keeps all discovered BLE devices. Discovery carries advertised services
as identity metadata through address deduplication and BlueZ busy-state refresh.
The selector applies the current profile policy after merging candidates, including
remembered/cache/connected sources for F2. Names and busy state are not capability
evidence. This filter performs no probe/connect/disconnect, changes no Serial/SPP
eligibility and does not restrict the all-device capability scanner or JSONL discover.

### Controller profiles

A `TerminalProfile` owns controller-specific configuration and convenience behavior, including when applicable:

- connect/reconnect preamble actions;
- controller command recognition/classification;
- human hotkeys and actions;
- human help additions;
- presentation policy;
- human-console stream selection;
- BLE characteristic-to-stream configuration supplied to the generic BLE transport;
- controller-specific measurement adapters exposed through the generic sweep-adapter registry.

A profile describes controller semantics through generic interfaces. A profile-owned sweep adapter may apply controller commands and recognize controller/protocol settlement only through the capability-limited sweep context supplied by the agent. It does not open serial ports, create Bleak clients, own RFCOMM sockets, implement reconnect loops, own TX queues, or create an alternative session/event/cursor implementation.

Profile selection is explicit and per session. `generic` is the default. Different sessions in one agent process may use different profiles without changing process-global transport semantics.

### Shared operational defaults

`settings.py` owns small frozen typed defaults for Serial baud, terminal discovery,
capability scanner/prober and session reconnect policy. Equal numeric values with
different meanings remain separate policies; wire sizes and protocol/radio timing
stay with their subsystem. Each profile exposes `default_serial_baud`; generic
selector resolution uses that capability without branching on profile names.
Transports do not import profiles. Omitted baud is retained through discovery so
agent `open` and human startup apply the same profile-aware rule. Explicit CLI or
runtime baud remains selector/object state and survives profile recreation.

### BLE shutdown ownership

BLE transport owns bounded client cleanup and backend release verification. Its
optional `release_report` uses the generic Transport interface; ManagedSession and
agent close only publish that report and do not learn BlueZ paths, BLE device names
or controller commands. Linux Device1 checks/Disconnect live in `bluez_release.py`,
whose system-bus imports are lazy. The exact path belongs to the client being
closed; discovery/cache enumeration is not used to choose a cleanup target.
Lifecycle serialization excludes cleanup of a replacement ST generation. Failed
release remains explicit while other sessions continue to close. Connected-device
discovery uses read-only BlueZ Device1 enumeration. Explicit selection of a
busy candidate authorizes exact-path release before normal scan/connect, shared
by human and agent frontends. The one-shot takeover is consumed after verified
release and is not replayed on ordinary reconnect. Cross-process ownership
arbitration and PID registries remain deferred; connected does not imply orphaned.

### Generic session core

`ManagedSession` owns controller-independent lifecycle and data mechanics:

- reconnect lifecycle;
- ordered reconnect-safe TX queue;
- generic accepted-TX fence state used to prove terminal transport outcome across higher-level ownership transitions;
- bounded per-TX transport-outcome lookup and connection lifecycle generation for higher-level idempotent recovery;
- raw `SessionEvent` history and cursors;
- canonical logical-line assembly per stream;
- connection-state boundaries;
- event/line notification;
- session shutdown.

The session core receives profile-derived configuration through generic callbacks/data. It must not branch on concrete profile names such as `chatter`.

### Generic sweep job layer

`SweepJob` / `SweepJobManager` own controller-independent long-running measurement execution:

- generic plan validation, ordered axes and exact repetition counts;
- one active sweep job per agent process;
- job lifecycle and bounded terminal retention;
- bounded job-local event history and cursor/window long-poll semantics;
- progress snapshots;
- finite phase deadlines and cancellation plumbing;
- mechanical `[SWEEP]` forensic records.

The generic sweep layer consumes only the `SweepAdapter` interface. It must not branch on concrete adapter/profile names or recognize controller commands, ACK/CRC/HDR/retry semantics, radio quality, or experiment-specific classifications.

`SessionManager` owns sweep mutation admission around existing sessions. A successful sweep atomically acquires mutation ownership of all declared participating sessions and captures each session's accepted-TX fence while the same admission lock excludes new external mutation. Before adapter `prepare`, the background job waits for all pre-lease TX through those fences to reach known terminal transport outcome. Ambiguous `tx_state:"unknown"` fails the sweep rather than being erased or treated as drained. External session mutations are rejected while ownership is active; ordinary read-only observation remains available. `ManagedSession` implements only the generic TX-fence primitive and does not learn sweep/controller protocol semantics.

A sweep adapter owns only the operational synchronization needed to make one requested measurement well-defined:

```text
apply coordinate
-> verify actual coordinate
-> start one sample
-> wait until that sample is operationally settled
```

That settlement may require controller-specific protocol evidence, but interpreting measurement quality remains above the sweep engine.

### Generic transports

`Transport`, `SerialTransport`, `BleNusTransport` and `BluetoothSppTransport` own physical I/O only.

Transport code may accept generic configuration such as BLE write UUID and receive characteristic/stream mappings. It may also expose a controller-agnostic human identity label already known from the physical transport, such as a BLE advertised name; profile UI may use that only as a presentation hint until controller-owned identity output arrives. Transport code must not import controller profiles, normalize controller aliases, recognize controller commands, infer application identity, or re-export controller constants.

A logical `BleNusTransport.write()` remains one byte stream, but `response=False` GATT output is segmented to the selected characteristic's `max_write_without_response_size`. Segmentation inserts neither delimiters nor pacing sleeps. If a later fragment fails after one or more earlier fragments completed, the logical TX outcome is ambiguous and must surface as `tx_state=unknown` rather than allowing the generic session queue to replay the whole payload blindly.

Generic session additionally owns addressable cancellation of a TX whose backend
write is not in flight, and bounded drain of an explicit set of caller-owned TX IDs.
Shutdown or unexpected worker exit settles accepted TX as cancelled before write or
unknown while a write remains in flight. Controller-specific queues stay outside
this fence. Serial nonzero short writes, invalid backend results and write/flush
exceptions are ambiguous and are never blindly replayed by the generic session.

The profile binary factory receives an optional generic `cancel_tx` hook alongside
`wait_tx_outcome`. The profile adapter tracks its own accepted host writes and exposes
an optional bounded `drain_binary` capability to FT1; unrelated writes are preserved.
Adapter controller readiness, output-mode query, host write and presentation waits
share an absolute monotonic deadline. FT1 recovery passes its remaining deadline
through optional `prepare_binary` for local readiness, then allows the RF send its
profile-derived budget; `send_binary_until` remains an explicit caller bound.

### File transfer layering

File transfer is an application layer above an opaque BINARY application transport
abstraction:

```text
FileTransfer / FT1
        |
        v
BinaryUserTransport
        |
        v
profile-owned binary adapter
        |
        v
ManagedSession / Transport
```

`BinaryUserTransport` exposes raw payload capacity, receive delivery and profile-owned
`send_binary()` settlement. The profile defines its precise local/link proof; neither
successful host write nor a node ACK proves remote host durability. It does not expose
filenames, compression, filesystem state or file progress.

An optional `timing_budget_s(purpose)` capability supplies positive finite deadlines
for control, resume and drain. Generic FT1 consumes these opaque budgets; concrete
LoRa ToA, frame sizes, ACK/retry policy, config commands and SPI readback remain in
the Chatter profile. The profile caches verified PHY by controller epoch, transport
generation and configuration revision. During local boot, existing control/idle
waits may use the last verified PHY estimate; this does not grant RF admission.
Config changes clear that estimate. Invalid readback prevents RF submission.
There is no implicit overall hour deadline and no timing-based DATA pacing.

Human Chatter USER presentation state is also profile-owned. Sent-but-unresolved
human payloads are released when a controller reset/boot/READY boundary is observed,
even if the USB-UART transport never disconnected; unsent session-queue entries are
preserved for the existing TX path.

The bundled Chatter profile composes `ChatterMachineClient` with an explicit legacy
adapter. The protected `/m1` codec, CRC, epoch/request correlation, two-slot window,
cached QUERY and LINK_OK settlement follow `CHATTER_MACHINE_PROTOCOL_V1.md`.
Machine RX/outcomes remain independent of human output mode. Explicit old-firmware
rejection selects `/bin` compatibility, whose first-TxDone presentation is a weaker
local proof and whose TELEMETRY-only limitation remains. Silence never selects legacy.
Human DELIVERY telemetry remains diagnostic; no metadata is added to radio USER.

FT1 has one coordinator instance with recovery, durable-storage and pipeline policies.
A bounded outbox serializes transport operations and terminal drain; the RX worker
queues control output without waiting for serial/BLE. RX/control overflow fails visibly
while preserving usable partial state. Unique DATA updates use incremental byte counts.
Close discards unstarted sends, records unresolved terminal work and retains ownership
until settling; no discarded terminal job can silently leave a published file verifying.

Chatter controller lifetime is tracked separately from generic transport connection
generation. A firmware reset may leave USB-UART physically connected, so a pending
profile-local BINARY settlement is invalidated by controller reset markers and replay
is held until a new `CHATTER READY`. Generic `ManagedSession` remains unaware of
Chatter reboot syntax.

`profiles/chatter/controller_lifecycle.py` owns the shared local-line grammar for
machine, legacy, PHY-cache invalidation and human presentation. It matches complete
boot/reset lines from column zero and the exact READY line, removing terminal CR/LF
only. USER/echo prefixes, leading whitespace and quoted markers are never removed.
Thus chat such as `first:` or a quoted `ESP-ROM:`/READY cannot release machine tickets,
advance the controller epoch or invalidate the verified PHY cache. Output-mode
responses used as readiness proof must also begin with their local `[SYS]` syntax.
Generic session/transport and frontends only forward logical lines to the profile.

FT1 owns metadata, chunk identity, compression, hashes, receiver storage, progress,
MISSING repair and final RESULT semantics. In-process reconnect repair keeps the same
transfer_id/chunk_index identities, retains incomplete receiver state, selectively
resends requested DATA ranges, and uses idempotent META/END replay when control outcome
is missing. Incomplete receiver state is bounded by an FT1-owned inactivity timeout so
an abandoned META cannot hold session mutation ownership forever.

`ManagedSession` remains unaware of FT1. Its generic per-TX outcome wait and
connection-generation hooks let a profile/application detect an ambiguous local
boundary without teaching the session about files. The generic TX queue still never
blindly repeats `tx_state=unknown`; FT1 may replay the same idempotent application
message above that boundary.

Neither `ManagedSession` nor generic Serial/BLE/SPP transports may learn filename,
chunk, compression, MISSING or filesystem semantics.

Frontend and agent code may consume the generic profile capability
`make_binary_user_transport()`; they must not branch on a concrete profile name.
A future profile/transport can therefore provide the same opaque binary capability
without rewriting FT1.

### Frontends

Human CLI/TUI and JSONL agent frontends select a profile and connect it to the shared discovery/session/transport core.

The human TUI is a generic SerialTerminal frontend, not a LoRa-Chatter application.
Its base experience must remain useful with arbitrary serial/BLE/SPP controllers and
devices: connection state, terminal output, editable input, generic transport/session
status and ordinary device selection belong to the frontend itself.

Controller-specific UI is additive and profile-owned. The selected profile may supply
extra presentation, actions and panels through frontend-facing profile interfaces. For
example, the bundled `chatter` profile may expose radio configuration/status,
Chatter telemetry, sweep controls or file-transfer presentation, while the `generic`
profile keeps a simpler general-purpose terminal workflow comparable in scope to a
traditional serial terminal such as CuteCom.

The frontend must not branch on a concrete profile name to construct controller
semantics. If a richer profile needs a radio-specific panel or action, the capability
and data/action contract belongs to the profile boundary; generic TUI layout and focus
mechanics may render it without learning Chatter commands or protocol rules.

Profile panels may expose `poll_actions(transport, connected, connection_generation)`
to return bounded frontend refresh actions. Generic TUI only dispatches those
actions through the existing session queue; it does not interpret commands or
responses. Chatter owns USB identity confirmation, canonical NODE parsing and
three rate-limited read-only identity retries after the initial Serial preamble.
BLE does not use that retry. Device-selection identity seeding runs while receive
is paused, before connection resumes, so a fast response cannot be overwritten
by a later transport hint. JSONL and classic initialization retain their contract.

Frontends may expose explicit profile selection, but they must not recreate controller semantics outside the selected profile. A compatibility option that overrides only one piece of profile behavior is not a substitute for a profile and should not be added to the generic API.

### Project-specific skills and firmware semantics

Application/protocol acceptance rules belong above SerialTerminal core:

- generic machine-interface mechanics: `AGENT_API.md` and `.agents/skills/serialterminal-agent/SKILL.md`;
- LoRa-Chatter operating/validation rules: `.agents/skills/node-agent/SKILL.md`;
- authoritative RF/protocol semantics: corresponding firmware source/docs.

SerialTerminal core must not promote protocol-specific delivery criteria, node roles, retry policy, RSSI/SNR/Q expectations, or lab topology into generic transport/session behavior.

For the bundled Chatter sweep, diagnostic isolation is host-orchestrated rather than a firmware mode. The profile adapter uses existing Chatter commands to settle reliable USER work and disable heartbeat/diagnostic/echo-loop/manual-echo activity, while generic sweep ownership blocks competing SerialTerminal mutations. No firmware `/sweep` command or wire bit/token is part of the SerialTerminal contract. Quiet-frequency/environment isolation from third-party RF remains a coordinator responsibility.

## Dependency direction

The intended dependency direction is:

```text
human CLI -------------------+
                             |
JSONL agent -----------------+----> profile interface/config
                             |              |
                             |              +----> profile-owned SweepAdapter
                             |                            ^
                             |                            |
                             +-------> SweepJobManager ---+
                             |              |
                             |              v
                             +-------> SessionManager / TerminalSession
                                            |
                                            v
                                      ManagedSession
                                            |
                                            v
                                       Transport API
                              +-------------+-------------+
                              v             v             v
                           Serial          BLE NUS       SPP

project-specific agent skill ----> generic agent API + explicit profile
firmware semantics --------------> consumed as external controller contract
```

Forbidden reverse dependencies include:

```text
transport -> concrete controller profile
generic discovery -> controller advertised-name convention
ManagedSession -> concrete profile name/controller command
agent generic API -> one-off controller compatibility toggle
generic sweep engine -> concrete adapter/profile name or controller command
generic sweep engine -> RF/protocol quality classification
terminal generic module -> re-export of controller constants for old callers
```

## Current Chatter mapping

For the bundled `chatter` profile, controller-specific ownership currently includes:

- `/id` connect preamble for the agent session path;
- Chatter human command/hotkey/presentation behavior;
- BLE `0003 -> chat` plus optional `0004 -> telemetry` mapping;
- command classification helpers and Chatter presentation state;
- the `chatter.reliable_user` sweep adapter, including Chatter quiet-state preparation through existing commands, command/config application and reliable-USER operational settlement;
- host-side Chatter sweep isolation semantics: profile preparation plus generic SerialTerminal session ownership; no firmware `/sweep` command or wire-level sweep identity is part of this contract;
- Chatter local machine codec/correlation/link settlement and explicit legacy BINARY-presentation compatibility, implementing generic `BinaryUserTransport`; human DELIVERY telemetry remains diagnostic only.

The following remain generic and must not depend on Chatter naming:

- BLE discovery eligibility;
- BLE target identity/address locking;
- NUS connection/reconnect mechanics;
- raw notification delivery;
- TX queueing;
- `observe` events/lines/cursors;
- run logging mechanics;
- generic sweep plan/job/cursor/retention semantics;
- participating-session mutation ownership;
- pre-sweep accepted-TX fencing and ambiguous-TX rejection;
- FT1 file metadata/chunks/compression/SHA/filesystem/progress semantics.

## Extension rule for a new controller

To add another controller family:

1. keep physical discovery generic and controller-independent; visibility alone is not proof of capability;
2. implement a new `TerminalProfile` for controller-specific configuration/commands/presentation;
3. if long-running measurement support is needed, register a profile-owned `SweepAdapter` through the generic adapter interface rather than branching in `agent.py` or `sweep.py`;
4. pass profile-provided BLE layout/configuration into `BleNusTransport` rather than creating a controller transport;
5. keep `ManagedSession` and session cursor/event semantics unchanged unless the generic contract itself truly needs to evolve;
6. put project-specific analysis/acceptance guidance in a consuming skill, not in the generic sweep engine;
7. add tests proving both the new profile behavior and continued zero-controller-assumption behavior of `generic`.

If a proposed change requires the generic core to recognize a controller name, advertised-name prefix, alias, command, application identity, or protocol outcome, treat that as an architecture warning: first determine whether the behavior belongs in a profile or a consuming project-specific layer.


### Human TUI and file-transfer controls

Output selection belongs to the controller profile and remains independent of FT1.
The TUI asks `TerminalProfile.human_action_is_non_disruptive` before submitting a
human action during an active transfer, including its final settlement. Chatter
classifies presentation controls and read-only queries as non-disruptive. Mutations,
RF text, device/profile changes are rejected with a message until completion/cancel;
ordinary input never implicitly cancels, closes or replaces a file/session. The file
manager does not recognize presentation commands or classify human actions.
The frontend-local `/clear` is handled before controller action classification and
FT1 admission checks. It shares F4's output-buffer/scrollback reset, preserves logs,
manager/session ownership and input history, and sends no device command. F9 help
lists the alias; the bottom shortcut bar starts with F4 so it remains visible.


A frontend-owned wide progress overlay renders the manager's ROOT snapshot, including
recursive repair status. F7 hides/shows the overlay; filenames wrap within it.
The overlay/confirmation have their own Dracula color pairs. F10 is unassigned.
Esc/F6 opens an address-bound cancellation confirmation. No is left, Yes is right,
Yes is selected initially; arrows select, Enter confirms and repeat Esc continues.
The transfer keeps running while the modal captures input. A stale confirmation
cannot cancel a newer ROOT/runtime attempt (including same-ID readmission) or submit
its Enter to the controller. Successful
completion closes progress and the compact header once. F7 toggles only active
transfers. Terminal progress headers are hidden; a dismissed terminal window stays
closed. The frontend event sink announces each ROOT attempt's terminal outcome
once in normal white chat output and the LOCAL primary log. It uses the bound
manager's public ROOT snapshot to exclude recursive service-file results, independently
of rendering/window visibility. Start, phase, recovery/resume, cancel-request and
suspension events also produce human chat summaries; per-chunk progress remains
visual rather than filling chat. Accepted local cancellation closes both the question
and progress overlay immediately; the manager retains ownership until settlement.
Received peer cancellation dismisses any question but retains stopped progress; Esc
closes it without confirmation. A stale Enter from the dismissed question is consumed.
These transitions are symmetric for TX/RX. Failed results remain until Esc; a
background terminal result never reopens the overlay. Success closes it automatically.
The manager's `presentation_snapshot()` supplies an atomic ROOT snapshot with runtime
ownership, an opaque per-attempt identity, cancel status and retained resume/activity
counters. Its process-local metadata is excluded from JSONL/status/history snapshots.
Cancellation validates the expected attempt under the admission lock; queued RX
cancellation retains that identity too. The frontend owns only closed/foreground/
background modes. One redraw uses one snapshot for overlay/header/body geometry.
Unowned/suspended history cannot enable F7. Profile-public controller status may
describe recovery without teaching the frontend boot syntax. READY alone cannot
create a transfer; actual resumed FT1 activity restores foreground once, including
when recovery occurred entirely between redraws. Background progress is one short
line with an F7 hint, without a second progress bar or detailed counters.
If success arrives during confirmation,
a visible terminal notice captures Enter/Esc before dismissing that stale modal.
The same visible guard remains if the snapshot/session disappears.
Ctrl+C/Ctrl+Q retain process-quit semantics.

FT1 validates the UTF-8 basename against the selected binary transport META budget
before preparation, reservation, sender-journal lookup or claim. The frontend displays
the structured failure; it does not duplicate the transport's wire-size calculation.

Before shutdown checkpoints, the file manager detaches incoming binary admission and
joins its RX worker; explicit cancellation is not converted into durable suspension.
An already ending/published RX frame is not restored from a stale recursive pointer.
The TUI keeps the profile adapter attached to completed incoming lines during manager
drain/CLOSE, and detaches it only after manager close returns.
TUI catches action errors, logs the traceback in the process application log and marks
an ERROR badge; cleanup failure does not skip the remaining resource cleanup.
The process log is separate from session evidence. Timing uses a bounded batch writer,
while application error records flush/fsync immediately.


### Serial physical-port ownership

On POSIX, `SerialTransport` requests pyserial exclusive ownership before opening a
tty. Two cooperating SerialTerminal processes must not read the same physical serial
stream concurrently: the second process remains disconnected and reports
`serial device busy: <path>`. This ownership is transport-level and independent of
controller profile, FT1, or session mutation ownership.

### FT1 source and publication ownership

FT1 preparation owns a temporary immutable wire snapshot for the current attempt,
including uncompressed data. Resume recreates and verifies that representation
against the durable sender journal. The receiver checkpoints bytes before advertising
RESUME progress and owns one destination from publishing intent through completed
tombstone. RESULT OK follows the durable commit; generic transport/session code
does not interpret this file-storage evidence. [FT1_RESUME.md](FT1_RESUME.md) owns
the ordering, filesystem limitations and restart contract.

## Codec2 voice-message application layer

Store-and-forward voice is intentionally above FT1 rather than inside the controller
profile or transport stack:

```text
TerminalTui
    |
    +-- FileTransferManager / FT1 ----------------------> BINARY USER transport
    |             ^
    |             | completed finalized .stvoice.c2 / verified ROOT RX completion
    |             |
    +-- VoiceMessageService
          |
          +-- Codec2Library -> Codec2Codec -> pinned portable libcodec2.so
          +-- AudioBackend -> arecord / aplay (Linux first implementation)
```

`VoiceMessageService` owns microphone/playback admission, the standard `.c2` file
lifecycle, the pending local voice-to-FT1 admission and autoplay policy. It never owns
FT1 metadata/chunks/hash/repair/resume/RESULT semantics. The generic TUI still obtains
file-transfer capability from the selected profile; there is no `profile.name ==
"chatter"` voice branch. Voice is enabled only when the runtime has an FT1 manager, an
explicit SDK tree and the local audio backend capability. The Codec2 shared library is
loaded lazily and must resolve inside that SDK tree with pinned provenance.

TX capture encodes S16_LE mono 8 kHz PCM directly into standard Codec2 mode 3200 frames
and writes the seven-byte `.c2` header immediately. A partial PCM frame is zero padded
once, only after capture has stopped and stdout has drained. Header-only/invalid output
is never admitted to FT1. Admission calls `FileTransferManager.start_send()` outside the
curses thread. The local voice attempt is registered before that call so a terminal FT1
event that races the return value can be reconciled exactly once. If admission is
refused, the completed source is retained as `READY_FILE`; normal F5 is the manual retry
path rather than a second voice delivery state machine. Capture jobs and unsettled TX
attempts have separate ownership: an older terminal can clean up its source without
changing a newer recording/admission. Each pending TX retains its job identity until
settlement; overflow reconciliation uses public retained snapshots for older TXs.

RX autoplay is a consumer of the existing verified durable ROOT `transfer_completed`
event. The event's wire filename decides whether it is a voice message while
`progress.final_path` is only the already-published content location. Recursive child
files and nonterminal/failed/cancelled results never become audio events. Event logging
and voice dispatch have independent exception boundaries; playback does not run from
the logger or FT1 callback. A bounded queue serializes playback and rejects new autoplay
requests on overflow while preserving the received file and successful FT1 result.
RX manager/generation is checked both before file validation and before enqueue, so
late events from a replaced session cannot create a new autoplay admission.

One condition-protected audio owner prevents simultaneous capture and playback. RX may
continue through FT1 while capture is active, but its playback waits. The owner is
reserved in STARTING before SDK loading and microphone startup; a timed-out wait cannot
admit playback. F12 never aborts
active playback. During capture/finalization/admission the TUI blocks device/profile/F5
and disruptive human actions while preserving non-disruptive profile controls and
normal process exit. Process cleanup, event queues and playback queues are bounded; the
recording itself intentionally has no arbitrary duration/encoded-byte timer in this
first stage and ends on the second F12. Shutdown never implicitly sends an unfinished
recording, and late admission/terminal results are retention-only once service shutdown
has begun. Capture outcomes distinguish a requested graceful stop from forced
terminate/kill and unexpected exit; forced or failed capture is never auto-sent.
The quiet arecord backend may return status 1 on normal SIGINT (alsa-utils 1.2.6);
that result is accepted only after our requested stop, without forced fallback or
stderr diagnostic. An unsolicited exit or status 1 with diagnostic remains a failure.
Every spawned playback child is stopped/reaped on decoder/iterator/pipe failure as
well as cancellation, before releasing its process ownership.

The TUI draws the voice startup/recording/finalization/admission snapshot in the
same overlay area as the FT1 window. Only RECORDING uses a solid red background,
white bold text, elapsed timer and F12 stop/send hint. Preparation is neutral;
FT1 presentation resumes when local voice work settles. The panel cannot be hidden
by F7/scrollback, does not own capture or FT1 lifecycle, and does not create a modal
input handler. Small terminals retain a compact recording indicator. RX playback uses a muted blue-violet
panel with estimated elapsed/total time, progress and a centered Cancel button.
Progress uses the monotonic clock after the first decoded PCM frame and is bounded by
decoded duration and validated file duration; it is not hardware sample position and
stays below 100% until the backend finishes. Enter/Esc/click Cancel closes the panel,
signals cancellation without blocking TUI and clears pending autoplay. A cancellation
epoch also excludes already-received RX events still in dispatch/validation; files
remain published. Future messages can autoplay. The backend cancellation watcher owns
the exact child and interrupts pipe writes/drain, then cleanup reaps it before audio
ownership is released. F5 remains available; general window/focus coordination belongs
to TODO_065 rather than introducing broad action prohibitions here.

The first implementation is human-TUI only. It adds no agent JSONL operation/schema,
no firmware/wire behavior and no realtime voice transport.

## FT1 persistent sender ownership

Frontends pass the selected generic device_key as an opaque peer_key to the file
manager. FT1 owns bound journal/lease namespaces and validation; discovery,
ManagedSession and transports do not learn FT1 or controller-specific identity
rules. No concrete profile branch, controller alias or USB/BLE identity inference
is added to generic mechanics. See FT1_RESUME.md for same-key restart and volatile
anonymous bindings in the fixed two-radio topology.
