# FT1 same-process pause/resume TODO

TODO-ID: TODO_035
Status: IMPLEMENTED / PHYSICAL VALIDATION OPEN
Parent: `TODO_033_FT1_RESUMABLE_TRANSFER_AND_CONTROLLER_RECOVERY`
Depends on: `TODO_034_CHATTER_CONTROLLER_LIFECYCLE_RECOVERY`

## Current implementation status

Automated implementation is complete. Active FT1 now enters `recovering_local_node` for recoverable local controller/transport outcomes, freezes later application messages, preserves exact current META/DATA/END identity, and replays only that idempotent current message inside one bounded recovery deadline. The old short fixed replay-count behavior is no longer the public recovery policy.

Current recovery defaults are documented in `FT1_RESUME.md`; the automated checkpoint is:

```text
SerialTerminal: dev_tui@2952d1e09ad550a60b25418dd10bb49e4aa73a4c
GitHub Actions: 37158286307 SUCCESS
pytest:         400 passed
```

Host tests cover repeated transient recovery beyond the old replay count, bounded timeout/cancellation, same transfer/message identity, lifecycle events, same-process receiver timeout/reopen, duplicate/conflicting DATA behavior, and preservation of existing END/MISSING/RESULT semantics.

**Physical validation has NOT been run.** Real sender/receiver reboot cases over BLE and USB, reset during repair, and bounded failure/cancel on actual nodes remain OPEN. Therefore this TODO is not CLOSED.

## Purpose

Make an active FT1 transfer survive a temporary reboot/disconnect of its **local** Chatter node while both SerialTerminal processes remain alive.

This TODO owns operation-specific FT1 recovery on top of the generic controller lifecycle established by TODO_034. It does not persist transfer state across SerialTerminal process death; that is TODO_036/037.

## Existing foundations to preserve

Current FT1 already provides:

```text
transfer_id : uint64
chunk_index : uint32
META / DATA / END / MISSING / RESULT
random-access receiver storage
idempotent identical DATA duplicate handling
MISSING selective repair after END
RESULT as application-level completion truth
```

Current Chatter BINARY handling also treats these local outcomes as replay candidates for an idempotent FT1 message:

```text
local_tx_unknown
local_disconnect
local_controller_reset
```

The missing piece is a coherent transfer lifecycle: today a real node reboot can still leave transfer progress stuck or exhaust short replay logic without a useful explicit recovery state.

## Architecture boundary

TODO_035 must consume the controller lifecycle from TODO_034 instead of independently parsing boot/reset strings.

FT1 owns whether a current application message is safe to replay. Generic session/transport code does not.

The firmware remains unaware of FT1 and file recovery. No firmware ACK or USER wire-format change belongs here.

## Target sender state machine

Required behavior is equivalent to:

```text
sending / repairing / waiting_result
        |
        | local controller reset or transport unavailable
        v
recovering_local_node
        |
        +--> stop issuing later FT1 application messages
        +--> preserve prepared source/wire representation
        +--> preserve transfer_id
        +--> preserve current application message
        +--> preserve DATA chunk_index/payload when current message is DATA
        +--> preserve progress accounting
        |
        v
usable local transport + controller READY
        |
        v
replay only current ambiguous idempotent FT1 message
        |
        +--> settled -> return to prior transfer phase and continue
        |
        +--> recovery deadline exhausted -> terminal failure
```

A controller reboot must never silently allocate a new transfer ID.

The underlying Chatter USER session/sequence may change after reboot. FT1 `transfer_id + chunk_index` remains the stable application identity.

## Replay-safe FT1 messages

These messages are safe to replay with identical bytes/identity:

```text
META   same transfer_id and metadata
DATA   same transfer_id + chunk_index + payload
END    same transfer_id + END identity
```

RESULT/MISSING handling must remain consistent with existing FT1 control semantics. If a local outage occurs while sending them, any replay decision must be based on their existing idempotent protocol behavior, not generic blind retry.

