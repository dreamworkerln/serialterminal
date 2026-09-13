# Handoff snapshot 007

```text
Snapshot: HANDOFF_007.md
Previous: HANDOFF_006.md
Created: 2026-09-13T23:04:01Z
Handoff authority: dreamworkerln/serialterminal/dev_handoff@f624c5495ad48056f272144482187918ab568805
Source checkpoints:
  SerialTerminal source/docs: dreamworkerln/serialterminal/dev@ab8dfde761e06649bdbb89173401e4054f9e8c18
  Node observation evidence: dreamworkerln/serialterminal/node_observations@761712ae7a7892764fbf47c1649710a1ef3e270f
  Chatter firmware/controller reference: dreamworkerln/lora-sack-protocol/dev_chat@49fcd72a26efa7f9f7029735242fa62d4fe66c1e
Knowledge base:
  SerialTerminal source/docs at dev@ab8dfde761e06649bdbb89173401e4054f9e8c18
  Node observation evidence at node_observations@761712ae7a7892764fbf47c1649710a1ef3e270f
  Chatter firmware/controller source at dev_chat@49fcd72a26efa7f9f7029735242fa62d4fe66c1e
Transfer / promotion boundary: none; this snapshot records the completed generic/Chatter profile separation slices and current evidence state without promoting unreviewed node observations.
```

This snapshot becomes immutable after publication through `HANDOFF_INDEX.md`.

## 1. Recovery / authority

Read applicable `AGENTS.md` first, then `CONTEXT.md`, `HANDOFF_INDEX.md`, and this snapshot. Refetch moving refs before new engineering work.

Authority split remains:

```text
dev
    SerialTerminal source/docs authority

dev_handoff
    recovery/handoff authority only

node_observations
    append-only run-specific hardware evidence/review state

lora-sack-protocol/dev_chat
    relevant Chatter firmware/controller source reference for the profile boundary work
```

`AGENT_API.md` is the canonical generic SerialTerminal JSONL contract. `.agents/skills/serialterminal-agent/SKILL.md` is the concise generic agent workflow. `.agents/skills/node-agent/SKILL.md` contains project-specific reusable LoRa-Chatter guidance and must not become a second definition of the generic SerialTerminal API.

## 2. Material changes since snapshot 006

Snapshot 006 recorded `dev@edeb4061d60a80768f38ddada0c6620798070d87` and `node_observations@301751038847f8416d5f6bab617185eee41f7f0a`. Current `dev@ab8dfde761e06649bdbb89173401e4054f9e8c18` is 24 commits ahead of that source checkpoint.

### TODO_004 is now CLOSED

Snapshot 006 described TODO_004 as deferred/unimplemented. That is historical and no longer current.

`TODO_INVENTORY.md` at the current source checkpoint reports no active TODOs. `TODO_004 — Automated node run bundles` is CLOSED. The guarded publication implementation is present, including `scripts/commit-node-run` and shared `scripts/node-publication-common.py`.

Recorded closure checkpoints include:

```text
Implementation/static-analysis:
  dev@4d50eb1aec50bfb4a71d1d8e63f95fbc7a0f436c
  GitHub Actions 34263084088 SUCCESS

Physical RUN + OBS publication:
  node_observations@f5020fd63e3cfdcf45244ff2dd6b0d86b963d7a0
  RUN_20260913T152239Z_todo004-bidirectional-publication-smoke
  result INCONCLUSIVE; publication path PASS / independently remote-verified

Physical RUN-only publication:
  node_observations@b22ee446d96e9fa9047d52f4d309830fca688893
  RUN_20260913T182004Z_post-reboot-bidirectional-smoke
  result PASS; bidirectional hardware path and publication path recorded as PASS
```

The evidence branch has advanced further since those closure checkpoints; do not confuse later run-specific findings with TODO_004 closure state.

### Bluetooth scanner UX clarification

Commit:

```text
e3ffc73b7da15c23e3b44b2a51ca62693c7aedb8
ui: clarify Bluetooth scanner selection
```

The interactive scanner now visibly confirms the eager numeric selection and prints one blank line between BLE and Classic/SPP phases in `all` mode. Routing and probe semantics were not changed.

### Generic / Chatter profile separation

The design boundary was checked against `lora-sack-protocol/dev_chat@49fcd72a26efa7f9f7029735242fa62d4fe66c1e`.

