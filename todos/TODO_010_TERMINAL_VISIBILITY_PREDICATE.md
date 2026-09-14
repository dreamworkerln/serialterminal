# TODO_010 — Terminal received-line visibility predicate

Status: OPEN

## Purpose

Remove or correctly define the currently unreachable `system_line_prefix` fallback in human-terminal received-line visibility logic without inventing a new presentation contract.

## Finding checkpoint

Static source review:

```text
dev@1490078c85bde05ce54ded0c96752ff24d0ca7c1
```

Observed facts at that checkpoint:

`TerminalSession._received_line_visible()` currently has this logical shape:

```text
if stream is a human-console stream:
    return True

return prefix exists
       and stream is a human-console stream
       and line starts with prefix
```

The second branch can never return true because reaching it already means the same stream-membership condition was false. `TerminalProfile.system_line_prefix` therefore has no distinct effect in this predicate.

No user-visible regression is asserted by this finding; it is an internal contract/dead-logic inconsistency that should be resolved deliberately.

## Scope

- human terminal line-visibility predicate;
- intended ownership/use, if any, of `TerminalProfile.system_line_prefix`;
- tests that distinguish human-console streams from background streams.

## Non-goals

- do not make background telemetry visible merely because a line resembles SYSTEM text unless that behavior is explicitly the intended profile contract;
- do not move controller-specific prefix parsing into generic transports or `ManagedSession`;
- no unrelated terminal presentation cleanup.

## Implementation

- [ ] Determine from current profile architecture/tests whether `system_line_prefix` is intended to affect cross-stream visibility or is obsolete in this path.
- [ ] Remove dead/redundant logic or implement the intended generic/profile-configured behavior with a clear invariant.
- [ ] Keep background-stream and human-console-stream ownership explicit.
- [ ] Update architecture/API/operator documentation only if the externally observable visibility contract changes.

## Validation

- [ ] Deterministic tests cover ordinary human-console lines.
- [ ] Deterministic tests cover background-stream lines.
- [ ] If `system_line_prefix` remains meaningful, tests demonstrate a reachable case where it changes the result.
- [ ] If it is removed from this contract, tests/documentation show no behavior regression.
- [ ] Relevant pytest suite PASS.
- [ ] GitHub Actions PASS on the implementation checkpoint.

## Closure criteria

`CLOSED` requires the visibility predicate to contain no unreachable fallback and for the role of `system_line_prefix` to be explicit, tested, and consistent with profile segregation.
