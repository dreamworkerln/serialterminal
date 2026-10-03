# FT1 resumable transfer and controller recovery TODO

TODO-ID: TODO_033
Status: OPEN

## Purpose

Make SerialTerminal tolerate local Chatter controller reboot/reconnect as a normal
lifecycle event and extend FT1 from same-process end-of-transfer repair into resumable
file transfer that can continue after a temporary node outage and, in the persistent
phase, after SerialTerminal process restart.

The work is intentionally split into three independently testable stages:

```text
1. controller reboot resilience in SerialTerminal generally
2. same-process FT1 pause/resume across local controller reset/reconnect
3. persistent FT1 resume using receiver partial state + sender journal
```

The file-resume mechanism is an application-level reliability layer above Chatter
reliable USER. It must not modify the firmware RF ACK format or teach firmware about
files, transfer IDs, chunk indexes or resume offsets.

Conceptually this becomes a second selective-recovery layer:

```text
firmware reliable USER
    -> reliability for one opaque USER transaction

FT1 file layer
    -> reliability/resume for stable file chunks
    -> effectively SACK-like recovery of file chunks, not RF packets
```

This TODO owns SerialTerminal-side design and implementation only. Firmware root-cause
work for RadioLib/SX1278 failures is external to this TODO.

## Motivation / observed failure

A current physical failure mode is a Chatter node hitting a rare RadioLib error such as
`-16` during specific radio conditions and then deliberately rebooting. The firmware
team is investigating the cause and may be able to avoid the reboot entirely, but
SerialTerminal must remain correct even if a controller reboots for this or any other
reason.

Today an active file transfer can become stuck or ultimately fail after the local node
reboots. This is unacceptable even if the firmware root cause is fixed because the same
host-side problem can also be triggered by:

```text
operator /reboot
brownout / power interruption
watchdog reset
BLE disconnect/reconnect
USB controller reset while the serial device stays open
future firmware recovery policy
other unexpected controller restart
```

The desired behavior is therefore not a one-off workaround for RadioLib `-16`.
Controller restart/reconnect must become a first-class host lifecycle event.

## Current source checkpoint and existing behavior

Finding/design checkpoint for this TODO:

```text
dreamworkerln/serialterminal
dev_tui@98fc5856cdc816b52629a334f4bd47e34e00c2a1
```

Relevant current components:

```text
src/serialterminal/session.py
src/serialterminal/profiles/chatter/binary_user.py
src/serialterminal/file_transfer/core.py
src/serialterminal/file_transfer/protocol.py
FILE_TRANSFER.md
AGENT_API.md
src/serialterminal/tui.py
src/serialterminal/agent.py
```

Current FT1 already has most of the identities required for safe resume:

```text
transfer_id : uint64
chunk_index : uint32
META
DATA
END
MISSING
RESULT
```

Current DATA identity is stable at the application layer:

```text
transfer_id + chunk_index
```

Receiver DATA storage is random-access:

```text
offset = chunk_index * chunk_size
```

and duplicate semantics are already idempotent:

```text
same transfer_id + same chunk_index + identical bytes
    -> harmless duplicate

same transfer_id + same chunk_index + different bytes
    -> protocol failure
```

Current FT1 `repairing` is same-process only and begins after `END`: the receiver
computes missing chunk indexes, sends one compact `MISSING` range set, and the sender
selectively seeks/resends those chunks before replaying `END`.

Current receiver state is not persistent. The `.part` wire file exists on disk while a
transfer is active, but the authoritative received-chunk map is held in memory. Current
failure/close paths may unlink the partial file. A SerialTerminal process restart loses
the transfer state.

Current sender `start_send()` allocates a new random `transfer_id` for a new send. A
manual retry after process restart therefore looks like a completely new transfer and
cannot be matched safely to an old receiver `.part` without additional persistent
identity.