Accepted ownership rule:

```text
profile
    selects controller compatibility/configuration and convenience behavior

core
    performs transport/session mechanics

firmware
    owns the meaning and execution of Chatter commands/control sequences
```

Chatter text commands and raw control sequences are firmware/controller interfaces. SerialTerminal does not implement their radio semantics; a Chatter profile may only know which opaque line/bytes to send and how to configure/controller-present the transport.

The refactor was deliberately split into isolated slices:

```text
Slice 1
  6f91551a5e45e3f07e33023f54bb7a2fd184bb75
  refactor: add terminal profile compatibility seam

Slice 2
  d09cdce672e9880cceb6c07ce12f8eda0475343d
  refactor: move Chatter presentation into profile
  de2ff6dc0dff9f914ea901acf8763bc1a91c9851
  test: follow Chatter presentation move

Slice 3
  ba62515984bbcbc989bd5d389e73237b6c1bcf1c
  refactor: parameterize BLE receive layout

Slice 4
  1da66fba4b64d5d58dc587858997a471fc8c34ca
  feat: add generic human profile

Slice 5
  ab8dfde761e06649bdbb89173401e4054f9e8c18
  feat: make agent profile explicit
```

Two transient publication-mechanics commits (`fddd8aef650b26e85241ad3c64eb9b8ecb5d44b2` and `7e4089eba609e6743ee3e69a2c4fbfcf3a36b318`) appear immediately before Slice 4. History was not rewritten; current source tree is the accepted state at `ab8dfde...`.

## 3. Current implementation state

### Core/session invariants

The following are invariants of this refactor and were intentionally not converted into a profile lifecycle/plugin framework:

```text
ManagedSession reconnect/session mechanics
ordered reconnect-safe TX queue
raw SessionEvent cursor model
observe
logical line assembly per stream
RunLog / paired agent logging model
```

Profiles are consumed at configuration/frontend/factory boundaries. There are no profile `on_rx` / `on_connect` / `on_disconnect` lifecycle callbacks inside `ManagedSession`.

### Profile API

The bundled profile layer now contains:

```text
profiles/base.py
profiles/generic.py
profiles/chatter/profile.py
profiles/chatter/presentation.py
```

Actions remain deliberately simple transport intents (`SendLine`, `SendBytes`) rather than semantic methods such as `set_chat_mode()` or `enable_echo()`.

### Generic profile

`GENERIC_PROFILE` currently provides:

```text
connect preamble: none
controller hotkeys/actions: none
device-help forwarding: none
presentation adapter: none
firmware-command recognition: none
BLE write: standard NUS 0002
BLE receive: standard NUS 0003 -> stream "main"
```

This is the architecture-level regression goal: generic connect/reconnect must not produce unsolicited controller-specific TX or interpret arbitrary firmware text as Chatter output.

### Chatter profile

`CHATTER_PROFILE` currently provides controller compatibility/convenience behavior:

```text
connect preamble: SendLine("/id")
device help: SendLine("/help")
controller shortcut actions for 0x14 control sequences
BLE 0003 -> "chat" required
BLE 0004 -> "telemetry" optional
ChatterPresentation adapter
Chatter command recognition/presentation conventions
```

The firmware remains the owner of what `/id`, `/help`, `/chat`, `/tele`, `/both`, `/echo`, `/reboot`, or raw `14 31/32/33/65` actually mean and execute.

### Human CLI default

Human CLI parsers now accept:

```text
--profile generic
--profile chatter
```

and default to `generic`. CLI-created terminal sessions therefore use generic behavior unless `--profile chatter` is explicitly selected.

Compatibility detail: the `TerminalSession` class constructor itself still defaults to `CHATTER_PROFILE`, and `DeviceSelector` also retains a Chatter constructor default for direct/legacy callers. The normal CLI passes its resolved profile explicitly. Do not describe the class-level compatibility defaults as fully removed.

### Agent API default

Machine `open` now accepts a per-session profile and defaults to generic:

```json
{"op":"open","device_key":"..."}
```

is equivalent to `profile:"generic"` and has no profile connect preamble.

Chatter operation is explicit:

```json
{"op":"open","device_key":"...","profile":"chatter"}
```

The successful open/status state records the profile. One agent process may hold sessions using different profiles.

