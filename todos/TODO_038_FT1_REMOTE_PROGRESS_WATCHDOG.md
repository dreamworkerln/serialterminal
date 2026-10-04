# FT1 remote application-progress watchdog TODO

TODO-ID: TODO_038
Status: OPEN / DEFERRED UNTIL CURRENT BLE/BLUEZ THROUGHPUT CHARACTERIZATION COMPLETES
Depends on: `TODO_037_FT1_PERSISTENT_SENDER_AND_RESUME_HANDSHAKE`
Related: `TODO_029_FILE_TRANSFER_RECONNECT_REPAIR`, `TODO_033_FT1_RESUMABLE_TRANSFER_AND_CONTROLLER_RECOVERY`, `FT1_RESUME.md`

## Purpose

Detect the failure mode where the radio/firmware reliable layer still appears healthy but the remote SerialTerminal/FT1 receiver application has stopped making useful file progress.

Today firmware USER ACK answers only:

```text
remote firmware received this reliable USER transaction
```

It does **not** prove:

```text
remote SerialTerminal is alive
remote SerialTerminal parsed this FT1 DATA
remote SerialTerminal wrote the chunk into its `.part` file
remote SerialTerminal advanced durable receive state
remote FT1 application is still servicing this transfer
```

A receiver-side ST process can therefore be dead, wedged, disconnected from its node, or otherwise unable to consume FT1 while firmware-level reliable ACKs continue to succeed. On a large file the sender may keep producing locally settled DATA until END before the existing RESULT timeout finally proves that application completion did not occur.

TODO_038 adds a **rare FT1 application-level progress checkpoint** so sender ST can distinguish:

```text
firmware/radio peer reachable
```

from:

```text
remote FT1 application alive and durably progressing
```

without turning FT1 into per-chunk stop-and-wait.

## Scheduling / current experiment boundary

Do **not** implement this TODO until the current BLE/BlueZ throughput and scheduling investigation has produced a stable baseline.

Reason: even a rare application-level round trip changes steady-state file-transfer timing. Introducing it during the current speed investigation would contaminate measurements intended to isolate firmware/BlueZ/controller scheduling behavior.

The current transfer path must remain unchanged until this TODO is explicitly selected for implementation.

## Layering boundary

The distinction is mandatory:

```text
firmware reliable USER ACK
    frequent
    firmware-to-firmware
    confirms one reliable USER transaction
    carries no FT1 file state

FT1 progress checkpoint
    rare
    SerialTerminal-to-SerialTerminal
    confirms remote application/durable receive state
    carries transfer_id + receiver-proven progress
```

Do not modify firmware ACK format.
Do not teach firmware about FT1 `transfer_id`, file offsets, chunk indexes or durable state.
Do not replace existing reliable USER ACK semantics.

Firmware remains an opaque transport for FT1 BINARY USER payloads.

## Required protocol direction

Preferred design is a dedicated small FT1 control exchange rather than overloading META permanently as a heartbeat:

```text
Sender ST                         Receiver ST

DATA ...
DATA ...
DATA ...

PROGRESS_QUERY -------------------->
                                  inspect current durable RX state
             <---------------- PROGRESS(next_chunk=N)

DATA ...
```

Names are provisional until wire encoding is finalized. The semantic contract matters more than the exact enum names.

A temporary implementation may prove the concept using existing idempotent `META -> RESUME` semantics, because a replayed META already causes the receiver to report its earliest missing chunk. However the maintained protocol should prefer an explicit progress query/reply if that keeps META identity/setup semantics clearer and logs easier to interpret.

Any new message types must remain an FT1 host-layer extension and must have explicit old/new host compatibility behavior.

## What the reply must prove

The reply must be more useful than `alive=true`.

At minimum it should identify:

```text
transfer_id
receiver-proven durable next/earliest-missing chunk
```

Conceptually:

```text
PROGRESS transfer_id=ABCD durable_next_chunk=817
```

The progress cursor must be based on receiver state that is safe to rely on after process restart. Prefer the same **durable** receive map used by TODO_036/037 rather than merely reporting transient in-memory DATA receipt.

Therefore a reply equivalent to `817` means:

```text
receiver ST is alive enough to service FT1 control
and
receiver durable state proves the contiguous prefix before 817
```

It must not imply that every later sparse chunk is absent; existing END/MISSING remains authoritative for exact final hole repair.

## Frequency / overhead requirement

This is deliberately **not** a per-DATA acknowledgement mechanism.

Do not implement:

```text
DATA
<- FT1 ACK
DATA
<- FT1 ACK
...
```

That would duplicate the firmware reliable ACK round trip and materially reduce throughput.

Initial policy should be **time-based and rate-limited**, not a fixed acknowledgement every N chunks.

Starting design target:

```text
approximately one FT1 progress checkpoint per 10 seconds of active DATA transfer
```

with these constraints:

- at most one outstanding FT1 progress query per transfer;
- do not issue a new checkpoint unless DATA progress occurred since the previous successful checkpoint;
- no checkpoint storm after reconnect/recovery;
- timeout/retry policy must be bounded;
- all timing constants must live in the appropriate maintained config/module constants with rationale;
- exact default interval should be selected after current BlueZ/throughput measurements, not guessed from today's packet rate;
- physical validation must quantify throughput overhead versus the pre-TODO_038 baseline.

Time-based cadence is preferred because the same number of FT1 chunks represents very different wall-clock duration at different LoRa PHY settings and after future host-performance changes.

## Initial sender behavior

The first implementation should favor simple correctness over pipelined complexity.

Conceptual flow:

```text
send DATA normally
    -> checkpoint interval becomes due
    -> send one PROGRESS_QUERY
    -> wait a bounded time for matching PROGRESS
    -> if valid reply arrives, continue DATA
```

This creates a short pause only at the rare checkpoint instead of after every chunk.

Do not immediately add an asynchronous multi-window pipeline. If measured overhead later matters, a bounded future optimization may allow a small number of additional DATA chunks while one progress query is outstanding, but that is not required for the first implementation.

## Progress validation

Sender must reject or safely ignore malformed/inconsistent replies.

At minimum validate:

- matching `transfer_id`;
- cursor inside `[0, chunk_count]`;
- no impossible semantic state for the current META/wire identity;
- completed/tombstoned receiver state follows existing TODO_037 completion semantics;
- a stale reply from an old transfer cannot advance a new transfer;
- duplicate replies are harmless;
- replies may lag locally sent progress without being treated as corruption.

The receiver cursor is proof of receiver state, not a claim that sender's latest locally submitted chunk has already become durable.

## Remote-stall detection

If the firmware reliable layer keeps succeeding but the remote FT1 application does not answer the progress checkpoint within the bounded policy, sender must stop blindly streaming the rest of a large file.

Desired lifecycle:

```text
sending
  -> progress checkpoint due
  -> progress query unanswered after bounded retry
  -> remote_stalled
```

The state/failure reason must distinguish this from:

```text
local controller reset/recovery
local transport disconnect
local BINARY presentation timeout
remote RESULT timeout after END
operator cancellation
```

Observability should make the diagnostic boundary explicit where evidence permits it, e.g.:

```text
local DATA submissions settled,
firmware reliable transport may still be operating,
but remote FT1 application progress is not being confirmed.
```

Do not claim firmware ACK success unless that fact is actually observable through the current host contract. The key architectural distinction remains that FT1 progress timeout is an application-level failure, not proof of RF failure.

## Stall is resumable, not automatically destructive

A detected remote application stall should integrate with TODO_036/037 durable resume rather than discard the transfer.

Preferred conceptual lifecycle:

```text
sending
  -> remote_stalled
  -> retain sender journal / same transfer_id
  -> bounded low-rate recovery probes or explicit operator retry according to final policy
  -> remote ST returns
  -> receiver-proven progress/resume cursor obtained
  -> continue same logical transfer
```

Do not delete sender resume state merely because a progress checkpoint timed out.

Do not automatically create a new transfer ID after a temporary remote stall.

The exact automatic recovery cadence must be bounded and must not produce endless RF/control traffic. If safe automatic recovery semantics are not convincing, terminal `remote_stalled` plus explicit `file_send_start(path)` resume is acceptable for the first version.

## Receiver behavior

Receiver must answer a valid progress query using current durable transfer state without disturbing normal DATA handling.

Requirements:

- no new receive lease for an already active matching transfer;
- no reset of existing received ranges;
- no final-file republish;
- no mutation of unrelated transfer state;
- response is idempotent;
- suspended durable partial state may be reopened/probed consistently with TODO_036/037 rules;
- completed tombstone can return completion semantics without requiring full DATA resend;
- conflicting transfer identity must produce a stable explicit protocol result rather than an invented cursor.

The progress response should reuse the same durable earliest-missing calculation as resume where possible, rather than introducing a second independently maintained notion of receiver progress.

## Interaction with existing END/MISSING/RESULT

TODO_038 does not replace final correctness machinery.

Keep:

```text
END
-> exact receiver completeness/hash validation
-> MISSING selective repair if needed
-> END replay as required
-> RESULT OK only after verified completion
```

Periodic progress only provides **mid-transfer liveness and coarse durable-prefix knowledge**.

`MISSING` remains authoritative for exact sparse-hole repair.
`RESULT` remains authoritative for successful application completion.

## Compatibility

The final wire design must define new/old host behavior explicitly.

At minimum cover:

```text
new sender -> new receiver
new sender -> old receiver
old sender -> new receiver
```

A new sender must not incorrectly declare an old but otherwise functional receiver dead merely because it cannot understand an optional new FT1 progress message. Possible designs include capability/version gating or a conservative compatibility fallback. Select one explicitly during implementation and test it.

Do not infer support from firmware revision: firmware remains unaware of this extension.

## Agent / TUI observability

Expose enough state to tell whether the transfer is:

```text
sending
waiting_remote_progress
remote_stalled
resuming
waiting_result
repairing
```

Exact public state names may be consolidated if needed, but agent and TUI must not turn a bounded remote-progress wait into an unexplained frozen percentage.