The Chatter binary adapter already models a controller epoch independently from the
physical transport generation. It recognizes reset/fatal markers, waits for
`[SYS] CHATTER READY`, invalidates cached output mode state and can surface
`local_controller_reset`. FT1 currently treats `local_tx_unknown`, `local_disconnect`
and `local_controller_reset` as bounded replay candidates for the current idempotent
application message.

Those mechanisms are useful foundations, but they are not yet a complete lifecycle or
persistent-resume contract.

## Relationship to existing TODOs

### TODO_029

`TODO_029_FILE_TRANSFER_RECONNECT_REPAIR` owns the existing same-process FT1
MISSING/RESULT selective repair architecture. TODO_033 extends it rather than replacing
it.

Preserve from TODO_029:

```text
stable transfer_id/chunk_index identity
random-access receiver storage
idempotent identical DATA duplicate handling
META/END replay safety
MISSING selective repair
RESULT as end-to-end application completion truth
```

TODO_029 explicitly excludes persistent resume after SerialTerminal process death.
That exclusion is lifted only by this new TODO.

### TODO_030

`TODO_030_CHATTER_FT1_NO_TELEMETRY` remains authoritative for the rule that FT1 must
not depend on TELEMETRY and must not change the operator-selected output mode.

Controller recovery/resume must preserve that contract.

### Historical TODO_032

A narrow `TODO_032_FT1_LOCAL_CONTROLLER_RESET_RECOVERY` briefly existed in repository
history and was removed at `dev_tui@98fc5856cdc816b52629a334f4bd47e34e00c2a1` as a
misplaced project TODO. Per `TODO_MANAGEMENT_POLICY.md`, TODO IDs are not reused.

TODO_033 is the current intentional task and has broader scope: generic controller
lifecycle resilience, same-process pause/resume, and persistent FT1 resume.

## Core architecture decision: do not put file resume into firmware ACK

Do **not** extend Chatter RF ACK with file offset/chunk state.

Firmware ACK continues to mean only:

```text
peer firmware received this reliable USER transaction
```

It must not mean:

```text
peer SerialTerminal stored a file chunk
file offset N is durable
peer host wants chunk M next
file is complete
```

Firmware remains unaware of:

```text
filename
transfer_id
chunk_index
META / DATA / END / MISSING / RESULT
partial files
resume journals
filesystem state
```

Resume is an FT1 application handshake carried as ordinary opaque BINARY USER data.
This preserves the existing clean boundary and allows the same file protocol to remain
independent from future radio-level SACK work.

## Stage 1: controller reboot resilience in SerialTerminal generally

### Goal

Turn controller reboot/reset into a first-class lifecycle state rather than an implicit
error that individual commands must rediscover independently.

The host must distinguish:

```text
physical transport generation
    BLE/USB/SPP connection instance

controller epoch
    firmware lifetime inside that transport
```

A USB serial device may stay physically open while the ESP restarts, so transport
continuity never proves controller continuity.

### Target controller lifecycle

Expose/maintain an explicit model equivalent to:

```text
controller_state = ready | resetting | reconnecting | unavailable
controller_epoch = monotonic local generation

controller_reset_detected
controller_ready
```

Exact public API names may differ, but the semantics must be explicit and testable.

After a controller epoch change:

- cached controller-owned state is stale;
- pending operations whose result may already have occurred become ambiguous;
- arbitrary commands must not be blindly replayed;
- operations with explicit idempotent replay semantics may elect to recover;
- frontend/agent observation must be able to tell recovery from ordinary waiting.

### Generic replay rule

Do not weaken generic `tx_state=unknown` semantics.

An arbitrary command such as a profile mutation can have side effects and is not safe
to repeat merely because the controller rebooted or the transport reconnected.

Recovery authority belongs to the operation that knows its idempotence contract.

For FT1, these application messages are replay-safe by design:

```text
same META + same transfer_id
same DATA + same transfer_id/chunk_index/payload
same END + same transfer_id
```

Other operations must explicitly opt into equivalent behavior rather than inheriting a
global retry policy.

