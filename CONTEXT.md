# Current work context

Status: IN PROGRESS

## Current operation

Publish the next SerialTerminal recovery snapshot after the post-003 documentation/agent-learning work on `dev`.

No production Python source change is part of this handoff operation.

## Exact current checkpoints

```text
SerialTerminal source/docs:
  dreamworkerln/serialterminal/dev@0da242eb9c67bf82d59fbfbbcb0bca3ced92a942
  GitHub Actions run 33909130096 SUCCESS

Observation evidence branch:
  dreamworkerln/serialterminal/node_observations@b024b43ef43d1e9fbe0806ef3996f1a4bc549198

Handoff authority after operating-instructions sync:
  dreamworkerln/serialterminal/dev_handoff@544bd8fdacab5581cf5da985e0d7426ccf767c77
```

Latest published recovery snapshot remains `HANDOFF_003.md` until `HANDOFF_004.md` is created, read back, verified, and only then published through `HANDOFF_INDEX.md`.

## Material state since snapshot 003

- `dev` advanced 22 commits from the source checkpoint recorded by snapshot 003.
- SerialTerminal Python transport/session/terminal implementation did not change in that range.
- Added `NODE_OBSERVATION_RECORDING_POLICY.md` for local executor raw hardware evidence.
- Added `NODE_SKILL_LEARNING_POLICY.md` for reviewer promotion/generalization.
- Added guarded `scripts/commit-node-observation` workflow and refined its standalone elevated execution/remote-verification contract.
- Run-specific node evidence moved to the orphan `node_observations` branch; `.agents/skills/node-agent/SKILL.md` is class-level only.
- Current `node_observations` contains three observation records; `REVIEW_STATE.md` still has no reviewed boundary.
- `AGENT_API.md` now explicitly says to run `python3 serialterminal.py agent` with elevated privileges.
- Node skill now documents current ACK-capable reliable USER semantics, bounded retry/queue/cancellation rules, duplicate/ACK handling, and the focused two-node reliability gate.
- Node skill keeps USER/ECHO payload guidance at `1..200` UTF-8 bytes; the 200-byte limit remains Chatter-specific, not a generic SerialTerminal send-line guard.
- Generic SerialTerminal send semantics remain unchanged: `send_line`/`send_bytes` queue transport work; firmware/application outcomes arrive later as RX/events.
- Current TODO inventory still has `Active: None`.

## Current authority boundaries

- `dev` is SerialTerminal source/docs authority.
- `dev_handoff` is recovery-only.
- `AGENT_API.md` is the generic JSONL contract.
- `.agents/skills/serialterminal-agent/SKILL.md` is the generic operational skill.
- `.agents/skills/node-agent/SKILL.md` is reusable class-level LoRa-Chatter guidance only.
- `node_observations` is append-only run-specific evidence, not source and not merged into `dev`.
- `NODE_OBSERVATION_RECORDING_POLICY.md` governs executor evidence recording.
- `NODE_SKILL_LEARNING_POLICY.md` governs reviewer promotion/generalization.
- Firmware/protocol authority remains the actual relevant `lora-sack-protocol` source/docs checkpoint.

## Validation

Current `dev@0da242eb9c67bf82d59fbfbbcb0bca3ced92a942` has GitHub Actions run `33909130096` with conclusion `success`.

No new hardware interaction is performed by this handoff task.

## Next action

1. Refetch exact `dev`, `node_observations`, and `dev_handoff` heads.
2. Create `HANDOFF_004.md`.
3. Read back and verify the snapshot.
4. Only then advance `HANDOFF_INDEX.md` to 004.
5. Finalize this mutable `CONTEXT.md` after publication.
