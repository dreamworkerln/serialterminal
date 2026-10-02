# Handoff snapshot 014

```text
Snapshot: HANDOFF_014.md
Previous: HANDOFF_013.md
Created: 2026-10-02T19:59:41Z
Handoff authority before snapshot creation:
  dreamworkerln/serialterminal/dev_handoff@167e511413f267a84b4f8c944ee22bc1ee7461a7
Source checkpoints:
  stable SerialTerminal source baseline:
    dreamworkerln/serialterminal/dev@7cf0459c4e00a81592d447e0592e83a1142e18d9
  active TUI / BINARY USER / file-transfer source:
    dreamworkerln/serialterminal/dev_tui@57108999bf267d58b5f824ed1c153122d95f5dd4
  hardware executor / evidence authority:
    dreamworkerln/serialterminal-observations/master@a80c4f48844b8179729d966e3a51a932d11fb807
  deployed firmware used by the latest complete profiling run:
    dreamworkerln/lora-sack-protocol@94ff6e4cb792cdb5e9ea77dcd214224053fb9c7b
  current firmware investigation branch, read-only from this workstream:
    dreamworkerln/lora-sack-protocol/dev_chat_ack_ble_tx_backpressure@d06a0d3cf2fd2156b98a936c0c22e403f72c9315
Knowledge base:
  SerialTerminal source/docs:
    dreamworkerln/serialterminal/dev_tui@57108999bf267d58b5f824ed1c153122d95f5dd4
  hardware executor instructions:
    dreamworkerln/serialterminal-observations/master@a80c4f48844b8179729d966e3a51a932d11fb807
Transfer / promotion boundary:
  dev_tui remains active SerialTerminal source; no promotion to dev.
  Hardware evidence/executor state now lives in the separate serialterminal-observations
  repository on master; the legacy serialterminal/node_observations role is superseded.
```

This snapshot becomes immutable after publication through `HANDOFF_INDEX.md`.

## 1. Recovery / authority

`dev_handoff` is the authoritative SerialTerminal recovery state.

Current source roles:

- `dev` — stable SerialTerminal baseline;
- `dev_tui` — active TUI/BINARY/FT1 source;
- `serialterminal-observations/master` — independent hardware executor/evidence
  workspace and publication authority;
- firmware repositories/branches — read-only references from this SerialTerminal
  workstream unless the operator explicitly starts firmware source work.

Before new work, refetch moving refs. Do not reuse the old
`serialterminal/node_observations` branch as the current hardware evidence authority.

The profiling conclusions below are tied to the deployed firmware checkpoint
`94ff6e4cb792cdb5e9ea77dcd214224053fb9c7b`. The current firmware branch
`dev_chat_ack_ble_tx_backpressure` has moved beyond that checkpoint, so source
inspection of its current HEAD must not be substituted for the exact code that
produced the captured traces.

## 2. Material changes since HANDOFF_013

### SerialTerminal BLE write fragmentation

`dev_tui` advanced from:

```text
50c2536842aff60cd52f64e1031710cc5739d228
```

to:

```text
57108999bf267d58b5f824ed1c153122d95f5dd4
commit: fix: fragment BLE writes to characteristic limit
```

The BLE NUS transport now fragments one logical host->node write to the characteristic
`max_write_without_response_size` and preserves the exact byte stream with no
inserted separator/newline/sleep between ATT fragments.

For the common FT1 DATA command:

```text
243 raw BINARY bytes
-> 324 base64 chars
-> about 330 command bytes including "/bin " and LF
```

physical timing evidence showed the actual host BLE write split as:

```text
244 + 86 bytes
```

with the GATT logical write completing in roughly 2 ms on the measured run.

Partial fragmented-write failure after at least one fragment is classified as
`TransportWriteOutcomeUnknown`; first-fragment definite failure remains retry-safe
under the existing transport semantics.

Source validation at this checkpoint:

```text
GitHub Actions run 36996139436: SUCCESS
job 110803169111: SUCCESS
compile/static-analysis/complexity/tests: PASS
pytest count recorded during development: 359 passed
```

Hardware traces confirm that the fragmentation path executes on the real BLE link.
They do not prove every disconnect/error edge case.

### Hardware executor instruction repair

The hardware executor has moved into the independent repository:

```text
dreamworkerln/serialterminal-observations
branch: master
checkpoint: a80c4f48844b8179729d966e3a51a932d11fb807
```

The executor instructions were corrected so a plain operator request such as
"transfer this file from one node to the other" has an explicit QUICK happy path.

The maintained rule is now:

