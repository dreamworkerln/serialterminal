# TODO_007 — Forensic agent log cursor-gap integrity

Status: CLOSED

## Purpose

Ensure the agent forensic log cannot silently omit retained session events while still appearing to be a complete source of transport/API truth.

## Finding checkpoint

```text
dev@1490078c85bde05ce54ded0c96752ff24d0ca7c1
```

At that checkpoint `SessionCursorExpired` in the companion event-logger path advanced directly to the oldest retained event without recording that earlier session events had been lost.

## Implemented

- `RunLog` tracks the last persisted raw event sequence independently for each session.
- If the next forensic event sequence skips forward, the logger writes an `[ERROR]` record with `event="forensic_gap"` before the next retained event.
- The marker records `session`, `last_logged_seq`, `next_logged_seq`, `lost_seq_first`, and `lost_seq_last`.
- Normal `[STATE]`, `[TX]`, `[RX <stream>]`, and `[ERROR]` records remain unchanged when sequences are contiguous.
- Public `observe` cursor-expiry semantics and bounded `ManagedSession` retention are unchanged.

A forensic log may therefore still contain a retention gap under extreme logger lag, but it can no longer present that gap as silent completeness.

## Validation

A deterministic small-ring test forces an overrun and verifies that `forensic_gap` is persisted before the first retained event; contiguous-event logging remains gap-free.

```text
accepted checkpoint: dev@4182390d73d9a8a5d02c6fd9b6b601e40fb5ae63
GitHub Actions:      34907393048 SUCCESS
compile:             PASS
static/Ruff:         PASS
complexity:          PASS
pytest:              PASS
hardware:            NOT RUN
```

## Closure

`CLOSED`: persisted forensic event loss is explicitly detectable and range-accounted instead of silently omitted.
