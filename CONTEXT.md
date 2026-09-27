# Current work context

Status: COMPLETED

## Current operation

Recovery-history repair is complete.

Three snapshots that were accidentally published on the source branch `dev` were removed from that branch and inserted into the authoritative `dev_handoff` chronology. The former authoritative `dev_handoff/HANDOFF_008.md` was shifted to `HANDOFF_011.md`.

## Canonical snapshot chain

```text
HANDOFF_001.md .. HANDOFF_007.md
  original authoritative dev_handoff history

HANDOFF_008.md
  originally dev/HANDOFF_001.md
  created 2026-09-26T22:29:35Z
  original commit 06b2c56c9c7e7f51125e38e8e7a2c5a14901f054
  original blob 73548fd665c60ab58b42b4e1b6c33b8ab71eafdb

HANDOFF_009.md
  originally dev/HANDOFF_002.md
  created 2026-09-27T01:15:27Z
  original commit 4adc721be89fb62d7941dda829d8e06c6d5d0a1c
  original blob 7ddb27d7bf7ec536d629236cdd8c52adfccee729

HANDOFF_010.md
  originally dev/HANDOFF_003.md
  created 2026-09-27T01:57:25Z
  original commit 786f7b7daee160d409042418d5b3fcfb557cfa6b
  original blob d2bc50f0372925c438cf28a1f95234f97bb9b471

HANDOFF_011.md
  formerly dev_handoff/HANDOFF_008.md
  created 2026-09-27T02:02:00Z
  pre-repair blob ef37b94cdec4fa7b1a9ad8a23d7576e1f978363a
```

## Exact repair checkpoints

```text
staged canonical HANDOFF_009..011:
  dev_handoff@6034e0a2223264bd988c917bfc913a482743c987

installed canonical HANDOFF_008 and advanced HANDOFF_INDEX -> HANDOFF_011:
  dev_handoff@6fc387013e76256edcb6e4751475b0ba3d022401

removed numbered snapshots/index from source branch:
  dev@307b57f2c9370150f73b1c2f5196025a7d7eb4a6
```

## Authority

- `dev_handoff` is authoritative recovery/handoff state.
- `dev` is SerialTerminal source/tests/docs authority.
- `dev` keeps only the small source-side `HANDOFF.md` pointer plus the shared `HANDOFF_MANAGEMENT_POLICY.md`; numbered snapshots and `HANDOFF_INDEX.md` live on `dev_handoff`.
- `node_observations` remains physical hardware executor/evidence authority.
- The original mispublished snapshot commits remain in git history as provenance.

## Recovery order

1. read current source `dev:AGENTS.md`;
2. read this `CONTEXT.md`;
3. read `HANDOFF_INDEX.md` on `dev_handoff`;
4. read verified `HANDOFF_011.md`;
5. read current `TODO_INVENTORY.md` and relevant source docs on `dev`;
6. refetch moving `dev`, `node_observations`, and relevant firmware refs before current work.

Historical snapshot state never overrides refetched source for current implementation truth.
