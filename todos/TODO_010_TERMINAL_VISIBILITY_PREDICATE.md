# TODO_010 — Terminal received-line visibility predicate

Status: CLOSED

## Purpose

Remove the unreachable `system_line_prefix` fallback in human-terminal received-line visibility logic without inventing a new cross-stream presentation contract.

## Finding checkpoint

```text
dev@1490078c85bde05ce54ded0c96752ff24d0ca7c1
```

At that checkpoint `_received_line_visible()` first returned true for human-console streams, then had a fallback that again required the same human-console membership together with `system_line_prefix`. The fallback was therefore unreachable and the profile field had no distinct visibility effect.

## Implemented

- Human terminal line visibility is now defined solely by `profile.human_console_streams()`.
- Removed `system_line_prefix` from `TerminalProfile`, `GenericProfile`, and `ChatterProfile`.
- Removed the obsolete Chatter system-prefix export from the profile package.
- Background streams remain transcript-only even when their text resembles `[SYS] ...`; no controller-specific prefix logic was moved into generic transport/session code.
- No externally observable visibility expansion was introduced.

## Validation

Per operator direction, no new dedicated regression test was added for this dead-logic removal. Existing terminal/profile/background-stream tests plus the full repository CI were used as the checkpoint smoke.

```text
accepted checkpoint: dev@a8a6c48b807865713412389bd61e1bb5bfb6f575
GitHub Actions:      34909003012 SUCCESS
compile:             PASS
static/Ruff:         PASS
complexity:          PASS
pytest:              PASS
hardware/manual UI:  NOT RUN
```

## Closure

`CLOSED`: the visibility predicate has one reachable invariant—only profile-declared human-console streams are rendered—and the obsolete prefix field is gone.
