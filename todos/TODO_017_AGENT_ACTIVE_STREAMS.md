# TODO_017 — Expose configured versus active receive streams to agents

Status: OPEN

## Purpose

Let a machine client distinguish profile-configured stream capability from receive streams that are actually subscribed/available on the current transport connection.

## Finding checkpoint

```text
dev@159f7a1ab52fb8f615af33b175545f13e04dd989
```

`BleNusTransport` already distinguishes:

```text
stream_capabilities  -> configured stream names
available_streams    -> subscriptions successfully active on this connection
```

Optional receive-stream subscription failure is tolerated so a connection can remain usable with fewer active streams. `SessionManager.open()` and `status()` currently return only `transport.stream_capabilities` as `streams`.

For Chatter this can report `chat` and `telemetry` even when optional telemetry notification subscription failed. An autonomous agent then has no structured way to know whether a silent telemetry stream is absent or simply produced no data.

## Target behavior

- Define API fields/semantics for configured stream capability versus currently active streams.
- `status` must reflect active-stream changes across disconnect/reconnect.
- Optional subscription failure must be observable without turning an otherwise usable connection into a hard failure.
- Generic API stays profile-agnostic: it reports stream names/state, not Chatter-specific meaning.
- Consuming skills may require an active stream when a scenario depends on it.

## Validation

- [ ] generic standard-NUS connected case reports the expected active stream;
- [ ] Chatter optional telemetry subscribe failure is visible in agent status/open result;
- [ ] reconnect can update active-stream state without changing configured capability;
- [ ] `AGENT_API.md` and generic skill define the fields precisely;
- [ ] node skill explains what to do when a required scenario stream is inactive;
- [ ] full repository CI PASS.