```text
one long-lived SerialTerminal agent process
-> discover/open both Chatter sessions
-> file_send_start on sender only
-> coarse read-only status about every 2-5 s
-> bounded file_transfer_observe only for lifecycle/fault needs
-> require application-level completed / remote RESULT OK
-> file_transfer_close retained state
-> close sessions/process
```

Explicitly forbidden for a plain file transfer:

- manual file chunking by the model;
- model-generated base64;
- manual `send_line("/bin ...")`;
- `send_bytes` as an FT1 data implementation;
- one model/tool turn per DATA chunk;
- per-chunk `file_transfer_observe` pacing;
- automatically turning a plain transfer into a benchmark/canonical RUN;
- changing PHY/power/heartbeat/diag/echo/output mode merely to transfer a file.

The executor also requires a sibling SerialTerminal runtime containing the high-level
file API. Current validated baseline is
`dev_tui@57108999bf267d58b5f824ed1c153122d95f5dd4` or a descendant preserving
`file_send_start`, `file_transfer_observe` and `file_transfer_close`.

All stale executor/publication references to branch `node_observations` were removed.
Canonical publication/recovery in the independent evidence repository now targets
`master`.

## 3. Profiling data and integrity

Two complete file-transfer profiling runs were analyzed from large SerialTerminal
`.fttiming.jsonl`, ordinary ST logs and firmware USB/UART timing logs.

The large raw profiling logs were supplied through the conversation and analyzed
streamingly with Python. They have not been published as canonical RUN bundles in the
hardware evidence repository at this snapshot. Therefore the numerical findings below
are strong working evidence but not yet durable repository evidence.

The second complete run had the strongest integrity checks:

```text
FT1 DATA chunks: 149/149
original bytes: 33763
sender and receiver completed
same transfer_id on both ST sides
reliable USER sequence: D08F/0..150
no missing USER sequence numbers
```

The sender->receiver BINARY stream extracted from both firmware USB logs matched
byte-for-byte and in order for all 151 logical BINARY messages (META + 149 DATA + END).
The reverse FT1 RESULT also matched byte-for-byte.

Exactly one retry occurred: `D08F/27`.

The receiver had already received the first `D08F/27`, sent an ACK, then received
the same USER again and classified it as a duplicate with duplicate presentation
suppressed. Therefore that retry is consistent with a lost/not-received first ACK,
not a lost first DATA frame.

## 4. Measured SerialTerminal / BLE path

The earlier host-side timing trace showed that SerialTerminal itself is not spending
hundreds of milliseconds between FT1 chunks.

Representative normal costs:

```text
FT1 start -> binary_submit                about 0.1 ms
logical host BLE write                    about 2-3 ms
presentation line -> presentation match   about 0.7 ms
binary_return -> next submit              about 1.6 ms
ordinary log writes                       small compared with 200+ ms RF/BLE cycle
```

The host-side transfer remains sequential at the local BINARY settlement boundary:

```text
FT1 DATA
-> /bin submitted
-> local first-TxDone BINARY presentation observed
-> send_binary returns
-> next FT1 DATA is submitted
```

This means every DATA currently pays a full controller/BLE feedback roundtrip before
the next logical BINARY is allowed to enter the firmware queue.

The second profiling run again showed a large gap between one firmware
`BIN_PRESENT_TX` and the next firmware `BIN_INPUT`, while ST itself submitted the
next command within only a few milliseconds after receiving the local presentation.
The residual is roughly 160-180 ms at the median and appears in approximately 45 ms
steps.

Correct current interpretation:

- `write_gatt_char(..., response=False)` completing in about 2 ms proves BlueZ/native
  acceptance, not physical arrival of all ATT fragments at the ESP32;
- the large quantized residual belongs to the BLE/controller roundtrip and scheduling
  around firmware->host presentation plus host->firmware next command;
- the exact negotiated BLE connection interval was not directly measured, so do not
  state that the 45 ms step is definitely the negotiated interval without HCI/link
  evidence.

## 5. Firmware-native timing result

The deployed firmware checkpoint used native records of the form:

```text
[TIMING] us=<uint32 micros> event=<EVENT> ...
```

For intervals inside one node, `us=` is authoritative. Host line timestamps are only
arrival time. Firmware `micros()` is 32-bit; local deltas must be computed modulo
`2^32`. Absolute `us=` values from different nodes must never be directly
subtracted.

The complete second run provided native timing on both nodes.

### Sender, normal DATA

Representative medians:

```text
BIN_INPUT -> USER_DEQUEUE       about 1.609 ms
USER_DEQUEUE -> USER_TX.start   about 2.925 ms
USER_TX airtime                 about 100.144 ms
USER_TX.done -> BIN_PRESENT_TX  about 1.877 ms

BIN_INPUT -> BIN_PRESENT_TX     about 106.7 ms total
USER_TX.done -> ACK_RX          about 62.22 ms
ACK_RX -> ACK_MATCH             about 4.42 ms
```

