# Current work context

Status: PAUSED / HANDOFF 014 PUBLISHED

## Current operation

The active SerialTerminal source workstream is `dev_tui`.

The previous timing-measurement operation is complete enough to identify the dominant
performance components. No new throughput optimization has been implemented in
SerialTerminal or firmware from this workstream.

Two follow-up tracks are open and intentionally separate:

1. exercise the corrected hardware-agent instructions on a plain file-transfer request;
2. let the firmware developer evaluate the measured receiver ACK scheduling delay and
   repeat native timing after any firmware change.

## Exact baselines

```text
Active SerialTerminal source:
  dreamworkerln/serialterminal/dev_tui@57108999bf267d58b5f824ed1c153122d95f5dd4
  GitHub Actions 36996139436 SUCCESS
  job 110803169111 SUCCESS

Stable SerialTerminal source baseline:
  dreamworkerln/serialterminal/dev@7cf0459c4e00a81592d447e0592e83a1142e18d9

Hardware executor / evidence authority:
  dreamworkerln/serialterminal-observations/master@a80c4f48844b8179729d966e3a51a932d11fb807

Deployed firmware used by latest complete profiling:
  dreamworkerln/lora-sack-protocol@94ff6e4cb792cdb5e9ea77dcd214224053fb9c7b

Current firmware investigation branch, read-only here:
  dreamworkerln/lora-sack-protocol/dev_chat_ack_ble_tx_backpressure@d06a0d3cf2fd2156b98a936c0c22e403f72c9315

Latest recovery snapshot:
  HANDOFF_014.md
  snapshot commit e146f4dafcf09e0f1d0acbc87699464f502d9864
  snapshot blob c4690d949ee064381c0f59b4323293b6cb75e624
```

## Current implementation state

SerialTerminal BLE NUS writes now fragment a logical command to the negotiated
write-without-response size. Physical timing showed the normal 330-byte FT1 command
submitted as 244+86 bytes.

File transfer remains sequential at the local BINARY first-TxDone presentation
boundary. No bounded multi-BINARY pipeline is implemented.

The independent hardware executor now has an explicit QUICK file-transfer workflow and
publishes evidence on `master`; old `node_observations` publication instructions are
superseded.

## Profiling state

The complete native timing run established, approximately:

```text
sender BIN_INPUT -> USER_TX.start       ~4.5 ms
full DATA USER airtime                  ~100.1 ms
receiver BIN_RX -> ACK_PENDING          ~5.2 ms
receiver ACK_PENDING -> ACK_TX.start    ~44.3 ms median
ACK airtime                              ~12.0 ms
sender USER_TX.done -> ACK_RX            ~62.2 ms
sender ACK_RX -> ACK_MATCH               ~4.4 ms

BLE/controller residual around next /bin:
  roughly 160-180 ms median, quantized in about-45 ms steps
```

The receiver ACK delay has no observed `ACK_GATE_BUSY` and no intentional fixed
44-ms guard at deployed firmware SHA. BLE output task scheduling/preemption is the
leading hypothesis, not yet causal proof.

## Invariants / do not change

- Firmware repo is read-only from the SerialTerminal workstream.
- Generic transport/session timing remains controller-agnostic.
- Chatter BINARY semantics stay profile-owned.
- FT1 stays above opaque BINARY USER.
- Do not remove explicit ambiguous-write semantics.
- Do not add unbounded host-side BINARY bursts.
- Do not add per-event disk writes to active timing paths.
- Do not reintroduce per-chunk model/tool orchestration.
- Plain hardware file transfer uses the high-level file API, not manual `/bin`.
- Raw base64 remains hidden/redacted by default.
- Ctrl+C remains ordinary quit behavior.

## Last completed action

`HANDOFF_014.md` was created on `dev_handoff`, read back and verified. The hardware
executor instructions were previously updated at
`serialterminal-observations/master@a80c4f48844b8179729d966e3a51a932d11fb807`.

## Next action

When the operator next asks the hardware agent to transfer a file:

1. refetch `serialterminal-observations/master`;
2. use the QUICK file-transfer workflow;
3. verify the sibling SerialTerminal runtime contains `file_send_start`;
4. do not mutate RF experiment settings unless explicitly requested;
5. preserve exact API/transport evidence if the workflow still misbehaves.

In parallel, firmware optimization discussion should start from the exact deployed
profiling SHA and the two distinct targets: receiver ACK scheduling and BLE/controller
roundtrip.

## Required validation

Still pending:

- a new simple hardware-agent file transfer using the corrected executor instructions;
- direct causal instrumentation of the receiver 44-ms ACK scheduling delay;
- hardware validation after any firmware ACK fast-path/task-priority change;
- any implementation/validation of bounded SerialTerminal BINARY pipelining;
- canonical publication of the large profiling evidence if desired.

## Recovery order

1. current source `dev_tui:AGENTS.md`;
2. this `CONTEXT.md`;
3. `HANDOFF_INDEX.md`;
4. `HANDOFF_014.md`;
5. current `dev_tui` docs/source and `serialterminal-observations` hardware skill;
6. refetch moving source/evidence/firmware refs.