Do not convert this into per-chunk application ACK traffic.

## Sender behavior

### Freeze later sends during recovery

Once the current local operation becomes ambiguous/unavailable, do not continue advancing through later DATA chunks.

The sender must have exactly one clear current application message whose outcome is being recovered before subsequent chunks are released.

### Preserve prepared data

Recovery must retain the current prepared wire source rather than recompressing/restarting the transfer within the same process.

For DATA, the exact payload for a replay must be byte-identical.

### Progress accounting

Do not increment file progress merely because a replay was attempted. Progress reflects logical FT1 chunk progression, not number of physical/local attempts.

### Waiting for RESULT

A local reboot while waiting for remote `RESULT` must not force a new full transfer. Re-establish local controller usability and continue the existing bounded META/END control-replay semantics as appropriate.

## Receiver same-process behavior

If receiver SerialTerminal remains alive while its local node resets/reconnects:

- retain current transfer record;
- retain `.part` wire file;
- retain received-chunk map in memory;
- stop treating local controller reboot as reason to discard already received chunks;
- resume accepting later DATA after local node becomes usable;
- use existing END -> MISSING repair for chunks whose local BINARY presentation was lost during outage;
- preserve harmless duplicate DATA behavior.

The receiver does not need persistent journaling yet; process memory is authoritative for TODO_035.

## Recovery timeout/failure semantics

Recovery must be finite.

Use a stable transfer-visible state and terminal error when local controller recovery cannot complete inside the bounded policy.

Exact code names may follow project conventions, but semantics must distinguish at least:

```text
normal binary send failure
recovering local node
local recovery exhausted
operator cancellation
```

Do not fall back to an automatic new `file_send_start` from chunk 0.

## TUI behavior

During recovery, show a state equivalent to:

```text
recovering local node
```

Do not leave the ordinary percentage frozen with no explanation.

After successful recovery, return to the previous logical phase:

```text
sending
repairing
waiting_result
```

or terminate explicitly on failure/cancel.

`Ctrl+C` remains the reliable operator escape path. Recovery ownership must never force the operator to kill the whole process merely to cancel a transfer.

## Agent API behavior

`file_transfer_observe` / status must expose enough structured information to distinguish:

```text
transfer active normally
controller reset detected
recovering local node
controller usable again
current FT1 message replayed
recovery exhausted
completed / failed / cancelled
```

The JSONL command loop must remain responsive during recovery.

## Relationship to TODO_029 / TODO_030

### TODO_029

Preserve existing reconnect/MISSING/RESULT architecture. TODO_035 extends the same-process contract specifically around local controller lifecycle recovery.

Existing selective repair remains authoritative:

```text
END
-> receiver computes missing chunk set
-> MISSING ranges
-> sender resends requested DATA
-> END
-> RESULT
```

### TODO_030

Preserve the no-TELEMETRY/no-output-mode-mutation contract. Recovery must not temporarily switch the node to BOTH/TELEMETRY just to obtain settlement information.

## Scope

TODO_035 includes:

- explicit FT1 recovering-local-node state;
- pause of later DATA while current local operation is unresolved;
- preserve current idempotent application message and transfer identity;
- replay after TODO_034 reports controller usability;
- receiver in-memory partial preservation across local node reset;
- existing MISSING repair after outage;
- bounded recovery failure;
- TUI/agent recovery visibility;
- cancellation/close safety;
- deterministic reset injection tests;
- physical two-node reset/reconnect validation.

## Non-goals

TODO_035 does **not** include:

- process-restart persistence;
- receiver manifests on disk;
- sender journals;
- new resume wire message;
- file offset in firmware ACK;
- automatic full-file restart under new transfer ID;
- generic blind retry of arbitrary writes;
- MISSING pagination;
- LoRa SACK;
- firmware `-16` root-cause work.

## Recommended implementation slices

Likely reviewable commit order:

```text
1. deterministic transfer reset tests reproducing the stuck state
2. FT1 recovery state + pause fence
3. sender current-message replay integration
4. receiver same-process state retention integration
5. TUI/agent recovery visibility and cancellation
6. integration/regression/docs
```

