# TODO_005 — Chatter presentation command/outcome alignment

Status: OPEN

## Purpose

Keep the human `chatter` profile presentation state aligned with the controller's current local-command and SYSTEM-outcome semantics without moving Chatter protocol knowledge into the generic SerialTerminal core.

## Finding checkpoint

Static source review:

```text
dev@1490078c85bde05ce54ded0c96752ff24d0ca7c1
```

Observed facts at that checkpoint:

- `CHATTER_TEXT_COMMANDS` recognizes `/help`, `/id`, `/chat`, `/tele`, `/both`, `/echo`, and `/reboot`, but does not recognize `/cancel` or `/cancel all`;
- `TerminalSession._submit_interactive_line()` routes any non-empty unrecognized line through `ChatterPresentation.submit_payload()` before transport queueing;
- the presentation failure resolver does not currently include queue-full or cancellation SYSTEM outcomes;
- therefore a supported Chatter control can be tracked as if it were a USER/ECHO payload, and a rejected/cancelled item can leave stale presentation state until a later unrelated resolution or disconnect.

This is a human-frontend/profile issue. The JSONL agent path does not use `ChatterPresentation` for request semantics.

## Scope

- Chatter text-command classification used by the human frontend;
- Chatter presentation pending-state resolution for currently supported controller outcomes;
- deterministic regression coverage for local commands, queue-full rejection, and cancellation presentation behavior;
- consistency review against current authoritative Chatter firmware/docs before implementation.

## Non-goals

- no firmware behavior change;
- no generic agent API change;
- no Chatter command knowledge in `ManagedSession`, generic transports, or generic discovery;
- no inference that a transport `written` event means RF delivery.

## Implementation

- [ ] Re-read the current authoritative Chatter command/outcome contract before editing code.
- [ ] Ensure every supported local text control, including `/cancel` and `/cancel all` if still authoritative, is classified as a command rather than a presentation payload.
- [ ] Define presentation handling for queue-full and cancellation outcomes so pending human presentation state cannot remain stale.
- [ ] Preserve the distinction between an in-flight USER already physically transmitted and a queued unsent USER cancelled before TX.
- [ ] Keep background telemetry unable to resolve or mutate human presentation state merely because text resembles a human-console outcome.
- [ ] Review affected operator/help documentation and Chatter skill guidance for consistency; update only if behavior/documentation actually becomes inaccurate.

## Validation

- [ ] Deterministic tests cover command boundary trimming for `/cancel` and `/cancel all`.
- [ ] Deterministic tests cover queue-full rejection without leaving a stale pending presentation entry.
- [ ] Deterministic tests cover both cancellation shapes that the authoritative firmware exposes.
- [ ] Existing success, duplicate-payload, disconnect, and background-telemetry presentation tests remain PASS.
- [ ] Relevant pytest suite PASS.
- [ ] GitHub Actions PASS on the implementation checkpoint.

## Closure criteria

`CLOSED` requires all currently supported Chatter local controls to bypass USER/ECHO presentation tracking, all authoritative rejection/cancellation outcomes to leave presentation state coherent, regression tests to cover the cases above, and profile segregation to remain intact.
