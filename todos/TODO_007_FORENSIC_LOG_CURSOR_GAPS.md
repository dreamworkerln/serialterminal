# TODO_007 — Forensic agent log cursor-gap integrity

Status: OPEN

## Purpose

Ensure the agent forensic log cannot silently omit retained session events while still appearing to be a complete source of transport/API truth.

## Finding checkpoint

Static source review:

```text
dev@1490078c85bde05ce54ded0c96752ff24d0ca7c1
```

Observed facts at that checkpoint:

- `ManagedSession` keeps a bounded raw event ring, default `event_limit=4096`;
- the agent event-logger thread consumes that ring by cursor through `events_after()`;
- when `SessionCursorExpired` is raised, `_event_logger_loop()` advances its cursor to `oldest_seq - 1` and continues;
- no explicit gap/loss record is written before continuing;
- project policy and `AGENT_API.md` treat the main agent log as forensic/API/transport truth.

Consequence: under sufficient logger lag/event volume, old events may be omitted from the persisted forensic log without an explicit indication that a gap occurred.

## Scope

- generic agent event logging and its relationship to bounded `ManagedSession` retention;
- loss detection/representation for the persisted forensic logfile;
- shutdown/flush behavior needed to keep the log's completeness claim honest.

## Non-goals

- no change to public `observe` cursor-expiry semantics unless independently required;
- no controller-specific behavior;
- no silent increase of retention as the sole correctness fix without proving it eliminates the failure mode.

## Implementation

- [ ] Choose a generic mechanism that makes persisted event loss impossible or explicitly detectable.
- [ ] If bounded retention can still overrun the logger, persist an unambiguous gap/error record with the lost cursor range or equivalent loss metadata.
- [ ] Ensure a run cannot present a gap-containing forensic log as silently complete.
- [ ] Preserve event ordering and current `[STATE]` / `[TX]` / `[RX <stream>]` / `[ERROR]` semantics for non-gap operation.
- [ ] Review `AGENT_API.md`, recording policy, and generic agent skill wording if the forensic-log completeness contract changes.

## Validation

- [ ] Deterministic regression test forces logger lag/retention expiry using a small event limit or controlled logger delay.
- [ ] Test proves the resulting log has no silent hole: either every event is persisted or an explicit loss marker is persisted.
- [ ] Normal logging-order tests remain PASS.
- [ ] Shutdown flush/cancel tests remain PASS.
- [ ] Relevant pytest suite PASS.
- [ ] GitHub Actions PASS on the implementation checkpoint.

## Closure criteria

`CLOSED` requires deterministic proof that event-ring overrun cannot produce a silently incomplete forensic log, plus documentation that accurately describes the resulting integrity contract.
