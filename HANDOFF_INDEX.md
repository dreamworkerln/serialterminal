# Handoff index

This file is the mutable stable recovery entry point for the `serialterminal` workstream.

## Recovery order

1. Read applicable source operating instructions from current `dev_tui:AGENTS.md`.
2. Read `CONTEXT.md` on `dev_handoff`.
3. Read this `HANDOFF_INDEX.md`.
4. Read latest verified snapshot named below.
5. Read current `dev_tui` docs/source and hardware-executor instructions referenced by
   that snapshot.
6. Refetch actual moving source/evidence/firmware refs before new work.

## Snapshot rules

- `HANDOFF_NNN.md` snapshots are immutable after publication through this index.
- Create and read-back/verify a snapshot before advancing this index.
- Never replace historical exact SHAs with moving branch heads.
- `dev_handoff` is authoritative recovery state.
- `dev` is the stable SerialTerminal source baseline.
- `dev_tui` is the active TUI/BINARY/FT1 source branch.
- `serialterminal-observations/master` is the current physical hardware
  executor/evidence authority.
- Historical `serialterminal/node_observations` references remain historical only and
  are not the current publication target.

## Current latest snapshot

```text
Snapshot: 014
File: HANDOFF_014.md
Snapshot publication checkpoint:
  dreamworkerln/serialterminal/dev_handoff@e146f4dafcf09e0f1d0acbc87699464f502d9864
Snapshot blob:
  c4690d949ee064381c0f59b4323293b6cb75e624
```

`HANDOFF_014.md` was created and read back before this index was advanced.

## Current source roles recorded by snapshot 014

```text
Stable SerialTerminal source baseline:
  dreamworkerln/serialterminal/dev@7cf0459c4e00a81592d447e0592e83a1142e18d9

Active TUI / BINARY USER / file-transfer source:
  dreamworkerln/serialterminal/dev_tui@57108999bf267d58b5f824ed1c153122d95f5dd4
  GitHub Actions 36996139436: SUCCESS
  job 110803169111: SUCCESS

Hardware executor / evidence authority:
  dreamworkerln/serialterminal-observations/master@a80c4f48844b8179729d966e3a51a932d11fb807

Deployed firmware used by latest complete profiling:
  dreamworkerln/lora-sack-protocol@94ff6e4cb792cdb5e9ea77dcd214224053fb9c7b

Current firmware investigation branch, read-only from this workstream:
  dreamworkerln/lora-sack-protocol/dev_chat_ack_ble_tx_backpressure@d06a0d3cf2fd2156b98a936c0c22e403f72c9315
```

Before new work, refetch moving refs; these SHAs are snapshot state.

## Current state summary

- Host->node BLE logical writes are fragmented to the characteristic write-without-
  response limit; the measured 330-byte FT1 command is physically submitted as
  `244+86` bytes.
- `dev_tui@57108999...` is CI-green and preserves explicit ambiguous-outcome semantics
  for partial fragmented writes.
- Complete profiling localized two distinct throughput costs:
  - a large BLE/controller roundtrip around each next `/bin`, roughly 160-180 ms
    median residual with about-45 ms quantization;
  - receiver firmware `ACK_PENDING -> ACK_TX.start` about 44.3 ms median on most
    DATA frames, despite no intentional fixed ACK guard at deployed firmware SHA.
- Sender firmware itself starts USER TX only about 4.5 ms after complete `BIN_INPUT`;
  full USER airtime is about 100.1 ms and ACK airtime about 12.0 ms at the measured
  SF7/BW500 setup.
- The strongest current ACK-delay hypothesis is protocol-loop scheduling interference,
  with BLE output worker scheduling/backpressure a prime candidate; this is not yet
  causally proven.
- A bounded next-BINARY pipeline is the main architectural host-side optimization
  direction; it should be a separate explicit source task, not inferred permission.
- The latest profiling raw logs were analyzed from conversation uploads but have not
  yet been published as canonical hardware evidence.
- Hardware-agent instructions now define a plain file transfer as QUICK and require the
  high-level file API; manual `/bin`/base64/per-chunk model orchestration is forbidden.
- The independent evidence repository publishes on `master`; legacy
  `node_observations` executor/publication references were removed from current
  hardware instructions.

## Open operation

Two next steps are intentionally separate:

1. Hardware executor: when asked to transfer a file, exercise the new plain QUICK
   workflow and verify that the agent performs only the intended high-level transfer.
2. Firmware developer: evaluate the ACK fast-path/task-priority finding against the
   exact deployed profiling checkpoint, then repeat native timing after any change.

Do not mix those into one experiment unless the operator explicitly asks.

## Knowledge base

SerialTerminal source/docs:

```text
dreamworkerln/serialterminal/dev_tui@57108999bf267d58b5f824ed1c153122d95f5dd4
```

Read as needed:

```text
AGENTS.md
ARCHITECTURE.md
AGENT_API.md
FILE_TRANSFER.md
LOGGING.md
.agents/skills/serialterminal-agent/SKILL.md
src/serialterminal/timing.py
src/serialterminal/runlog.py
src/serialterminal/session.py
src/serialterminal/transports/ble_nus.py
src/serialterminal/profiles/chatter/binary_user.py
src/serialterminal/file_transfer/core.py
src/serialterminal/tui.py
src/serialterminal/agent.py
```

Hardware executor instructions:

```text
dreamworkerln/serialterminal-observations/master@a80c4f48844b8179729d966e3a51a932d11fb807
AGENTS.md
.agents/skills/lora-chatter-hardware/SKILL.md
CODEX_HARDWARE_TEST_SETUP.md
NODE_OBSERVATION_RECORDING_POLICY.md
.agents/skills/lora-chatter-hardware/references/evidence-recovery.md
README.md
```

## Immediate continuation

1. Refetch `dev_tui`, `serialterminal-observations/master` and any firmware ref
   relevant to the next task.
2. For the next plain file-transfer request, use the hardware executor QUICK workflow:
   one long-lived agent, both Chatter sessions, `file_send_start` on sender only,
   coarse `status`, application-level completion, retained-state close.
3. If that simple transfer misbehaves, preserve the exact executor/API failure rather
   than falling back to manual FT1 commands.
4. If firmware ACK scheduling is changed, rerun the same two-node native timing
   measurement and compare first-attempt DATA separately from retries.
5. Keep the measured BLE roundtrip problem separate from the receiver ACK-delay
   problem.
6. Implement bounded BINARY pipelining only after an explicit source-design task defines
   queue/window, reconnect and ambiguous-write semantics.
7. Publish profiling evidence into `serialterminal-observations/master` only if the
   operator wants durable canonical evidence.

## Standing reminders

- Authoritative recovery branch is `dev_handoff`.
- Active SerialTerminal source is `dev_tui`.
- Current hardware executor/evidence authority is
  `serialterminal-observations/master`.
- Published snapshots remain immutable.
- Firmware is read-only from ordinary SerialTerminal source work.
- Profiling conclusions in snapshot 014 are tied to deployed firmware
  `94ff6e4cb792cdb5e9ea77dcd214224053fb9c7b`.
- GitHub Actions is source validation, not physical BLE/radio validation.
- Deferred timing files require clean shutdown to be finalized.
- Do not reintroduce per-chunk LLM/tool file-transfer control loops.
- Raw base64 remains hidden/redacted by default.
- Ctrl+C remains ordinary quit semantics.
- FT1 same-process repair is not persistent resume.
