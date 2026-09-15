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

## Related live hardware finding

The published BLE smoke run below produced malformed logical lines during a `/help` + `/id` burst:

```text
node_observations@649352f2a53329c4dbed933b586822e306d0916a
runs/RUN_20260914T235131Z_radio-interface-smoke/
SerialTerminal dev@159f7a1ab52fb8f615af33b175545f13e04dd989
```

That run is **not evidence that this TODO's line assembler is the root cause**. Its forensic `RX chat` events already contain missing byte ranges before logical-line assembly. For example, session `s1` receives raw chunks ending with `[SYS]   CHAT       c` and then `show this help\n`, while the complete peer output contains `chat + SYSTEM\n`. Later raw chunks similarly jump from `[SYS]   /cancel all ` directly to `RMINAL MACROS:\n`.

Therefore the burst-loss/corruption investigation is tracked separately as `TODO_024_BLE_BURST_RX_COMPLETENESS.md`. This TODO remains about eliminating the duplicate human parser and aligning semantics; it must not be closed by merely fixing or explaining the BLE burst anomaly.

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
