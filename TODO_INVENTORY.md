# TODO inventory

This file is the authoritative current-state index for engineering TODOs in this project.

## Active

### TODO_011 — `todos/TODO_011_CHATTER_PRESENTATION_CORRELATION.md`

Status: OPEN

Goal: make Chatter human presentation correlate queue-full and cancellation outcomes with the correct one or many pending submissions instead of resolving one FIFO item for every failure-like line.

Finding checkpoint: `dev@159f7a1ab52fb8f615af33b175545f13e04dd989`.

### TODO_012 — `todos/TODO_012_SPP_CAPABILITY_CACHE_UNKNOWN.md`

Status: OPEN

Goal: preserve prior definitive SPP capability and RFCOMM channel across a transient UNKNOWN probe while retaining truthful newest probe diagnostics.

Finding checkpoint: `dev@159f7a1ab52fb8f615af33b175545f13e04dd989`.

### TODO_013 — `todos/TODO_013_SERIAL_SPP_WRITE_AMBIGUITY.md`

Status: OPEN

Goal: prevent reconnect-safe automatic retry from blindly repeating Serial/SPP writes whose side effects may already have partially occurred.

Finding checkpoint: `dev@159f7a1ab52fb8f615af33b175545f13e04dd989`; static semantic risk, no physical duplicate claimed.

### TODO_014 — `todos/TODO_014_TERMINAL_CANONICAL_LINE_ASSEMBLY.md`

Status: OPEN

Goal: remove the human frontend's semantically different line parser so controller/presentation reasoning uses the same canonical logical-line semantics as `ManagedSession`.

Finding checkpoint: `dev@159f7a1ab52fb8f615af33b175545f13e04dd989`. The later BLE burst anomaly is tracked separately in `TODO_024`: its raw `RX chat` evidence already contains missing byte ranges, so it must not be misattributed to this line-assembly cleanup.

### TODO_015 — `todos/TODO_015_PROFILE_PREAMBLE_SCOPE.md`

Status: OPEN

Goal: resolve the architecture mismatch between profile-owned connect preamble semantics and the human frontend's concrete-transport-specific preamble suppression.

Finding checkpoint: `dev@159f7a1ab52fb8f615af33b175545f13e04dd989`; design/ownership ambiguity, no behavior change selected yet.

### TODO_016 — `todos/TODO_016_BLE_RX_LIFECYCLE_BOUNDARY.md`

Status: OPEN

Goal: prevent BLE RX bytes buffered under one connection generation from being silently delivered across a disconnect/reconnect lifecycle boundary.

Finding checkpoint: `dev@159f7a1ab52fb8f615af33b175545f13e04dd989`; static lifecycle risk.

### TODO_017 — `todos/TODO_017_AGENT_ACTIVE_STREAMS.md`

Status: OPEN

Goal: expose configured versus actually active receive streams so an agent can detect optional subscription loss instead of treating silence as evidence.

Finding checkpoint: `dev@159f7a1ab52fb8f615af33b175545f13e04dd989`.

### TODO_018 — `todos/TODO_018_OBSERVE_THREAD_RETENTION.md`

Status: OPEN

Goal: keep long-lived continuous-observe agent runs from retaining an unbounded history of completed observe thread objects.

Finding checkpoint: `dev@159f7a1ab52fb8f615af33b175545f13e04dd989`.

### TODO_019 — `todos/TODO_019_AGENT_REQUEST_VALIDATION.md`

Status: OPEN

Goal: make JSONL request field types/ranges strict and deterministic instead of relying on Python coercion/truncation or leaking malformed input into generic internal errors.

Finding checkpoint: `dev@159f7a1ab52fb8f615af33b175545f13e04dd989`.

### TODO_020 — `todos/TODO_020_AGENT_SCANNER_WORKFLOW_DOCS.md`

Status: OPEN

Goal: document an exact non-interactive scanner/prober recovery workflow for autonomous agents and surface critical `unknown` TX / forensic-gap semantics in the agent overview.

Finding checkpoint: `dev@159f7a1ab52fb8f615af33b175545f13e04dd989`.

### TODO_021 — `todos/TODO_021_NODE_EXECUTOR_PROVENANCE_BOUNDARY.md`

Status: PARTIAL

Goal: keep physical-node execution separate from source/history/provenance selection, prohibit flashing in ordinary node validation, and forbid inferred deployed firmware revisions.

Finding checkpoint: `dev@159f7a1ab52fb8f615af33b175545f13e04dd989`.

Partial implementation: root delegation rules added at `dev@37925c48b6646c3e70d0f11e9a47abda5e9b357e`; node-skill/policy alignment remains open. Live run `node_observations@649352f2a53329c4dbed933b586822e306d0916a` correctly used `Firmware: unknown` but still discussed source-SHA workspace availability, reinforcing the remaining executor/provenance boundary work.

### TODO_022 — `todos/TODO_022_BLE_CONNECT_TIMEOUT_OWNERSHIP.md`

Status: OPEN

Goal: ensure a timed-out BLE connect coroutine is cancelled/retired or otherwise prevented from overlapping later reconnect attempts.

Finding checkpoint: `dev@159f7a1ab52fb8f615af33b175545f13e04dd989`; static lifecycle risk.

### TODO_023 — `todos/TODO_023_DEVICE_CACHE_CONCURRENT_WRITERS.md`

Status: OPEN

Goal: make capability-cache read-modify-write safe across concurrent SerialTerminal/scanner processes without lost updates or shared-temp-file races.

Finding checkpoint: `dev@159f7a1ab52fb8f615af33b175545f13e04dd989`; static concurrency risk.