### Bounded lifecycle recovery

No controller recovery wait may be infinite.

Use an overall recovery deadline/state, not only a short fixed count of immediate
message retries. The exact constants are implementation choices, but the semantics must
support real controller reboot time and transport reconnect time while remaining finite.

Conceptually:

```text
operation active
    -> controller reset/disconnect
    -> recovering_local_node
    -> wait for usable transport + controller READY
    -> operation-specific replay/resume

recovery deadline exhausted
    -> stable terminal failure
```

The user must retain cancellation/control while recovery is pending.

### General validation for stage 1

Cover both reset shapes:

```text
BLE:
controller reset -> BLE disconnect -> reconnect -> READY

USB:
controller reset -> serial port may remain open -> new controller epoch -> READY
```

Use deterministic `/reboot` injection for validation. Reproducing the rare RadioLib
`-16` trigger is not required to prove host lifecycle correctness.

## Stage 2: same-process FT1 pause/resume

### Goal

If the SerialTerminal processes remain alive, a temporary local controller reset or
transport reconnect must pause an active file transfer and resume it without creating a
new transfer or retransmitting the whole file unnecessarily.

### Sender state machine

Target behavior equivalent to:

```text
sending / repairing / waiting_result
        |
        | local controller reset or local transport unavailable
        v
paused_reconnecting / recovering_local_node
        |
        +--> stop issuing later FT1 messages
        +--> preserve prepared source
        +--> preserve transfer_id
        +--> preserve current DATA chunk_index/payload
        +--> preserve progress
        |
        v
usable local transport + CHATTER READY
        |
        v
replay current ambiguous idempotent FT1 message
        |
        +--> settled -> continue previous transfer state
        |
        +--> recovery deadline exhausted -> terminal failure
```

Do not silently allocate a new transfer ID after controller reboot.

The firmware Chatter USER session/sequence is allowed to change after reboot. FT1
application identity remains authoritative for duplicate safety.

### Receiver same-process behavior

If receiver ST remains alive while its node reboots/reconnects:

- keep active FT1 record and partial file;
- do not discard already written chunks merely because local controller epoch changed;
- resume accepting DATA after local controller readiness returns;
- continue to use END -> MISSING for any chunks whose host presentation was lost during
  the outage;
- keep identical duplicate DATA harmless.

### Why this already resembles file-level SACK

Current receiver can detect an arbitrary missing set after END and request compact
ranges. That is already selective acknowledgment/recovery at the FT1 chunk layer.

Stage 2 should use that mechanism rather than inventing per-DATA FT1 ACK traffic.

## Stage 3: persistent FT1 resume

### Goal

Allow a transfer to resume after one or both SerialTerminal processes are restarted,
without trusting an unverified filename/offset heuristic and without restarting from
zero when valid partial data is available.

Persistent resume has three required pieces:

```text
receiver partial-state persistence
sender transfer identity/source persistence
META -> resume-state handshake
```

## Receiver persistent partial state

### Persistent artifacts

Keep a durable partial wire file plus a small manifest/journal, conceptually:

```text
.serialterminal-<transfer_id>.part
.serialterminal-<transfer_id>.resume.json
```

Exact naming/format may differ, but the persisted state must contain enough identity to
reject stale or conflicting resume attempts.

At minimum persist equivalent fields:

```text
format/schema version
transfer_id
full META identity
filename
original_size
wire_size
compression
chunk_size
original_sha256
chunk_count or derivable total
received chunk bitmap/ranges/checkpoint
part-file identity/path
last activity/checkpoint timestamp
```

The manifest must not use filename alone as transfer identity.

### Checkpoint policy

Do not fsync/rewrite a JSON manifest for every 227-byte DATA chunk on the normal path.
That would create avoidable disk and latency amplification.

Use bounded/coalesced persistence such as:

```text
periodic time checkpoint
or every N chunks
plus graceful/terminal lifecycle checkpoints
```

