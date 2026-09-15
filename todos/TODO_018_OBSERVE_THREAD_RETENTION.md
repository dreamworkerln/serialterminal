# TODO_018 — Bound JSONL observe thread lifecycle

Status: OPEN

## Purpose

Prevent the recommended continuous-observe workflow from retaining an unbounded history of completed Python `Thread` objects for the lifetime of one agent process.

## Finding checkpoint

```text
dev@159f7a1ab52fb8f615af33b175545f13e04dd989
```

The JSONL runner stores every asynchronous observe worker in `_observe_threads`. Each `observe` appends a new thread, but completed workers are not removed or pruned. Shutdown joins the entire historical list.

`AGENT_API.md` and the generic agent skill explicitly recommend issuing a new `observe` after every completed response and keeping one long-lived agent process for large scenarios. A sufficiently long autonomous run therefore accumulates thread objects even though only a small number of observations are active at once.

## Target behavior

- Retain only active/pending observe workers or otherwise bound completed-worker bookkeeping.
- Preserve concurrent observations with distinct request IDs.
- Preserve `request_id_busy` until the corresponding observation actually finishes.
- Shutdown must cancel and join every active observation without depending on an unbounded historical list.
- No unsolicited output or response-order contract changes.

## Validation

- [ ] stress test hundreds/thousands of sequential short observes and prove worker bookkeeping remains bounded;
- [ ] multiple simultaneous observes still work;
- [ ] request-ID reuse is allowed only after prior completion;
- [ ] EOF cancellation returns correlated shutdown responses and leaves no live observe workers;
- [ ] full repository CI PASS.