Once a complete `/bin` has reached `BIN_INPUT`, the sender firmware normally begins
the RF USER attempt after only about 4.5 ms. Therefore the 200-300+ ms host-observed
per-chunk delay is not created by a large sender scheduler delay after `BIN_INPUT`.

### Receiver ACK turnaround

The second run exposed a new important component:

```text
BIN_RX -> ACK_PENDING        median about 5.194 ms
ACK_PENDING -> ACK_TX.start  median about 44.284 ms
ACK_TX airtime               median about 12.021 ms
BIN_RX -> ACK_TX.done        median about 61.533 ms
```

Distribution for `ACK_PENDING -> ACK_TX.start` across the 149 DATA frames was roughly:

```text
135 cases: about 44.3 ms
13 cases:  about 13.6 ms
1 case:   about 34 ms
```

No `ACK_GATE_BUSY` was observed in that run.

Inspection of the exact deployed firmware SHA showed no intentional fixed 44 ms ACK
guard in the pending-ACK path. Pending ACK is intended to send as soon as the radio
is not actively receiving.

The strongest current hypothesis is therefore scheduler/task interference before
`servicePendingAckIfReady()`, with BLE output work a prime candidate:

- RX handling creates telemetry/chat/BINARY presentation work;
- BLE TX runs in a separate FreeRTOS worker;
- deployed config has `BLE_TX_TASK_PRIORITY = 2`;
- the recurring about-44 ms and about-13 ms classes are consistent with BLE/controller
  scheduling effects;
- this is not yet a causal proof. A dedicated trace around
  `ACK_READY / ACK_SERVICE_ENTER / BLE_TX_WORK_START / BLE_TX_WORK_DONE` would
  distinguish scheduler preemption from another local cause.

## 6. Accepted optimization direction from profiling

Two independent bottlenecks should be treated separately.

### A. Receiver ACK fast path

Preferred firmware design direction for the firmware developer to evaluate:

```text
RxDone
-> validate/deduplicate USER
-> establish ACK obligation
-> transmit ACK as protocol-critical work
-> only then perform/defer host-facing telemetry/chat/BINARY BLE presentation
```

Host presentation should not be in the causal path between RxDone and ACK TX.

Also verify actual FreeRTOS priorities so BLE output cannot preempt protocol-critical
radio work for a full BLE connection-event-sized interval.

This is a firmware design recommendation only. No firmware code was modified from this
SerialTerminal workstream.

### B. Bounded next-BINARY pipeline

The larger throughput loss is the stop-and-wait coupling between ST and local first
TxDone presentation.

Current cycle is approximately:

```text
current USER TxDone
-> firmware > [BINARY]
-> BLE notify to host
-> ST receives/matches presentation
-> ST submits next /bin
-> BlueZ/controller delivers next command
-> firmware BIN_INPUT
-> next USER
```

The firmware reliable USER queue already demonstrated during retry that a later BINARY
can wait safely while the previous reliable transaction is still unsettled.

Therefore a likely high-value host/protocol optimization is a bounded pipeline/window
that keeps the next one or several idempotent BINARY/FT1 DATA messages queued ahead,
rather than waiting for local first-TxDone presentation before submitting every next
message.

Do not implement an unbounded host burst. Queue ownership, reconnect ambiguity,
`tx_state:unknown`, retry/idempotence and firmware queue depth must remain explicit.

A cleaner future flow-control signal could be a generic controller-level queue-accept
event distinct from local first-TxDone presentation. This is a design possibility, not
an implemented API.

### Rough measured ceiling estimate

Current complete transfer payload throughput was about 5.6-5.8 kbit/s.

Measured components imply that removing only the approximately 44 ms ACK scheduling
gap could improve the cycle materially, while keeping the next DATA already queued by
ACK completion could provide the larger gain.

A combined optimized cycle on the measured SF7/BW500 setup plausibly approaches the
order of 125 ms rather than the current roughly 273 ms, corresponding to an
experimental payload-rate target around 14-15 kbit/s.

This is an engineering estimate from measured components, not a validated throughput
claim.

## 7. Current validation state

### SerialTerminal source

```text
dev_tui@57108999bf267d58b5f824ed1c153122d95f5dd4
GitHub Actions 36996139436: SUCCESS
job 110803169111: SUCCESS
```

The BLE fragmentation implementation is source-tested and was observed physically
splitting a 330-byte logical FT1 command into 244+86-byte GATT writes.