Exact interval/count is an implementation choice and must be measured.

Crash consistency rule:

```text
persisted received map may lag actual .part contents
```

That is acceptable because an unrecorded-but-written chunk can simply be retransmitted.
DATA replay is idempotent. Never infer that a chunk is durable merely from `.part`
file size because sparse/random-access writes can create holes.

### Suspended rather than deleted

A resumable incoming transfer that stops receiving activity must not automatically
unlink its `.part` solely because the peer disappeared.

Introduce a persistent/suspended state equivalent to:

```text
receiving
    -> peer/local interruption
    -> suspended
```

A suspended transfer should release the active session lease so unrelated future work
is not permanently blocked, while retaining bounded recoverable disk state.

Provide cleanup policy:

```text
TTL and/or max retained partial transfers
max total retained bytes or equivalent resource bound
safe explicit delete/cancel operation
```

Do not allow abandoned partials to grow without bound.

## Sender persistent journal

### Stable transfer identity

A restarted sender must be able to re-use the same `transfer_id` for the same logical
transfer.

Persist enough information to prove the source still matches the transfer:

```text
transfer_id
source path or stable source reference
source size
source mtime/inode only as hints, never sole content identity
original SHA-256
compression selection
wire size
chunk size
wire SHA-256 / END identity when available
protocol/schema version
```

Before resuming, revalidate the source content/metadata needed to guarantee that replayed
DATA for an existing `transfer_id` is byte-identical to the original transfer.

If source identity conflicts, do not resume under the old transfer ID.

### Deterministic wire representation

Current gzip preparation uses deterministic `mtime=0`, which is useful for rebuilding
an identical wire representation after restart.

Do not require permanent retention of the entire compressed temporary stream if it can
be deterministically rebuilt and verified. If implementation chooses to retain it for
performance, lifecycle/cleanup limits must be explicit.

## META -> resume handshake

### Direction

After sender establishes or restores its transfer identity, it sends the same idempotent
META first.

Receiver uses META to decide whether it has:

```text
no prior state for transfer_id
matching suspended partial state
matching already-completed state
conflicting state for transfer_id
```

Resume information is returned by FT1, not firmware ACK.

### Preferred initial resume contract: earliest missing chunk

For the first persistent implementation, prefer a simple application response equivalent
to:

```text
RESUME_FROM(next_chunk)
```

where `next_chunk` is the earliest chunk the receiver cannot prove present from its
durable received map.

Conceptual exchange:

```text
Sender ST                              Receiver ST

META ------------------------------------>
                                      load matching partial state
                                      determine earliest missing chunk
      <----------------------- RESUME_FROM N

DATA N --------------------------------->
DATA N+1 ------------------------------->
...
END ------------------------------------>
      <-------------------- MISSING ranges, if needed
selectively resend missing chunks ------>
END ------------------------------------>
      <--------------------------- RESULT OK
```

For a completely new transfer, receiver may indicate the equivalent of
`RESUME_FROM 0`.

For a fully completed retained transfer, receiver should return completion state/result
rather than request DATA again.

Exact wire encoding/name is to be finalized before implementation. If reusing an
existing FT1 message type can express the same semantics without ambiguity, document
and test that choice. Do not overload the firmware RF ACK.

### Why earliest-missing first

A single resume cursor is intentionally conservative and simple.

If receiver durable state is:

```text
0..816 present
817 missing
818..900 present
```

`RESUME_FROM 817` may cause harmless duplicate DATA for 818..900, but correctness is
simple and existing duplicate semantics protect the receiver.

After END, the existing MISSING repair mechanism still provides exact selective repair
for any residual holes.

Thus the initial hybrid is:

```text
fast resume:
    one earliest-missing cursor

exact completion repair:
    existing MISSING ranges
```

This avoids making persistent resume depend on a complex pre-transfer bitmap protocol.

## Optional later optimization: full file-chunk SACK before DATA

