# TODO_015 — Clarify profile connect-preamble scope across frontends

Status: OPEN

## Purpose

Resolve the ownership mismatch between the architecture rule that a `TerminalProfile` owns connect/reconnect preamble behavior and the human frontend's transport-specific suppression of that preamble.

## Finding checkpoint

```text
dev@159f7a1ab52fb8f615af33b175545f13e04dd989
```

Current behavior is intentionally documented but architecturally split:

- agent `profile:"chatter"` applies the profile `/id` preamble on each supported transport connect/reconnect;
- human `TerminalSession._human_connect_preamble()` applies the selected profile preamble only when the concrete transport is `SerialTransport`, suppressing it for BLE/SPP;
- `ARCHITECTURE.md` says connect/reconnect preamble actions belong to `TerminalProfile` and frontends should not recreate controller semantics outside the selected profile.

The desired user-visible behavior is not changed by this TODO. The inconsistency needs an explicit design decision rather than an accidental frontend type check.

## Target behavior

Choose and document one of these architecture-consistent directions:

- encode transport/frontend applicability as generic profile-provided policy/data; or
- deliberately relax the architecture contract and document why frontend-specific preamble scope is an allowed exception.

Whichever direction is selected:

- generic core remains controller-agnostic;
- transport modules do not import concrete controller profiles;
- human and agent behavior is explicit, tested and documented;
- no compatibility behavior is changed silently.

## Validation

- [ ] dependency direction reviewed against `ARCHITECTURE.md`;
- [ ] human Serial/BLE/SPP preamble behavior covered by tests;
- [ ] agent Serial/BLE/SPP preamble behavior covered by tests;
- [ ] README, `AGENT_API.md`, generic skill and profile docs agree;
- [ ] full repository CI PASS.