### Hardware profiling

Actually observed:

- complete FT1 transfers with remote RESULT OK;
- exact sender/receiver transfer identity and payload consistency in the second run;
- firmware-native USER airtime around 100 ms for full DATA;
- firmware-native ACK airtime around 12 ms;
- repeatable about-44 ms receiver ACK scheduling class;
- repeatable large BLE/controller residual with about-45 ms quantization;
- one duplicate/retry case consistent with first ACK loss.

Still open:

- direct proof of the internal cause of the 44 ms receiver ACK scheduling delay;
- direct measurement of negotiated BLE connection parameters/HCI event timing;
- physical validation of any ACK fast-path change;
- implementation/validation of bounded BINARY pipelining;
- canonical publication of the profiling raw evidence into
  `serialterminal-observations`.

## 8. Important invariants

Preserve:

- firmware remains read-only from ordinary SerialTerminal source work;
- generic transport/session layers remain controller-agnostic;
- Chatter BINARY semantics remain profile-owned;
- FT1 remains above opaque BINARY USER transport;
- `tx_state=written` is not peer/application delivery;
- sender FT1 completion requires remote RESULT OK;
- BLE fragmented writes preserve the exact logical byte stream with no inserted delay;
- partial fragmented-write ambiguity remains explicit;
- timing instrumentation must not add synchronous per-event disk I/O;
- raw base64 remains redacted by default;
- Ctrl+C remains ordinary immediate quit semantics;
- do not reintroduce one-model-turn-per-chunk orchestration;
- plain hardware file transfer uses high-level file API, not manual `/bin`;
- the independent hardware evidence repository publishes on `master`, not the legacy
  `node_observations` branch.

## 9. Current hardware-agent contract

For a plain operator request to transfer a file:

```text
classification: QUICK
transport default: BLE unless operator/scenario says otherwise
one long-lived agent process
both nodes opened with profile chatter
file_send_start only on sender
coarse status every about 2-5 s
bounded file_transfer_observe only if needed
PASS only at application-level completion
file_transfer_close retained state
normal session/process cleanup
no RUN/OBS unless explicitly requested
```

Do not automatically normalize RF experiment settings for this QUICK operation.

The current instructions implementing this contract are in:

```text
dreamworkerln/serialterminal-observations/master@a80c4f48844b8179729d966e3a51a932d11fb807
AGENTS.md
.agents/skills/lora-chatter-hardware/SKILL.md
CODEX_HARDWARE_TEST_SETUP.md
NODE_OBSERVATION_RECORDING_POLICY.md
.agents/skills/lora-chatter-hardware/references/evidence-recovery.md
README.md
```

## 10. Immediate continuation

1. When the operator asks the hardware executor to transfer another file, use the new
   QUICK file-transfer path from `serialterminal-observations/master@a80c4f48...`.
2. Verify the sibling runtime used by that executor contains the high-level file API;
   current validated baseline is `dev_tui@57108999...` or a descendant preserving it.
3. Observe whether the agent now performs only the intended simple transfer workflow;
   do not convert that test into a benchmark unless requested.
4. Firmware developer/colleague should evaluate the ACK fast-path/task-priority finding
   against the exact deployed profiling SHA before changing code.
5. After any firmware optimization, repeat the same two-node profiling with firmware
   `[TIMING]` enabled and compare first-attempt DATA separately from retry chunks.
6. If bounded SerialTerminal BINARY pipelining is requested, treat it as a separate
   source-design task with explicit queue/window and ambiguity semantics; do not infer
   permission from this handoff alone.
7. If the profiling evidence is to become durable project evidence, publish a
   canonical RUN/OBS in the independent `serialterminal-observations` repository
   rather than resurrecting the legacy source-repo evidence branch.

## 11. Standing reminders

- Refetch moving heads before new work.
- `dev_handoff` is recovery authority, not source authority.
- `dev_tui` is active SerialTerminal source.
- `serialterminal-observations/master` is current hardware executor/evidence
  authority.
- Historical `HANDOFF_013.md` statements about `node_observations` remain immutable
  historical state and are superseded by this snapshot.
- The profiling numbers in this snapshot are tied to deployed firmware
  `94ff6e4cb792cdb5e9ea77dcd214224053fb9c7b`.
- Current firmware branch HEAD is newer and must not silently replace that exact
  profiling provenance.
- CI success is source validation, not proof of RF/throughput behavior.
- The large raw profiling logs were analyzed but are not yet canonical repository
  evidence.
- Keep the BLE fragmentation fix and ACK/pipeline performance questions conceptually
  separate: one fixes transport correctness; the others target throughput.