After the basic persistent resume is proven, FT1 may optimize the resume handshake by
returning the exact missing ranges immediately after META and sending only those chunks.

That would be true selective file-chunk recovery:

```text
META
<-- missing ranges / receiver chunk state
send only requested DATA chunks
END
<-- RESULT or residual MISSING
```

Current MISSING range encoding is already compact:

```text
range_count : uint8
repeated:
    start_chunk : uint32
    count       : uint32
```

At current 243-byte BINARY USER capacity, only a bounded number of ranges fit in one
message. Current FT1 intentionally has no MISSING pagination.

Therefore full pre-transfer file SACK is an optimization, not a prerequisite for the
first persistent-resume implementation. If required later, pagination/multiple-range
messages must be designed as a separate bounded protocol extension rather than silently
removing current limits.

## Completed-transfer tombstones

Persistent resume must handle this failure window:

```text
receiver got all DATA
receiver got END
receiver verified hashes
receiver atomically published final file
receiver sent RESULT OK
sender rebooted/lost connection before observing RESULT
```

On restart the sender may replay META/END for the same transfer ID.

Receiver must retain a small completed-transfer tombstone containing enough identity to
recognize the exact completed transfer and reply `RESULT OK` again.

Do not create a second destination such as `filename (1)` and do not receive the entire
file again merely because the previous RESULT was lost.

Current same-process FT1 already replays RESULT for matching completed META/END. Stage 3
makes that memory durable across process restart.

Tombstones need bounded retention/cleanup just like suspended partial transfers.

## Resume identity and conflict rules

Resume must be conservative.

Matching resume requires the same logical transfer identity and compatible metadata.
At minimum reject:

```text
same transfer_id with conflicting META
same transfer_id with different original hash/size
same transfer_id with incompatible chunk_size/compression/wire size
DATA bytes differing from an already durable chunk
completed tombstone with conflicting END/hash identity
```

Never silently merge partial state from two different files because names/sizes happen
to match.

## End-to-end completion truth

Preserve the current distinction:

```text
local transport written
local > [BINARY] first-TxDone presentation
firmware USER ACK
```

are **not** file completion.

Sender FT1 completion remains:

```text
remote verified RESULT OK
```

Persistent journal cleanup on sender must not occur before this application-level
completion is durable/observed according to the final design.

## Reboot/reconnect behavior outside file transfer

Controller reboot handling introduced for stage 1 must be usable by the whole Chatter
profile/session, not buried as a file-only parser special case.

However, recovery actions remain operation-specific:

```text
controller lifecycle event
    -> generic observation/state

whether to replay a command
    -> operation semantics
```

Do not make all user/profile commands auto-resume merely because FT1 can safely replay
its idempotent messages.

Agent API and TUI should expose controller recovery without freezing or silently
holding ownership forever.

## TUI behavior

During temporary local recovery, file transfer progress must not look silently frozen.
Show a state equivalent to:

```text
recovering local node
paused / reconnecting
resuming from chunk N
```

Exact wording is UI work, but state must distinguish normal RF transfer latency from a
local controller outage.

`Ctrl+C` keeps its ordinary reliable quit/cancel meaning. Recovery must never create a
mutual lock that prevents operator cancellation.

After recovery, transition back to the appropriate transfer phase rather than starting
a hidden new transfer.

## Agent API behavior

Structured API must expose enough information/events to distinguish:

```text
controller_reset_detected
recovering_local_node
controller_ready
transfer_paused
current application message replayed
resume handshake started
resume position/state accepted
persistent partial found / not found
repair requested
recovery exhausted
completed / failed / cancelled
```

Exact event names can follow existing conventions.

The JSONL request loop must remain responsive while recovery waits. Do not implement
resume by blocking the whole agent command loop.

A future explicit `file_send_resume` operation may be considered if automatic restart
of a persisted sender journal would be ambiguous or surprising. Do not invent implicit
background sends after process startup without a clear operator/API contract.

## Persistence location and ownership

Before implementation, define one stable application-data location for:

