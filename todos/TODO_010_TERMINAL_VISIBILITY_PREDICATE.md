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

The implementation checkpoint first passed the existing terminal/profile/background-stream suite and full repository CI. Dedicated host-side regression coverage was then added in `tests/test_terminal_visibility.py` and is run automatically by the normal GitHub Actions pytest stage.

The dedicated regression coverage proves:

- a profile-declared human-console stream remains visible for both ordinary and `[SYS]`-like text;
- a background stream remains hidden for both ordinary and `[SYS]`-like text;
- `write_received()` keeps background `[SYS]` text transcript-only while rendering the same class of text from a human-console stream.

```text
implementation checkpoint: dev@a8a6c48b807865713412389bd61e1bb5bfb6f575
implementation CI:         34909003012 SUCCESS
regression checkpoint:     dev@9d9525dc0a0563bff47a6e903c4c39d8aebe91d6
regression CI:             34909632781 SUCCESS
compile:                   PASS
static/Ruff:               PASS
complexity:                PASS
pytest:                    PASS
hardware/manual UI:        NOT RUN / not required for these host-side tests
agent/node scenarios:      NOT RUN / intentionally deferred
```

## Closure

`CLOSED`: the visibility predicate has one reachable invariant—only profile-declared human-console streams are rendered—and that invariant now has dedicated automated regression coverage in the GitHub Actions pipeline.