`auto_id` still exists only as a migration/compatibility override rather than as the generic default contract:

```text
auto_id omitted
    use selected profile preamble

auto_id=false
    suppress selected profile preamble

auto_id=true
    accepted only when selected profile defines a preamble

generic + auto_id=true
    invalid_profile_option
```

An unknown profile returns `unknown_profile`.

The project-specific node skill now instructs agents to open every Chatter session explicitly with `"profile":"chatter"`.

### BLE transport boundary

`BleNusTransport` no longer hard-codes the Chatter receive layout. It receives write characteristic plus configured receive UUID/stream mappings. Its no-configuration default is standard NUS `0002` write + `0003` receive as `main`.

The Chatter profile supplies custom `0003 -> chat` and optional `0004 -> telemetry` mapping.

## 4. Known incomplete generic decoupling / limitations

The profile split is materially implemented, but SerialTerminal is not yet completely free of project-specific Chatter/LoRa assumptions outside the profile package.

Remaining known coupling includes:

- `transports/ble_nus.py` still contains Chatter/project-oriented constants/helpers such as `NUS_CHAT_TX_UUID`, `NUS_TELEMETRY_TX_UUID`, `LoRa-*` name handling, `PINGER_NAME`, `REPEATER_NAME`, and legacy `p/r` target aliases/helpers;
- `ble_discovery.py` still knows `chat` / `telemetry` capability names and uses `LoRa-*` as a trusted visibility hint;
- Bluetooth scanner output still probes/reports `NUS`, `CHAT`, and `TELEMETRY` rather than only a generic standard-NUS capability model;
- CLI still retains legacy `p/r` alias normalization;
- direct `TerminalSession` / `DeviceSelector` constructor defaults remain Chatter compatibility defaults even though normal human CLI defaults to generic.

These are follow-up boundaries, not evidence that profile selection failed.

### Raw Chatter shortcut wire behavior is intentionally still legacy

The profile currently represents the firmware raw shortcut strings as `SendLine("\x141")`, `SendLine("\x142")`, `SendLine("\x143")`, and `SendLine("\x14e")`. Therefore the configured line ending is still appended.

The firmware-side ABI documents raw `14 31/32/33/65` controls without EOL. Converting these profile shortcuts to `SendBytes` is a separate observable wire-behavior change and has not yet been done. Do not claim it was fixed by the profile refactor.

### README is stale

`AGENT_API.md`, `.agents/skills/serialterminal-agent/SKILL.md`, and `.agents/skills/node-agent/SKILL.md` were updated for the current profile API. `README.md` was not yet synchronized and materially contradicts current defaults in several places: it still presents Chatter-oriented `/help`, `/id`, BLE 0004, hotkey, discovery, and old `auto_id=true` behavior as generic/default behavior.

README synchronization on `dev` is an immediate documentation follow-up. Do not repair it on `dev_handoff`; source/docs authority remains `dev`.

## 5. Validation evidence

### Current source checkpoint

```text
dev@ab8dfde761e06649bdbb89173401e4054f9e8c18
GitHub Actions run 34787938656: SUCCESS
Compile: PASS
Ruff/static analysis: PASS
pytest: 122 passed
Lizard: non-blocking exit 1 / 14 threshold warnings
```

GitHub Actions remains the authoritative clean-environment validation. The workflow is green despite the non-blocking complexity warnings.

### Hardware validation of the profile refactor

No physical hardware validation has been established for the current profile-refactor checkpoint `ab8dfde...`.

The latest evidence head is newer as an evidence branch but its newest recorded run used an older SerialTerminal source checkpoint. For example `node_observations@761712ae7a7892764fbf47c1649710a1ef3e270f` records `SerialTerminal: 5b98a61716b28d2b127370be94708890e59b5d21` in `RUN_20260913T224731Z_ack-queue-full-take2`, which predates the profile slices.

Therefore do not infer that explicit `profile:"chatter"`, current Chatter BLE profile injection, generic zero-preamble default, or mixed-profile agent sessions have been physically verified merely because later evidence commits exist.

## 6. Node observation evidence state

Current evidence head:

```text
node_observations@761712ae7a7892764fbf47c1649710a1ef3e270f
run: ack queue full take2
```

`REVIEW_STATE.md` is still unadvanced:

