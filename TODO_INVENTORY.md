# TODO inventory

This file is the authoritative current-state index for engineering TODOs in this project.

## Active

No active engineering TODOs.

The next validation phase is intentionally consolidated rather than duplicating manual UI checks after every small host change: existing repository CI remains the per-change smoke gate, while node/firmware behavior should be exercised through a larger autonomous agent/API scenario run where possible. Manual terminal/hotkey checks are reserved for behavior that cannot be established through the machine interface or automated host tests.

The active project-specific node/hardware guidance is `.agents/skills/node-agent/SKILL.md`. `AGENT_API.md` remains the canonical generic SerialTerminal JSONL contract.

## Closed

### TODO_010 — `todos/TODO_010_TERMINAL_VISIBILITY_PREDICATE.md`

Status: CLOSED

Goal: remove the unreachable terminal `system_line_prefix` visibility fallback and keep stream visibility explicitly owned by profiles.

```text
implementation checkpoint: dev@a8a6c48b807865713412389bd61e1bb5bfb6f575
implementation CI:         34909003012 SUCCESS
regression checkpoint:     dev@9d9525dc0a0563bff47a6e903c4c39d8aebe91d6
regression CI:             34909632781 SUCCESS
manual/hardware:           NOT RUN
agent/node scenarios:      NOT RUN
```

Dedicated host-side regression tests now cover ordinary and `[SYS]`-like text on both human-console and background streams, including transcript-only behavior for background SYSTEM-like lines. These tests run automatically in the normal GitHub Actions pytest stage.

### TODO_009 — `todos/TODO_009_BLE_RX_CHUNK_ORDERING.md`

Status: CLOSED

Goal: preserve arrival order when an oversized BLE notification is split by `read_chunk(size)`.

```text
accepted checkpoint: dev@69cc1e4157471f69718dbb9fbb46ef5b8d945ab7
GitHub Actions:      34908096672 SUCCESS
hardware:            NOT RUN
```

### TODO_008 — `todos/TODO_008_BLE_WRITE_TIMEOUT_AMBIGUITY.md`

Status: CLOSED

Goal: make timed-out BLE write ownership explicit so a possibly-late GATT side effect is not silently treated as a definite failure followed by automatic duplicate retry.

```text
accepted checkpoint: dev@441fc99d3f123e9133253c820f59f54e37d23f88
GitHub Actions:      34907924472 SUCCESS
hardware:            NOT RUN
```

Selected contract: BLE write timeout may produce `tx_state="unknown"`; that TX is not automatically retried. Ordinary definite transport failures retain reconnect-safe retry.

### TODO_007 — `todos/TODO_007_FORENSIC_LOG_CURSOR_GAPS.md`

Status: CLOSED

Goal: ensure bounded event retention cannot produce a silently incomplete persisted forensic log.

```text
accepted checkpoint: dev@4182390d73d9a8a5d02c6fd9b6b601e40fb5ae63
GitHub Actions:      34907393048 SUCCESS
hardware:            NOT RUN
```

Persisted event sequence discontinuities now emit an explicit `forensic_gap` error record with the lost sequence range.

### TODO_006 — `todos/TODO_006_BLE_CAPABILITY_CACHE_UNKNOWN.md`

Status: CLOSED

Goal: preserve prior definitive BLE NUS capability across a transient UNKNOWN probe while keeping newest diagnostics truthful.

```text
accepted checkpoint: dev@522180cf92d573a51020eeb6e84c2edb528ad5d3
GitHub Actions:      34907044192 SUCCESS
hardware:            NOT RUN
```

### TODO_005 — `todos/TODO_005_CHATTER_PRESENTATION_OUTCOMES.md`

Status: CLOSED

Goal: align Chatter human presentation with current local-command and SYSTEM-outcome behavior so supported controls are not tracked as payloads and rejection/cancellation cannot leave stale pending state.

```text
accepted checkpoint: dev@4f06f9a21dfd4263a0729e8ade5c58132f8ecdc4
GitHub Actions:      34906863308 SUCCESS
hardware:            NOT RUN
```

### TODO_004 — `todos/TODO_004_NODE_RUN_BUNDLES.md`

Status: CLOSED

Goal: automate complete hardware-run publication so a reviewer can fetch the curated report, exact SerialTerminal forensic log, human-console companion log, manifest, and optional observation directly from GitHub.

```text
accepted implementation/static checkpoint:
  dev@4d50eb1aec50bfb4a71d1d8e63f95fbc7a0f436c
  GitHub Actions 34263084088 SUCCESS

recorded-observation hardware publication:
  SerialTerminal dev@c9c6d4099c3532494bac8bfecb9fead37e27fe1e
  node_observations@f5020fd63e3cfdcf45244ff2dd6b0d86b963d7a0
  result INCONCLUSIVE; publication path PASS

RUN-only hardware publication:
  SerialTerminal dev@c9c6d4099c3532494bac8bfecb9fead37e27fe1e
  node_observations@b22ee446d96e9fa9047d52f4d309830fca688893
  result PASS; A->B PASS; B->A PASS; BLE stability PASS
```

Future hardware evidence continues under `NODE_OBSERVATION_RECORDING_POLICY.md` and `.agents/skills/node-agent/SKILL.md`.

### TODO_003 — `todos/TODO_003_AGENT_CODE_QUALITY.md`

Status: CLOSED

Goal: reduce accidental complexity in agent receive/wait orchestration, JSON dispatch, and JSONL runner lifecycle without changing the documented machine API.

```text
accepted checkpoint: dev@a74b46585b3f2c0e032b6b444b2d1089b4fde1e9
GitHub Actions:      33785730259 SUCCESS
```

### TODO_002 — `todos/TODO_002_AGENT_EVENT_WAIT.md`

Status: CLOSED

Goal: provide multi-session asynchronous receive waiting while ordinary JSONL commands continue and responses remain correlated by request ID.

The historical `wait_events` operation was later superseded by canonical `observe`; current machine clients must follow `AGENT_API.md`.

```text
accepted historical checkpoint: dev@aaeab3002e60bd1e85595d73e3248d42c3141c1f
GitHub Actions:              33782252791 SUCCESS
post-closure physical smoke: PASS / two BLE nodes / 2026-09-03
```

### TODO_001 — `todos/TODO_001_AGENT_INTERFACE.md`

Status: CLOSED

Goal: provide a generic machine-facing interface over shared SerialTerminal session/transport logic without duplicating Serial/BLE/SPP implementations or changing normal human-console ownership.

```text
accepted documented checkpoint: dev@396f499305c7ab1c425483b5a5f10e8521125f4f
GitHub Actions:               33764159009 SUCCESS
post-closure hardware smoke:  PASS / physical BLE multi-device / 2026-09-03
```

## Current validation posture

Repository CI is the normal per-change clean-environment gate. Physical-node claims remain separate: do not infer current-head hardware validity from older run bundles. For the next build-level validation pass, prefer one long-lived `serialterminal agent` process and a broad scenario matrix over repeated manual operator actions; only UI-specific behavior that the machine API cannot exercise should require a separate human pass.