```text
incoming .part files
incoming resume manifests
sender transfer journals
completed tombstones
```

Do not scatter persistent protocol state through arbitrary current working directories.

File permissions, atomic manifest replacement and crash-safe update semantics must be
explicit.

Use temporary-write + atomic replace for manifests where appropriate.

Do not put raw source-file contents or BINARY/base64 payloads in JSON journals.

## Security / filesystem safety

Preserve current receiver filename sanitization and atomic final publish.

Persistent state must additionally defend against:

- path traversal through persisted or remote filenames;
- symlink surprises when reopening partial files;
- manifest path tampering;
- stale/corrupt manifest parsing;
- duplicate transfer IDs pointing at the wrong partial file;
- unbounded disk retention;
- decompression/hash verification bypass during resume.

Final file publication still requires complete wire hash and original hash/size
verification. Resume state is never sufficient proof of final correctness.

## Scope

This TODO includes:

- generic Chatter controller epoch/lifecycle recovery semantics in SerialTerminal;
- explicit finite recovery states/events;
- same-process FT1 pause/resume across controller reboot and transport reconnect;
- persistent receiver partial state;
- persistent sender transfer identity/source journal;
- persistent completed-transfer tombstones;
- META-driven resume handshake;
- preferred earliest-missing resume cursor for initial implementation;
- reuse of existing MISSING ranges for exact final selective repair;
- bounded retention and cleanup;
- TUI and agent API visibility;
- deterministic host tests and physical two-node validation;
- documentation updates to FILE_TRANSFER.md / AGENT_API.md / relevant skills;
- exact implementation and validation checkpoint recording.

## Non-goals

This TODO does **not** include:

- firmware source changes;
- diagnosing or fixing RadioLib/SX1278 `-16` root cause;
- changing firmware reliable USER ACK wire format;
- putting file offsets/chunk indexes into firmware ACK;
- radio-level LoRa SACK design;
- treating local first-TxDone presentation as remote file delivery;
- blind generic retry of arbitrary ambiguous commands/writes;
- unbounded automatic replay/reconnect loops;
- unbounded persistent partial-file retention;
- mandatory full pre-transfer missing-range SACK in the first implementation;
- hiding a failed source-identity check by silently starting a different transfer.

## Implementation plan

### Phase A — controller lifecycle foundation

- [ ] map all existing reset/fatal/READY markers and current controller epoch consumers;
- [ ] define explicit controller lifecycle state/event contract at Chatter/session boundary;
- [ ] keep controller epoch separate from transport generation;
- [ ] invalidate controller-owned caches on epoch change;
- [ ] make controller recovery observable by TUI/agent without relying on TELEMETRY;
- [ ] define one overall bounded recovery deadline/backoff policy;
- [ ] preserve generic ambiguous-write semantics and forbid blind retry;
- [ ] ensure operator cancel/quit remains responsive during recovery;
- [ ] cover BLE disconnect/reconnect and USB reset-with-port-open;
- [ ] add deterministic `/reboot` tests/injection path.

### Phase B — same-process FT1 pause/resume

- [ ] introduce explicit FT1 local recovery/pause state;
- [ ] stop issuing later FT1 messages while current local operation is unresolved;
- [ ] preserve prepared source and exact current FT1 message across recovery;
- [ ] preserve transfer_id/chunk_index/progress;
- [ ] replay only replay-safe current META/DATA/END after controller readiness;
- [ ] retain receiver partial state across local controller reconnect;
- [ ] continue normal END -> MISSING selective repair after outage;
- [ ] convert recovery exhaustion to stable terminal failure;
- [ ] expose recovery state/events in file_transfer_observe;
- [ ] show explicit recovery state in TUI;
- [ ] verify Ctrl+C/file cancel cannot deadlock against recovery ownership.

### Phase C — receiver persistent resume state