### TODO_024 — `todos/TODO_024_BLE_BURST_RX_COMPLETENESS.md`

Status: PARTIAL

Goal: isolate the byte-loss boundary seen during high-rate BLE `/help` + `/id` output, where exact raw `RX chat` / `data_b64` evidence already contains missing byte ranges before canonical logical-line assembly.

Initial live finding: `node_observations@649352f2a53329c4dbed933b586822e306d0916a`, run `RUN_20260914T235131Z_radio-interface-smoke`, using SerialTerminal `dev@159f7a1ab52fb8f615af33b175545f13e04dd989`.

Host-side isolation: a deterministic 1001-callback / 10005-byte burst test proves exact byte/order preservation from the SerialTerminal Bleak notification callback through `_queue_notify`, `read_chunk` and `ManagedSession` raw events. Test introduced at `dev@a8b6c1974242df0bb267fa7156c704f8aeb0f6c0`; validated tree `dev@bb48db1709ab66df3f4492f25a51b997fe23c357`, GitHub Actions `34992221772` SUCCESS.

Controlled physical reproduction: `node_observations@ccab9e37747c564c5f238cf6e5eef83fd8760ea1`, run `RUN_20260915T170402Z_ble-burst-rx-completeness-take2`, SerialTerminal `dev@276aeee2ca90e6ee964120153bf72e5dbafcf307`, result INCONCLUSIVE. Isolated `/help` was already malformed on one node; concurrent `/help` produced `10/10` malformed/baseline-inconclusive session-cases and `/help` + `/id` produced `10/10`, with no `forensic_gap` and no disconnect/reconnect in affected intervals.

Next boundary test: capture a controlled reproduction with exact Linux HCI/BlueZ evidence (for example `btmon`) in parallel with SerialTerminal raw events, persist the exact HCI capture as an optional same-RUN artifact, and compare the first missing SerialTerminal byte range against the corresponding HCI/ATT notification sequence. `btmon` is opt-in diagnostic instrumentation for this scenario, not an automatic part of ordinary hardware runs.

Impact: low-rate radio evidence can still be usable when its required exact evidence is complete, but high-rate/burst BLE human-console output must not be assumed lossless until the first proven physical loss boundary is isolated.

### TODO_025 — `todos/TODO_025_MATERIAL_FOLLOWUP_EVIDENCE.md`

Status: PARTIAL

Goal: keep materially used follow-up/control evidence reviewable while allowing non-evidentiary scratch experiments to remain temporary, and provide a bounded same-run namespace for exact auxiliary diagnostic captures.

Live finding checkpoint: `RUN_20260914T235131Z_radio-interface-smoke` cited a fresh isolated `/help` control case as complete while its logs remained only in `/tmp`.

Partial implementation: optional same-run `artifacts/` publication added at `dev@a7e567783169cbd0ba626e0dc809960e83e55230`; follow-up test fix/validated tree `dev@4e8ac48e39232d75c774c87d9f1878a3ffb242b7`; GitHub Actions `35039172751` SUCCESS. The four canonical RUN files remain required, manifest schema v1 is unchanged, auxiliary files are accepted only below `artifacts/`, symlinks are rejected, and push-failure retry preserves atomic append-only publication. `NODE_RUN_AUXILIARY_ARTIFACTS.md` explicitly makes diagnostic capture opt-in; helper support does not start `btmon` automatically.

Remaining work: align the primary `NODE_OBSERVATION_RECORDING_POLICY.md` and node-agent skill so they distinguish same-run auxiliary captures from separately executed material control/reproduction runs, while not requiring publication of every scratch experiment.

TODO_026 logging-contract investigation is also OPEN and may be scheduled independently when log-format work is selected.

Suggested implementation order for the next pass: finish the HCI boundary isolation in `TODO_024`, then correctness/evidence boundaries (`TODO_011`, `TODO_013`, `TODO_016`, `TODO_017`, `TODO_021`, remaining `TODO_025` docs), then lifecycle/API robustness (`TODO_018`, `TODO_019`, `TODO_022`, `TODO_023`), then consistency/docs follow-ups (`TODO_012`, `TODO_014`, `TODO_015`, `TODO_020`). Re-evaluate ordering if implementation exposes dependencies.

### TODO_026 — `todos/TODO_026_UNIFIED_LOGGING_CONTRACT.md`

Status: IMPLEMENTED / PHYSICAL VALIDATION OPEN

Goal: unify or explicitly standardize interactive and agent logging so manual and machine-driven runs have a documented, comparable timestamp/session/direction contract without weakening forensic evidence.

Implementation: `dev@5965d576c3bb124d85adf7842282684e755894c7`; GitHub Actions `35733796357` SUCCESS; 156 tests PASS.

Selected contract: both frontends create the same timestamped `.console.log` logical timeline. Human primary `.log` remains the compatibility transcript; agent primary `.log` remains forensic/API/transport truth. Interactive output uses canonical `ManagedSession` completed lines for companion records.

Remaining gate: physical interactive smoke + physical agent smoke and timing comparison on the same firmware event type.

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
post-closure hardware smoke: PASS / physical BLE multi-device / 2026-09-03
```

## Current validation posture

Repository CI is the normal per-change clean-environment gate. Physical-node claims remain separate: do not infer current-head hardware validity from older run bundles. The newly recorded static and live findings are OPEN/PARTIAL until their individual implementation and validation gates are completed. For the next build-level validation pass, continue to prefer one long-lived `serialterminal agent` process and a broad scenario matrix over repeated manual operator actions; only UI-specific behavior that the machine API cannot exercise should require a separate human pass.