```text
last_reviewed_observation: none
last_reviewed_observation_commit: none
reviewed_against_dev: none
reviewed_by_commit: none
reviewed_at: none
unresolved: []
```

The evidence branch contains multiple published `RUN_20260913...` bundles created after snapshot 006. Their individual verdicts and exact recorded source revisions remain run-specific evidence. Do not promote them into class-level node guidance without the separate review/promotion process.

The newest `ack-queue-full-take2` run is `INCONCLUSIVE` and explicitly records firmware revision as `unknown`; preserve that uncertainty.

## 7. Firmware/controller reference boundary

The profile design was checked against:

```text
dreamworkerln/lora-sack-protocol/dev_chat@49fcd72a26efa7f9f7029735242fa62d4fe66c1e
```

Key architectural conclusion: controller commands and raw controls are executed/interpreted by the firmware. SerialTerminal profile logic should remain transport/configuration convenience and optional presentation compatibility, not an implementation of radio semantics.

Current detailed Chatter acceptance semantics, delivery evidence, RSSI/SNR/Q meaning, retry/ACK behavior and node-level test criteria belong in the project-specific node skill and firmware/protocol source/evidence, not in generic SerialTerminal core.

## 8. Important current documents/code

Source/docs authority at `dev@ab8dfde...`:

```text
AGENTS.md
AGENT_API.md
README.md                         # known stale profile-default sections
.agents/skills/serialterminal-agent/SKILL.md
.agents/skills/node-agent/SKILL.md
TODO_INVENTORY.md
NODE_OBSERVATION_RECORDING_POLICY.md
src/serialterminal/profiles/base.py
src/serialterminal/profiles/generic.py
src/serialterminal/profiles/chatter/profile.py
src/serialterminal/profiles/chatter/presentation.py
src/serialterminal/terminal.py
src/serialterminal/agent.py
src/serialterminal/cli.py
src/serialterminal/transports/ble_nus.py
src/serialterminal/ble_discovery.py
tests/test_generic_profile.py
tests/test_profiles.py
tests/test_ble_nus.py
tests/test_agent.py
```

Evidence authority at `node_observations@761712...`:

```text
REVIEW_STATE.md
observations/
runs/
```

## 9. Immediate continuation

1. Refetch `dev`, `node_observations`, and relevant `lora-sack-protocol` refs before making new claims or changes.
2. Synchronize `README.md` on `dev` with the current generic-default / explicit-Chatter profile behavior; do not leave the stale old `auto_id=true` and Chatter-default descriptions in the generic README path.
3. Deliberately audit the remaining project-specific coupling in BLE discovery/scanner/name aliases and decide which pieces belong in the Chatter profile versus generic discovery primitives. Keep `ManagedSession`, `observe`, cursor/line assembly and RunLog out of that cleanup unless tests force a change.
4. Treat the raw Chatter hotkey conversion from `SendLine`+EOL to exact `SendBytes(14 31/32/33/65)` as a separate behavior change with dedicated tests; it is not complete yet.
5. Run a hardware regression against the then-current `dev` using the real agent interface with `open(profile="chatter")`: verify profile preamble/controller identity, `/help`, expected BLE streams, and at least a narrow real node communication smoke. Publish run evidence under the normal observation/run policy if requested.
6. Preserve the reverse automated regression: generic open/connect/reconnect must emit zero controller-specific unsolicited bytes and must not interpret arbitrary controller output as Chatter presentation.
7. Keep `AGENT_API.md`, generic agent skill, and node-agent Chatter workflow synchronized with any subsequent profile/API change.

## 10. Standing reminders

- `dev` / `dev_handoff` / `node_observations` remain separate source / recovery / evidence authorities.
- Published handoff snapshots are immutable.
- TODO_004 is CLOSED; snapshot 006's deferred/unimplemented statement is historical only.
- `ManagedSession`, `observe`, raw cursor model, logical-line assembler and RunLog are invariants of the profile refactor unless a concrete defect requires otherwise.
- Profiles configure controller compatibility/convenience; firmware owns Chatter semantics.
- Current profile refactor has clean automated CI, but no current-revision hardware proof yet.
- Do not infer observation review/promotion while `REVIEW_STATE.md` remains unadvanced.
- Do not store concrete run-specific IDs, addresses, measurements or topology in the class-level node skill.
