# TODO_019 — Strict structured validation for JSONL request fields

Status: OPEN

## Purpose

Make malformed machine requests fail with deterministic documented structured errors instead of Python coercion, truncation, or generic `internal_error` paths.

## Finding checkpoint

```text
dev@159f7a1ab52fb8f615af33b175545f13e04dd989
```

Current handlers validate some fields carefully but coerce others:

- `discover` eventually applies `int(baud)` / `float(scan_seconds)` without a protocol-level typed validation contract;
- `open` calls `int(wait_connected_ms)` before `SessionManager.open()`, so strings are accepted, floats are truncated, and malformed values can escape as generic failures;
- `observe` catches conversion errors for `timeout_ms` but still uses `int(...)`, accepting numeric strings and truncating floats despite documenting an integer field;
- invalid selector scope may surface from lower-level constructor validation rather than a dedicated request error.

JSON boolean values also require deliberate handling because Python `bool` is an `int` subclass.

## Target behavior

- Define exact JSON types and ranges for every operation field in `AGENT_API.md`.
- Reject wrong types rather than silently coercing/truncating them unless coercion is explicitly part of the API.
- Reject booleans where numeric values are required.
- Map invalid values to stable structured error codes/messages/details at the protocol boundary.
- Lower-level `ValueError`/`TypeError` caused by user request shape must not become `internal_error`.
- Preserve compatibility for valid requests.

## Validation

- [ ] table-driven malformed-request tests for every operation;
- [ ] numeric string, float, bool, null, negative and overflow/unsupported values covered where applicable;
- [ ] invalid `scope`, `profile`, `eol`, cursor and base64 remain deterministic;
- [ ] valid integer timeouts retain current semantics;
- [ ] `AGENT_API.md` request field types/errors synchronized;
- [ ] full repository CI PASS.