Useful events should include equivalents of:

```text
progress_checkpoint_sent
progress_checkpoint_reply
progress_checkpoint_timeout
remote_stall_detected
remote_progress_recovered
```

Include transfer ID, sender-local progress and receiver-proven cursor where useful. Do not log raw file content.

## Throughput protection

This TODO is accepted only if it does not accidentally become another stop-and-wait acknowledgement layer.

Validation must measure:

```text
baseline steady-state throughput before TODO_038
vs
steady-state throughput with progress checkpoints enabled
```

using the same PHY, file, node roles and host/BLE topology.

The target is a small bounded overhead consistent with the chosen rare checkpoint cadence. If the measured penalty is unexpectedly large, investigate BLE/BlueZ/RF scheduling interaction before accepting the default interval.

Do not hide overhead by reporting only receiver final completion time without the same baseline comparison.

## Automated validation

Add deterministic tests for at least:

1. no per-DATA FT1 progress ACK is emitted;
2. checkpoint is not sent before configured time/progress eligibility;
3. only one progress query may be outstanding;
4. valid matching progress reply advances receiver-proven cursor;
5. delayed/duplicate reply is harmless;
6. wrong transfer ID cannot affect active transfer;
7. invalid/out-of-range cursor is rejected safely;
8. progress query timeout is bounded;
9. bounded retry cannot loop forever;
10. remote stall retains sender journal/resumable identity;
11. recovery resumes the same transfer ID from receiver-proven state;
12. receiver reply uses durable state, not unsafe transient-only progress;
13. sparse durable receiver state reports the same earliest-missing semantics as TODO_037;
14. completed tombstone path does not republish/resend the file;
15. cancellation works while waiting for progress;
16. local controller reset during checkpoint uses TODO_034/035 recovery semantics without creating a second outstanding query;
17. old/new host compatibility follows the selected contract;
18. agent status/events expose progress wait/stall/recovery deterministically;
19. ordinary small transfers that complete before the checkpoint interval incur no periodic progress exchange;
20. existing END/MISSING/RESULT tests remain unchanged/green.

## Physical validation

After current firmware/BlueZ investigation is complete and a throughput baseline is accepted, validate on two real nodes.

Required cases:

1. long normal transfer with checkpoints enabled: completion + hash PASS;
2. compare throughput against the exact pre-TODO_038 baseline;
3. kill/pause receiver ST while both firmware nodes remain alive; sender must detect application stall before streaming an arbitrarily large remainder;
4. restart receiver ST and prove same-transfer resume from receiver durable state;
5. repeat with sender/receiver node roles reversed;
6. receiver local controller reboot during progress checkpoint;
7. BLE disconnect/reconnect around a checkpoint;
8. USB case where tty remains open but receiver application/controller stops progressing;
9. operator cancel while `waiting_remote_progress` or `remote_stalled`;
10. old/new SerialTerminal compatibility according to the selected protocol rule.

Capture enough evidence to distinguish local controller lifecycle, transport lifecycle, firmware-visible behavior where available, FT1 progress query/reply, resume cursor and final RESULT.

## Non-goals

This TODO does **not**:

- modify firmware ACK or LoRa reliable USER format;
- introduce per-chunk FT1 ACK;
- implement LoRa SACK;
- replace TODO_037 persistent resume;
- replace END/MISSING/RESULT final verification;
- promise that a progress reply proves physical media durability beyond the receiver's documented TODO_036 durability contract;
- solve BlueZ scheduling or BLE connection-interval behavior;
- change the current throughput experiment before this TODO is explicitly selected.

## Suggested implementation checkpoints

Prefer several reviewable commits rather than one large change:

```text
1. protocol message/capability design + encoding tests
2. receiver durable progress reply
3. sender time-based checkpoint scheduler + bounded wait/retry
4. remote_stalled lifecycle + persistent-resume integration
5. agent/TUI observability
6. old/new compatibility tests
7. full regression + documentation
8. physical throughput/stall/recovery validation
```

Every source checkpoint must follow the normal deletion/diff review, targeted tests and full CI gate before acceptance.

## Acceptance criteria

TODO_038 can be CLOSED only when all of the following are true:

- remote ST application progress is periodically proven during sufficiently long transfers;
- the mechanism is rare/rate-limited and is not per-chunk stop-and-wait;
- firmware ACK remains unchanged and file-unaware;
- the receiver reports receiver-proven durable progress, not a meaningless alive bit;
- silent remote-application stall is detected before unbounded remainder transmission;
- timeout/retry/recovery are bounded;
- detected stalls retain resumable transfer identity/state;
- existing TODO_036/037 resume and END/MISSING/RESULT semantics remain authoritative;
- old/new host compatibility is explicit and tested;
- TUI/agent state does not appear frozen while waiting/stalled;
- automated tests cover the failure/recovery/compatibility matrix;
- physical two-node validation proves stall detection and same-transfer recovery;
- measured throughput overhead is documented against the pre-TODO_038 baseline;
- current firmware/BlueZ throughput characterization was completed before enabling this mechanism by default.
