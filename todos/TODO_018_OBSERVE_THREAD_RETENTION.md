# TODO_018 — Bound JSONL observe thread lifecycle

Status: CLOSED

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

- [x] stress test 1000 sequential short observes and prove worker bookkeeping returns to zero;
- [x] multiple simultaneous observes still work;
- [x] request-ID reuse is allowed only after prior completion;
- [x] EOF cancellation returns correlated shutdown responses and leaves no live observe workers;
- [x] full repository CI PASS.

## Result

Implementation:

```text
dev@dd9856bd540f66c8ca601cc92688a9539a1e0002
```

The JSONL runner now tracks only active asynchronous `observe` / `sweep_observe`
workers in a set. Each completed worker removes itself together with its pending request
ID bookkeeping. Shutdown snapshots and joins only workers that are still active.

Regression coverage submits 1000 sequential short asynchronous observations and
requires worker bookkeeping to return to zero while the existing concurrent-observe,
request-ID and EOF-shutdown tests remain passing.

Validated together with the reopened TODO_028 correction at:

```text
dev@4792fc2bdc357ce3eaee2755ccfb39fa4144a855
GitHub Actions 36314768924 SUCCESS
compile PASS
ruff PASS
complexity step PASS
pytest 222 passed
```

Status: CLOSED