# Reduce agent context/token amplification TODO

TODO-ID: TODO_027
Status: IMPLEMENTED / CLEAN CI OPEN

## Purpose

Снизить model-context и token amplification в long-lived SerialTerminal agent runs без потери forensic evidence и без изменения cursor/session semantics.

## Trigger

A physical two-node CANONICAL_RUN on 2026-09-23 completed correctly but consumed about:

```text
total tokens:   97,954
input tokens:   90,854
cached input: 1,138,432
reasoning:        1,096
```

The low reasoning count versus very high repeated input showed that response/log replay, not task complexity, dominated model traffic.

The largest API-level amplifier was `observe`: every ordinary logical-line poll also serialized all raw `SessionEvent` objects, including chunk metadata and `data_b64`, even when the consumer only needed `result.lines`.

## Selected contract

Default:

```json
{"id":20,"op":"observe","cursors":{"s1":42},"timeout_ms":1000}
```

returns:

```text
lines
cursors
timed_out
```

Raw transport events are explicit opt-in:

```json
{"id":21,"op":"observe","cursors":{"s1":42},"timeout_ms":1000,"include_events":true}
```

Only the opt-in response contains `result.events`.

## Invariants

- observe remains event-cursor based;
- raw activity still wakes a pending observe even when no complete line exists;
- cursors advance exactly as before;
- a line begun before the input cursor can still be returned complete when its terminating event is after the cursor;
- `include_events:true` preserves exact raw event schema including `data_b64`;
- forensic `.log` records raw state/TX/RX events independently of response projection;
- `forensic_gap` semantics are unchanged;
- no BLE/Serial/SPP transport behavior changes.

## Implementation

- [x] make `observe.result.events` opt-in through boolean `include_events`;
- [x] default `observe` response to logical lines + cursors + timeout state;
- [x] preserve raw forensic logging independently;
- [x] document default logical consumption and forensic opt-in;
- [x] document no accumulated stdout replay after already-consumed responses;
- [x] document targeted finalized-log inspection instead of whole-log replay;
- [x] add regression tests for default/opt-in/cursor/partial-line behavior;
- [x] add payload-amplification regression coverage.

## Measurement

A deterministic burst regression fixture compares the serialized default response with the same cursor range requested using `include_events:true`.

Acceptance:

```text
same lines
same cursors
65 raw events available with opt-in
default response < one third of opt-in response size
```

A second retrospective measurement will be recorded after implementation against the previously captured two-node diagnostic observe responses.

## Validation

- [ ] targeted agent tests PASS;
- [ ] full pytest PASS;
- [ ] compile PASS;
- [ ] static analysis PASS;
- [ ] BASE..HEAD diff/deletions/function-definition gate PASS;
- [ ] GitHub Actions PASS;
- [ ] observation-workspace hardware skill aligned with new default consumption rule.

## Result

Implementation checkpoint: pending.

Clean CI: pending.

Status: IMPLEMENTED / CLEAN CI OPEN.
