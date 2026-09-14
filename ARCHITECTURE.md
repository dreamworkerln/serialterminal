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

Generic discovery must not infer controller type from an advertised name and must not contain controller-specific aliases or trusted name prefixes. A profile does not whitelist a device into discovery.

### Controller profiles

A `TerminalProfile` owns controller-specific configuration and convenience behavior, including when applicable:

- connect/reconnect preamble actions;
- controller command recognition/classification;
- human hotkeys and actions;
- human help additions;
- presentation policy;
- human-console stream selection;
- BLE characteristic-to-stream configuration supplied to the generic BLE transport.

A profile describes controller semantics through generic interfaces. It does not open serial ports, create Bleak clients, own RFCOMM sockets, implement reconnect loops, own TX queues, or create an alternative event/cursor model.

Profile selection is explicit and per session. `generic` is the default. Different sessions in one agent process may use different profiles without changing process-global transport semantics.

### Generic session core

`ManagedSession` owns controller-independent lifecycle and data mechanics:

- reconnect lifecycle;
- ordered reconnect-safe TX queue;
- raw `SessionEvent` history and cursors;
- canonical logical-line assembly per stream;
- connection-state boundaries;
- event/line notification;
- session shutdown.

The session core receives profile-derived configuration through generic callbacks/data. It must not branch on concrete profile names such as `chatter`.

### Generic transports

`Transport`, `SerialTransport`, `BleNusTransport` and `BluetoothSppTransport` own physical I/O only.

Transport code may accept generic configuration such as BLE write UUID and receive characteristic/stream mappings. It must not import controller profiles, normalize controller aliases, recognize controller commands, infer application identity, or re-export controller constants.

### Frontends

Human CLI and JSONL agent frontends select a profile and connect it to the shared discovery/session/transport core.

Frontends may expose explicit profile selection, but they must not recreate controller semantics outside the selected profile. A compatibility option that overrides only one piece of profile behavior is not a substitute for a profile and should not be added to the generic API.

### Project-specific skills and firmware semantics

Application/protocol acceptance rules belong above SerialTerminal core:

- generic machine-interface mechanics: `AGENT_API.md` and `.agents/skills/serialterminal-agent/SKILL.md`;
- LoRa-Chatter operating/validation rules: `.agents/skills/node-agent/SKILL.md`;
- authoritative RF/protocol semantics: corresponding firmware source/docs.

SerialTerminal core must not promote protocol-specific delivery criteria, node roles, retry policy, RSSI/SNR/Q expectations, or lab topology into generic transport/session behavior.

## Dependency direction

The intended dependency direction is:

```text
human CLI -------------------+
                             |
JSONL agent -----------------+----> profile interface/config
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
terminal generic module -> re-export of controller constants for old callers
```

## Current Chatter mapping

For the bundled `chatter` profile, controller-specific ownership currently includes:

- `/id` connect preamble for the agent session path;
- Chatter human command/hotkey/presentation behavior;
- BLE `0003 -> chat` plus optional `0004 -> telemetry` mapping;
- command classification helpers and Chatter presentation state.

The following remain generic and must not depend on Chatter naming:

- BLE discovery eligibility;
- BLE target identity/address locking;
- NUS connection/reconnect mechanics;
- raw notification delivery;
- TX queueing;
- `observe` events/lines/cursors;
- run logging mechanics.

## Extension rule for a new controller

To add another controller family:

1. keep physical discovery generic and capability-based;
2. implement a new `TerminalProfile` for controller-specific configuration/commands/presentation;
3. pass profile-provided BLE layout/configuration into `BleNusTransport` rather than creating a controller transport;
4. keep `ManagedSession` and agent cursor/event semantics unchanged unless the generic contract itself truly needs to evolve;
5. put project-specific operating and acceptance guidance in a consuming skill, not in the generic agent API;
6. add tests proving both the new profile behavior and continued zero-controller-assumption behavior of `generic`.

If a proposed change requires the generic core to recognize a controller name, advertised-name prefix, alias, command, application identity, or protocol outcome, treat that as an architecture warning: first determine whether the behavior belongs in a profile or a consuming project-specific layer.