Each semantic step gets targeted tests and full CI before advancing.

## Implementation checklist

- [ ] reproduce reset during active FT1 deterministically with `/reboot`/synthetic lifecycle;
- [ ] add explicit transfer recovery state/event;
- [ ] block later FT1 messages while current message is unresolved;
- [ ] preserve prepared source/wire representation;
- [ ] preserve transfer_id and current chunk_index/payload;
- [ ] replay only the current idempotent message after controller READY;
- [ ] resume previous logical transfer phase after successful replay;
- [ ] retain receiver in-memory partial state across local controller recovery;
- [ ] ensure END -> MISSING repair still catches host-visible holes;
- [ ] make recovery deadline finite and terminal failure stable;
- [ ] keep cancellation responsive during recovery;
- [ ] ensure close/session teardown cannot deadlock with recovery;
- [ ] expose structured recovery events/state through agent API;
- [ ] expose clear TUI state;
- [ ] preserve TODO_030 output-mode contract;
- [ ] update FILE_TRANSFER.md / AGENT_API.md as required;
- [ ] record exact implementation and validation checkpoints.

## Automated validation matrix

### Sender reset points

- [ ] after META local write but before exact local presentation;
- [ ] during an ordinary DATA settlement;
- [ ] between logical DATA chunks;
- [ ] while resending requested MISSING chunks;
- [ ] while sending/replaying END;
- [ ] while waiting for RESULT;
- [ ] repeated reboot until recovery deadline exhaustion;
- [ ] cancel during each recovery phase.

### Receiver reset points

- [ ] after META before DATA;
- [ ] mid-DATA;
- [ ] after some DATA before END;
- [ ] after all DATA before END;
- [ ] while preparing/sending MISSING;
- [ ] while sending RESULT;
- [ ] recover and still detect missing chunks correctly.

### Transport shapes

- [ ] BLE reset causing disconnect/reconnect;
- [ ] USB controller reset with tty still open;
- [ ] transport disconnect without controller reset;
- [ ] reset without transport-generation change;
- [ ] reconnect only to same selected logical node.

### Correctness

- [ ] no duplicate logical progress increment on replay;
- [ ] duplicate DATA remains harmless only when bytes match;
- [ ] conflicting duplicate DATA remains fatal;
- [ ] transfer_id never changes silently during recovery;
- [ ] prepared wire bytes remain identical across replay;
- [ ] no automatic new-transfer/full-file restart loop;
- [ ] final RESULT remains required for sender completion.

## Physical validation

Using two actual nodes and real SerialTerminal processes:

- [ ] sender-node deliberate reboot mid-file over BLE -> transfer resumes/completes;
- [ ] receiver-node deliberate reboot mid-file over BLE -> transfer resumes/repairs/completes;
- [ ] USB controller reboot with port staying open -> transfer resumes/completes;
- [ ] reset during repair round -> recovery/completion;
- [ ] repeated reset until bounded failure -> no indefinite hang;
- [ ] cancellation while recovering -> clean cancellation without killing ST;
- [ ] exact final byte count/SHA after every successful case.

Use deterministic `/reboot`; reproducing the rare firmware `-16` is not required.

## Acceptance criteria

TODO_035 is CLOSED only when:

- TODO_034 controller lifecycle is used as the recovery source of truth;
- active FT1 explicitly pauses during local node recovery;
- only the current replay-safe FT1 message is replayed;
- transfer identity/progress/source remain stable;
- receiver state survives same-process local node outage;
- existing MISSING repair closes resulting holes;
- recovery either succeeds or terminates with stable bounded failure, never hangs indefinitely;
- TUI/agent expose recovery and remain cancellable;
- automated tests/full CI pass;
- required two-node physical reset cases pass at exact recorded checkpoints.

Completion of TODO_035 provides the in-process state machine on which persistent receiver state in TODO_036 can build.