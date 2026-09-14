# TODO_005 — Chatter presentation command/outcome alignment

Status: CLOSED

## Purpose

Keep the human `chatter` profile presentation state aligned with the controller's current local-command and SYSTEM-outcome semantics without moving Chatter protocol knowledge into the generic SerialTerminal core.

## Finding checkpoint

Static source review:

```text
dev@1490078c85bde05ce54ded0c96752ff24d0ca7c1
```

At that checkpoint `/cancel` and `/cancel all` were not classified as Chatter local commands, and queue-full/cancellation SYSTEM outcomes could leave stale human presentation state.

## Implemented

- `/cancel` and `/cancel all` are classified as local Chatter controls and bypass USER/ECHO presentation tracking.
- Queue-full rejection resolves pending human presentation state instead of leaving a stale entry.
- Cancellation outcomes resolve pending presentation through the stable `[SYS] DELIVERY CANCELLED:` prefix; the host does not invent an unverified controller suffix.
- Background telemetry cannot mutate human presentation state merely because its text resembles a console outcome.
- Chatter behavior remains profile-local; generic `ManagedSession`, transports, discovery and JSONL request semantics were not given controller-specific knowledge.
- Human help includes the cancellation controls while retaining the previous help text used by existing callers/tests.

## Validation

The implementation was validated by the existing and added host-side test suite. The first CI attempt exposed one stale help-text assertion; the compatibility help wording was restored and the repeated full CI passed.

```text
accepted checkpoint: dev@4f06f9a21dfd4263a0729e8ade5c58132f8ecdc4
GitHub Actions:      34906863308 SUCCESS
compile:             PASS
static/Ruff:         PASS
complexity:          PASS
pytest:              PASS
hardware:            NOT RUN
```

Physical-node validation was not required to establish this host presentation-state fix and is intentionally not claimed.

## Closure

`CLOSED`: supported Chatter local controls no longer enter payload presentation tracking, queue-full/cancellation outcomes cannot silently leave stale pending state, and profile segregation remains intact.
