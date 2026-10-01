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
- capability-based BLE visibility (advertised NUS or cached confirmed NUS);
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

Transport code may accept generic configuration such as BLE write UUID and receive characteristic/stream mappings. It must not import controller profiles, normalize controller aliases, recognize controller commands, infer application identity, or re-export controller constants.

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

`BinaryUserTransport` exposes raw binary payload capacity, binary receive delivery
and controller-local `send_binary()` settlement. A successful send means the local
transport write is known and the profile-specific controller has exposed its bounded
submission/first-transmit signal; it is explicitly not peer delivery proof. The
transport does not expose filenames, compression, filesystem state or file progress.

Human Chatter USER presentation state is also profile-owned. Sent-but-unresolved
human payloads are released when a controller reset/boot/READY boundary is observed,
even if the USB-UART transport never disconnected; unsent session-queue entries are
preserved for the existing TX path.

The bundled `chatter` profile owns the local `/bin <BASE64>` command/presentation
adapter. It settles a send on the exact matching local `> [BINARY] <BASE64>`
presentation emitted after first physical TxDone. `DELIVERY WAIT_ACK/ACK/FAILED`
telemetry is diagnostic only and is not part of FT1 progression, backpressure,
correctness or reconnect recovery. Base64 is local textual encapsulation only; the
LoRa BINARY USER payload remains raw bytes. FT1 never changes CHAT/TELEMETRY/BOTH
mode on behalf of a transfer. Unknown Chatter mode is discovered through the
profile-owned read-only `/help` status response before BINARY submission.

Chatter controller lifetime is tracked separately from generic transport connection
generation. A firmware reset may leave USB-UART physically connected, so a pending
profile-local BINARY settlement is invalidated by controller reset markers and replay
is held until a new `CHATTER READY`. Generic `ManagedSession` remains unaware of
Chatter reboot syntax.

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
- Chatter BINARY USER local base64 framing and exact local BINARY-presentation settlement used to implement the generic `BinaryUserTransport` capability; DELIVERY telemetry remains diagnostic only.

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

1. keep physical discovery generic and capability-based;
2. implement a new `TerminalProfile` for controller-specific configuration/commands/presentation;
3. if long-running measurement support is needed, register a profile-owned `SweepAdapter` through the generic adapter interface rather than branching in `agent.py` or `sweep.py`;
4. pass profile-provided BLE layout/configuration into `BleNusTransport` rather than creating a controller transport;
5. keep `ManagedSession` and session cursor/event semantics unchanged unless the generic contract itself truly needs to evolve;
6. put project-specific analysis/acceptance guidance in a consuming skill, not in the generic sweep engine;
7. add tests proving both the new profile behavior and continued zero-controller-assumption behavior of `generic`.

If a proposed change requires the generic core to recognize a controller name, advertised-name prefix, alias, command, application identity, or protocol outcome, treat that as an architecture warning: first determine whether the behavior belongs in a profile or a consuming project-specific layer.
