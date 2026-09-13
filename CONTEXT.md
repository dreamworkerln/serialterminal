# Current work context

Status: COMPLETED

## Current operation

Snapshot 007 publication is complete.

No production source change was part of this handoff operation.

## Exact completed state

```text
SerialTerminal source/docs:
  dreamworkerln/serialterminal/dev@ab8dfde761e06649bdbb89173401e4054f9e8c18
  GitHub Actions run 34787938656 SUCCESS
  compile PASS / Ruff PASS / pytest 122 passed
  Lizard non-blocking: 14 threshold warnings

Observation evidence:
  dreamworkerln/serialterminal/node_observations@761712ae7a7892764fbf47c1649710a1ef3e270f
  REVIEW_STATE.md remains unadvanced (none)

Chatter firmware/controller reference:
  dreamworkerln/lora-sack-protocol/dev_chat@49fcd72a26efa7f9f7029735242fa62d4fe66c1e

Pre-snapshot handoff checkpoint:
  dreamworkerln/serialterminal/dev_handoff@f624c5495ad48056f272144482187918ab568805

Verified snapshot creation:
  dreamworkerln/serialterminal/dev_handoff@faf4c2dcfabfc1b47ecf3926924a89bd3e38e49b
  HANDOFF_007.md blob 594f42f22a403249977a8b01fad5c224c9f9bada

Index publication:
  dreamworkerln/serialterminal/dev_handoff@e17814d8491f9f8475dc5568fde58b9c5c10a44d
```

`HANDOFF_INDEX.md` now points to verified `HANDOFF_007.md`. Older published snapshots remain immutable.

## Current recovery state

Recovery order:

1. read `AGENTS.md`;
2. read this `CONTEXT.md`;
3. read `HANDOFF_INDEX.md`;
4. read verified `HANDOFF_007.md`;
5. refetch moving `dev`, `node_observations`, and relevant firmware/protocol refs before current work.

## Current project state

- `dev` is source/docs authority; `dev_handoff` is recovery-only; `node_observations` is append-only run-specific evidence/review state.
- TODO_004 is CLOSED; current `TODO_INVENTORY.md` reports no active TODOs.
- `ManagedSession`, `observe`, the raw cursor model, per-stream logical-line assembly and `RunLog` remain invariants of the profile work.
- Human CLI now defaults to `profile=generic`; `--profile chatter` selects the bundled Chatter controller compatibility profile.
- Generic profile sends no controller-specific connect preamble, has no Chatter presentation/hotkeys, and uses standard NUS `0002` write + `0003` receive as stream `main`.
- Chatter profile provides `/id` preamble, `/help` forwarding, Chatter presentation, and BLE `0003 -> chat` plus optional `0004 -> telemetry` configuration. Firmware remains the owner of Chatter command/raw-control semantics.
- Agent `open` now defaults to `profile="generic"`; Chatter node work must explicitly use `profile:"chatter"`. Profile selection is per session.
- Legacy `auto_id` remains only as a compatibility override; it is not the generic default behavior.
- `BleNusTransport` now accepts injected characteristic/stream layout; Chatter `0004` semantics are no longer hard-coded in the transport runtime.
- Remaining generic-decoupling work exists in discovery/scanner/name aliases and compatibility defaults; see `HANDOFF_007.md`.
- Chatter raw control shortcuts are still represented as `SendLine` and therefore still append EOL; conversion to exact raw `SendBytes(14 31/32/33/65)` is not complete.
- `README.md` is materially stale relative to current profile defaults. `AGENT_API.md` and the generic/node agent skills were updated.
- Current profile-refactor source checkpoint has green automated CI but no current-revision physical hardware validation. Latest evidence runs were recorded against older SerialTerminal source revisions.
- `REVIEW_STATE.md` remains unadvanced; do not infer review/promotion from the newer run bundles.

## Validation

Current recorded source/docs validation:

```text
dev@ab8dfde761e06649bdbb89173401e4054f9e8c18
GitHub Actions run 34787938656 SUCCESS
Compile PASS
Ruff PASS
pytest 122 passed
Lizard non-blocking / 14 threshold warnings
```

No new physical hardware interaction was performed by this handoff task.

## Next action

No handoff publication action remains.

For the next engineering task, refetch all moving refs first. Immediate follow-up is to synchronize `README.md` with the generic/default profile behavior, continue the deliberate audit of residual Chatter/LoRa coupling in BLE discovery/scanner/aliases, keep raw-hotkey wire changes separate, and run a current-revision hardware regression through `serialterminal agent` using `open(profile="chatter")` before claiming physical validation of the profile refactor.