- [ ] choose stable persistent state directory and schema version;
- [ ] persist `.part` identity and full META identity;
- [ ] persist received-chunk bitmap/ranges with coalesced checkpoints;
- [ ] use atomic manifest updates;
- [ ] restore suspended incoming transfers after process restart;
- [ ] distinguish partial/suspended/completed/conflicting transfer IDs;
- [ ] stop deleting resumable partial state on ordinary peer timeout;
- [ ] release active session ownership while a transfer is suspended;
- [ ] add TTL/count/byte cleanup bounds;
- [ ] add explicit cleanup/cancel semantics;
- [ ] validate corrupted/stale/symlink/path-conflict manifests safely.

### Phase D — sender persistent journal

- [ ] persist transfer_id and source/wire identity before or during initial transfer;
- [ ] revalidate source identity before resume;
- [ ] deterministically rebuild or safely retain wire representation;
- [ ] refuse old transfer_id reuse if source identity changed;
- [ ] retain journal until remote application completion is proven;
- [ ] define explicit operator/API behavior for discovered resumable outgoing transfers;
- [ ] clean completed/expired journals safely.

### Phase E — META resume handshake

- [ ] finalize exact FT1 wire representation for resume state;
- [ ] preserve backward/version behavior explicitly;
- [ ] sender sends/replays META before resumed DATA;
- [ ] receiver finds matching durable partial/completed state by transfer_id + metadata;
- [ ] receiver returns earliest missing chunk for initial implementation;
- [ ] sender seeks to requested chunk and resumes from there;
- [ ] receiver accepts harmless duplicates after earliest missing chunk;
- [ ] END still triggers exact existing MISSING repair for residual holes;
- [ ] completed tombstone returns RESULT OK without retransmitting file;
- [ ] conflicting durable state returns deterministic protocol failure;
- [ ] bound resume-handshake retries/timeouts.

### Phase F — optional file-level SACK optimization

- [ ] measure whether earliest-missing resume retransmits enough duplicate suffix data to
      justify a richer pre-transfer selective request;
- [ ] if justified, design bounded missing-range resume response;
- [ ] do not add pagination/multipart MISSING implicitly;
- [ ] if pagination becomes necessary, create an explicit bounded protocol extension and
      validation plan.

### Phase G — docs/API cleanup

- [ ] update `FILE_TRANSFER.md` with persistent resume and controller lifecycle;
- [ ] update `AGENT_API.md` for any new operations/states/events;
- [ ] update `.agents/skills/serialterminal-agent/SKILL.md` so agents do not manually
      restart from zero when supported resume exists;
- [ ] update TUI help/status documentation if operator controls are added;
- [ ] update `TODO_INVENTORY.md` implementation/validation checkpoints;
- [ ] record exact protocol version/message compatibility decision;
- [ ] keep firmware boundary explicit in all docs.

## Automated validation matrix

At minimum cover the following without real RF fault dependence.

### Controller reset phases

- [ ] sender reset before META local presentation settlement;
- [ ] sender reset during ordinary DATA settlement;
- [ ] sender reset while repairing a MISSING range;
- [ ] sender reset while waiting for RESULT;
- [ ] receiver reset after META but before DATA;
- [ ] receiver reset mid-DATA;
- [ ] receiver reset after all DATA but before END;
- [ ] receiver reset while sending MISSING/RESULT;
- [ ] repeated reset until recovery deadline exhaustion;
- [ ] cancel during each recovery state.

### Transport forms

- [ ] BLE physical disconnect/reconnect around controller reboot;
- [ ] USB controller reboot with serial port continuously open;
- [ ] transport disconnect without controller reset;
- [ ] controller reset without transport generation change;
- [ ] reconnect to same logical selected device only; do not silently migrate transfer
      ownership to a different node.

### Persistent receiver restart

- [ ] restart receiver ST after only META;
- [ ] restart after contiguous prefix;
- [ ] restart with sparse received chunks;
- [ ] restart after all DATA but before END;
- [ ] restart after END verification but before sender sees RESULT;
- [ ] corrupted/stale manifest is rejected without publishing final file;
- [ ] persisted map lag causes safe duplicate retransmission, not corruption;
- [ ] cleanup TTL/resource bounds work without deleting active state.

