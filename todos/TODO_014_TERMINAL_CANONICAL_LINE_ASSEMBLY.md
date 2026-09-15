# TODO_014 — One canonical logical-line assembler for human and agent paths

Status: OPEN

## Purpose

Make the human terminal consume the same canonical logical-line semantics owned by `ManagedSession` instead of maintaining a second independent line parser for presentation decisions.

## Finding checkpoint

```text
dev@159f7a1ab52fb8f615af33b175545f13e04dd989
```

Architecture and `AGENT_API.md` define `ManagedSession` as the single owner of canonical per-stream logical-line assembly. The human `TerminalSession.write_received()` still keeps its own incremental UTF-8 decoders and per-stream buffers and uses `str.splitlines(keepends=True)`.

Those parsers are not semantically identical: canonical `ManagedSession` completes lines only on LF and removes a CR only immediately before LF, while Python `splitlines()` recognizes additional boundaries such as bare CR and several Unicode separators. Human presentation/outcome tracking can therefore react to a different logical boundary than `observe.result.lines` and the companion line model.

This is an architecture/consistency finding; no current hardware failure is claimed.

## Target behavior

- One canonical line-assembly implementation owns stream UTF-8 state, LF termination, CRLF normalization, lifecycle reset and seq boundaries.
- Human Chatter presentation consumes canonical completed line records or a shared generic line-assembly primitive, not a semantically different `splitlines()` implementation.
- Raw human transcript may remain raw/chunk-preserving where required, but controller outcome interpretation must use canonical line semantics.
- Connection boundaries must continue preventing incomplete text from joining across reconnect.

## Validation

- [ ] bare CR does not become a canonical completed line unless the chosen contract explicitly changes;
- [ ] Unicode line-separator characters do not create frontend-only boundaries;
- [ ] CRLF and empty-line behavior matches `ManagedSession`;
- [ ] split UTF-8 across chunks remains correct per stream;
- [ ] disconnect/reconnect clears incomplete state exactly once;
- [ ] human presentation and agent logical-line tests share the same expected semantics;
- [ ] full repository CI PASS.