# SerialTerminal logging contract

This document defines the generic logging roles shared by the human terminal and the machine-facing agent.

## Paired paths

A normal run uses one basename and two files:

```text
<name>.log
<name>.console.log
```

With the default unique name:

```text
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.log
logs/serialterminal-YYYYMMDD-HHMMSS-ffffff-pPID.console.log
```

If `--log <path>` is supplied, that path names the primary `.log`; the companion path is derived by replacing a final `.log` with `.console.log` or appending `.console.log` otherwise.

## Primary `.log` roles

The primary file is frontend-specific and its role must not be inferred from the extension alone.

Human terminal:

```text
.log = compatibility transcript
```

It preserves terminal-local status text, accepted typed input and received transport text using the existing transcript behavior. It is useful for operator review but is not the agent forensic event record.

Agent:

```text
.log = forensic/API/transport record
```

It contains timestamped `[RUN]`, `[AGENT]`, request/response, state, TX, raw RX and error records. Raw RX preserves transport chunk boundaries and byte-accurate `data_b64`. Persisted sequence gaps remain explicit through `forensic_gap`.

Do not replace the agent forensic log with the human transcript format.

## Shared `.console.log`

Both frontends create a companion human-console audit view with the same physical record shape:

```text
2026-09-22T15:58:21.123+03:00 [s1] [I] /id
2026-09-22T15:58:21.287+03:00 [s1] [O] READY
```

Fields:

```text
timestamp  offset-aware host wall clock, ISO 8601, millisecond precision
session    process-local logical session token
[I]        one line queued through the frontend line-send path
[O]        one completed logical line from a profile human-console stream
```

The interactive frontend owns one logical managed session and uses `s1`. Agent mode uses its normal `s1`, `s2`, ... session identifiers.

A console record is one physical logfile line. Embedded CR/LF characters in input text are escaped as `\r` and `\n`.

The companion view is presentation/audit convenience, not transport or peer-delivery proof. `[I]` does not mean that the peer received or accepted the line.

## Receive-line semantics

`[O]` uses the canonical completed logical lines assembled by `ManagedSession`, with the receive-event timestamp that terminated the line.

Only streams declared as human-console streams by the selected profile are included.

Examples:

```text
generic BLE: main
Chatter BLE: chat
```

Background streams such as Chatter machine telemetry remain outside `.console.log`. In agent mode they remain available in the forensic `.log` and raw `observe.result.events`; in human mode the compatibility transcript keeps its existing receive/transcript behavior.

## Lifecycle and compatibility

The human transcript format remains available in its primary `.log` so existing operator workflows are not broken.

The agent forensic format and `forensic_gap` semantics remain unchanged.

The shared companion exists to give human and agent runs a comparable timestamped logical timeline without pretending that a presentation log is raw forensic evidence.