### Persistent sender restart

- [ ] restart sender with unchanged source and resume same transfer_id;
- [ ] source content changed -> old transfer_id resume refused;
- [ ] deterministic gzip rebuild yields identical wire bytes/hash;
- [ ] completed receiver tombstone makes repeated META/END finish quickly;
- [ ] no resumable receiver state -> clean start at chunk 0 under same agreed transfer
      identity or explicitly documented new-transfer behavior;
- [ ] resume request outside declared chunk_count is rejected.

### Integrity

- [ ] final original byte count exact;
- [ ] final SHA-256 exact;
- [ ] no duplicate final file on lost RESULT replay;
- [ ] identical duplicate DATA remains harmless;
- [ ] conflicting duplicate DATA remains fatal;
- [ ] same transfer_id + conflicting META remains fatal;
- [ ] interrupted gzip transfer still validates wire and original hashes after resume.

## Physical validation

Physical validation must use two actual nodes and real SerialTerminal processes in the
normal deployment topology:

```text
host A <-> node A <------ LoRa ------> node B <-> host B
```

Required scenarios should include deterministic `/reboot` rather than depending on the
rare RadioLib `-16` trigger.

At minimum:

- [ ] sender-node reboot mid-file over BLE, transfer resumes/completes;
- [ ] receiver-node reboot mid-file over BLE, transfer resumes/repairs/completes;
- [ ] USB controller reboot where port remains open;
- [ ] restart receiver SerialTerminal mid-file and resume from durable partial state;
- [ ] restart sender SerialTerminal mid-file and resume same transfer identity;
- [ ] restart both SerialTerminal sides with retained journals and complete transfer;
- [ ] lost/replayed final RESULT path returns completion without duplicate final file;
- [ ] verify exact hashes and byte counts after every completed case;
- [ ] verify cancellation during recovery does not require killing SerialTerminal.

Record exact SerialTerminal SHA, firmware SHA(s), transport, node identities and logs for
accepted hardware evidence.

## Acceptance criteria

TODO_033 may be CLOSED only when all three stages are complete and validated.

### Stage 1 accepted when

- controller reboot is a bounded explicit lifecycle event;
- BLE and USB reset forms are covered;
- arbitrary ambiguous commands are not blindly replayed;
- TUI/agent remain responsive and observable.

### Stage 2 accepted when

- same-process FT1 survives temporary local node reboot/reconnect without hidden
  new-transfer restart;
- current idempotent message is safely replayed as needed;
- receiver gaps are repaired with existing MISSING;
- recovery either progresses or terminates with a stable reason, never hangs forever.

### Stage 3 accepted when

- receiver partial state survives process restart;
- sender can restore/revalidate transfer identity;
- META-driven resume begins from receiver-proven durable state rather than blindly from
  zero;
- residual holes are repaired selectively;
- completed tombstones survive lost RESULT/process restart;
- persistent state is bounded, crash-safe and cleaned deterministically;
- two-node physical restart/resume cases pass with exact final hashes.

Until those gates pass, inventory status must remain OPEN/PARTIAL/IMPLEMENTED with the
remaining validation called out explicitly.

## Design summary

Preferred architecture:

```text
Stage 1
controller reboot resilience for SerialTerminal generally

Stage 2
same-process FT1 pause/resume using existing idempotent FT1 identity and MISSING repair

Stage 3
persistent .part + receiver manifest
+ sender journal
+ META -> resume-state handshake
+ earliest-missing resume cursor
+ existing MISSING for exact final repair
+ durable completed tombstone
```

Do not modify firmware ACK for this feature.

The result is deliberately a file-layer selective recovery protocol: SACK-like behavior
for FT1 chunks while firmware continues to provide ordinary reliable opaque USER
transport.