# FT1 recovery and persistent resume

## Current recursive coordinator extension

The experimental branch dev_tui_exp_recursive_missing uses FT1 v3. Both endpoints
must run it; v1/v2 wire interoperability is not required. FILE_TRANSFER.md sections9..16
specify expanded META/END and the hash-verified full missing-list service files.
DATA and RESUME cursor shapes remain unchanged. Durable ROOT storage, source/wire
identity validation, atomic publication, quarantine and explicit resume below remain
applicable. Older stage checkpoints and v1 compatibility paragraphs are historical.

Service META adds previous_repair_id, matching its parent's latest END repair_id.
A parent retains only its latest completed child META and one queued verified
request; evicted old child identities cannot restart repair. Settled ROOT frames
retire while terminal records/tombstones preserve late completion semantics.

ROOT holds the external lease through its child stack. Parent control/idle waits pause
during children. ROOT threshold30%, service exemption, depths1..8 and per-file three
no-progress cycles are implemented by recursive.py. No overall one-hour deadline is
applied to recursive repair; unanswered control and transport recovery remain bounded.

A process restart suspends usable ROOT partial state; it does not restore an active
recursive stack. Explicit ROOT file_send_start revalidates the journal and same ID,
uses receiver-proven RESUME, then builds fresh service contexts after END. Internal
service files are not published as downloads. They do not prove ROOT completion.
New snapshots can contain repair progress. Physical checks for this extension are
pending and are separate from the historical stage8 evidence below.


This document is the authoritative contract for the controller-recovery and FT1
resume work implemented by TODO_034 through TODO_037 on `dev_tui`.

It specifically supersedes older statements elsewhere in the repository that say an
FT1 transfer must restart from zero after a SerialTerminal process restart or that a
receiver timeout always deletes its partial file. Those statements describe the
pre-TODO_033 implementation.

## Architecture boundary

Recovery is split into two layers:

```text
Chatter controller lifecycle
    local controller epoch/reset/READY state

FT1 application recovery
    file identity, chunks, durable partial state, resume cursor, MISSING, RESULT
```

Firmware reliable USER ACK is unchanged. It does not contain a file offset, transfer
ID, chunk bitmap, or resume cursor. Firmware continues to carry opaque BINARY USER
payloads. FT1 resume is host-to-host application protocol behavior.

Generic ambiguous writes are also unchanged: arbitrary commands are not blindly
replayed after disconnect/reset. Replay is allowed only where the owning operation can
prove idempotence. FT1 META, DATA and END satisfy that requirement for the same
transfer identity.

## Controller lifecycle

For the bundled Chatter profile, controller lifetime is distinct from transport
connection lifetime.

```text
connection_generation
    ManagedSession transport connection instance

controller_epoch
    firmware lifetime behind that transport
```

A USB tty may stay physically open while the ESP reboots. Therefore a controller reset
can advance `controller_epoch` without changing `connection_generation`.

`ChatterBinaryUserAdapter` owns reset/fatal/READY parsing and exposes controller state.
Current observable state includes the controller epoch and transport connection
generation. Reset markers invalidate controller-owned cached assumptions; a later
`[SYS] CHATTER READY` makes the new epoch usable.

The agent `status` result exposes a structured `controller` snapshot for Chatter
sessions. The TUI exposes non-ready controller state instead of presenting an
unexplained frozen operation.

A transport disconnect without reset evidence remains distinguishable from a proven
controller reboot; transport reconnect alone does not manufacture a new controller
epoch.

## Experimental transport lifecycle hardening

The architecture-repair series starts after SerialTerminal checkpoint `b7f58f8` and
paired Chatter checkpoint `2d8723ca`. Its overall execution plan lives in Chatter:
`chatter/ARCHITECTURE_REPAIR_EXECUTION_PLAN_2026-10-11.md`.

Serial short/invalid writes and backend write/flush exceptions produce an unknown
host outcome instead of blind generic replay. FT1 accounts for owned host writes
before releasing its mutation lease; a drain timeout reports a terminal failure and
retains ownership until session close. Chatter drain uses remaining admitted
machine-ticket deadlines plus the local guard; it is not clipped to 10 seconds or
an overall file deadline. There is no default hour-long RESULT wait. A secondary
cleanup error is recorded without hiding the primary failure. This does not prove
settlement of unobserved firmware/RF queues.

Chatter adapter waits share the caller's absolute monotonic deadline, including
scheduling lock acquisition, controller readiness and output-mode queries. Recovery
uses optional `prepare_binary(deadline, cancel_event)` to bound host reconnect and
controller preparation separately from the radio send budget. Without that capability,
`send_binary_until` carries the caller deadline when supported. A synchronous opaque
backend without deadline support cannot be promised a hard bound inside its call.

An unexpected RX handler, overflow-handling or idle-sweep exception is visible as `rx_worker_error` and
ends the affected attempt while retaining its partial/manifest. The shared RX worker
remains available. Invalid DATA index/length and END chunk count reject only that
message. Conflicting duplicates and hash/decompression failures retain the partial
in quarantine, which cannot automatically resume. MISSING delivery failure and
range overflow retain a suspended manifest; explicit cancellation removes it.
Legacy MISSING still carries the full set in one message, at most 28 ranges at
payload capacity 243; overflow reports `repair_too_large` without pagination.

An observed negative RESULT wakes recovery waits and stops new DATA submissions
in original, pipeline and repair paths, including cancellation-aware send,
readiness and pipeline submit/settle waits. It does not set operator cancellation or
issue `/cancel all`. Sender journals remain resumable. Secondary pipeline cleanup
failures are recorded without replacing the remote failure; ambiguous drain still
retains ownership. Third-party backends ignoring the stop signal retain their own
blocking-call limits. RESULT decoding rejects contradictory status/code pairs.
Already issued firmware/RF operations are outside the legacy host drain guarantee.

Local automated checkpoint for stages 1–4: 494 tests passed with an isolated device
cache. Stage 4 source is retained at `f9c8a8f`. Physical validation remains separate.
Same-process retry reuses the failed record and event cursor after its worker settles;
claim/checkpoint failure preserves the old terminal history. Lease rollback failure
retains admission instead of allowing another transfer. Old RESULT/MISSING/cancel
state is cleared only after the new attempt is admitted. FT1 v1 has no attempt epoch;
a delayed negative RESULT can therefore safely fail a later same-ID attempt.

Lost local echo after real delivery and discarded unresolved pipeline tickets block
new legacy BINARY submissions with `local_tx_unsettled`. A connection generation or
READY line alone does not settle the old firmware queue; observed controller reset
is required. This condition is intentionally not added to the automatic recoverable
set. RESULT/control/repair work shares one absolute completion deadline, including
nested local recovery; blocking third-party legacy adapters retain their own limits.

RX restore performs durable/runtime rollback before releasing a claimed identity
if checkpoint or runtime publication fails. Failed rollback keeps admission owned;
it cannot expose a phantom receiving operation as safely released.
Remote integrity/quarantine/invalid_metadata identity failures mark sender journals
terminal before settlement; a new explicit send allocates a fresh ID. A failed
terminal-journal checkpoint holds admission rather than blindly reusing the ID.
Timeout/restart/lost outcome remain resumable. Early META rejection retains remote_code.

Final-name selection and publication are coordinated by a POSIX namespace lock.
Other writers skip names reserved by retained publishing manifests, including crash
before the final file exists. Exclusive hard-link publication never overwrites a
final name; the temporary name is then removed. Both names are on the same filesystem.
The durable publishing destination remains fixed through restart and tombstone.

## Same-process FT1 recovery

An active FT1 sender treats these BINARY failures as recoverable local-node lifecycle
failures:

```text
local_tx_unknown
local_disconnect
local_controller_reset
```

Recovery is bounded by an overall deadline, currently 60 seconds, with a short retry
interval. It is not a fixed small replay count.

While recovering:

```text
current FT1 message is preserved
later DATA does not advance
state = recovering_local_node
the exact same idempotent META/DATA/END may be replayed
```

Relevant structured events include:

```text
local_recovery_started
binary_send_replay
local_recovery_resumed
local_recovery_failed
```

Cancellation and close remain responsive. Exhausting the recovery deadline produces a
stable failure rather than an unbounded hang.

Receiver-side same-process timeout no longer destroys resumable state. A matching META
can reopen retained durable state and continue the same transfer.
If it arrives while the previous terminal attempt is still draining/releasing
ownership, identical META replays are coalesced and deferred until the complete
settlement finishes, including recursive context cleanup. RX remains available.
Unsettled ownership after drain/release failure, or another active transfer, yields
`busy` rather than an identity conflict; retained chunks remain available for resume.
Failure to queue a deferred replay is recorded as `meta_replay_failed`; a later
matching META can retry admission. Close never reopens a deferred transfer.
Closing retained runtime history while ownership or terminal settlement is still
active returns `file_transfer_active`; the record remains available until safe
retirement. Unresolved ownership requires session close.

## Durable state location

Persistent FT1 state is stored below the configured receive directory:

```text
<receive_dir>/.serialterminal-state/
    incoming/
    outgoing/
    completed/
```

The receive directory must therefore remain the same across process restarts for the
same persisted state to be discovered.

The store uses schema version 1 and bounded cleanup policy. Current defaults retain a
bounded number/age of incoming, outgoing and completed records and bound total partial
storage.

## Receiver durable partial state

The receiver retains a stable hidden `.part` file plus an incoming manifest containing
META identity and the durable received-chunk ranges.

The manifest is authoritative for what may be skipped after restart. File size alone
is never proof that a chunk is durable.

Checkpoint ordering follows a safe-lag rule:

```text
write DATA bytes
-> fsync .part
-> atomically replace/fsync manifest with advanced received ranges
```

An active-META RESUME first forces a successful checkpoint, so its cursor cannot
advance beyond persisted bytes and ranges. A checkpoint failure prevents that cursor
from being sent.

If a crash happens after bytes are written but before the manifest advances, the sender
may retransmit those bytes. That is safe because duplicate DATA for the same
transfer/chunk must be identical and is idempotent.

Agent EOF also uses the manager suspension path, preserving receiver partial bytes
and the sender journal. It must not first invoke explicit cancellation, which discards
receiver partial state. The same distinction applies when checking shutdown evidence: a
retained manifest must reference existing bytes.

Receiver idle timeout releases current runtime ownership and records suspended durable
state rather than deleting the partial transfer. Runtime history may still surface
`remote_sender_timeout`; that does not mean the durable partial was discarded.

Durable state and final/tombstone paths reject unsafe symlink/path substitution. A
symlinked or dangling expected `.part` path is not followed outside the receive
directory.

## Completed tombstones

The receiver uses one chosen destination throughout publication:

```text
verify wire and original hashes/sizes
-> fsync final bytes
-> durable publishing intent with chosen destination
-> rename final bytes to that destination
-> fsync destination directory
-> durable completed tombstone
-> RESULT OK
-> partial/manifest cleanup
```

A restart reconciles an existing verified destination or reuses the retained intent
when publication has not happened. It never chooses a second destination for an
accepted intent. A failure to submit RESULT after the durable commit leaves local
completion intact. Completed replay verifies and persists that same commit again;
it does not publish a second copy. Cleanup failure does not revoke the commit.

On POSIX, file/directory fsync errors stop advancement. The durability model assumes
atomic rename and a filesystem/storage stack honoring fsync; automated fault
injection is not a physical power-loss test. Non-POSIX platforms retain the existing
best-effort directory fallback and do not claim the same power-loss guarantee.

This covers the case:

```text
receiver verifies + publishes file
receiver sends RESULT OK
sender/process dies before observing RESULT
```

A later matching transfer replay can recover completion semantics without publishing a
second copy or resending the full file.

## Sender journal

The sender persists enough identity to prove that a restart refers to the same logical
transfer, including:

```text
transfer_id
source path
filename
original size + SHA-256
wire size + SHA-256
compression
chunk size
status
```

`file_send_start(path)` remains the explicit operator/API trigger. SerialTerminal does
not automatically start old transfers merely because it found journals at startup.

For a matching journal, source content is revalidated before the old `transfer_id` is
reused. Filesystem mtime/inode are not sufficient proof.

If source content changed, the old transfer identity is not reused. A new transfer may
start with a new ID; changed bytes are never silently sent under the retained old
identity.

If more than one valid resumable journal matches the same source, SerialTerminal does
not guess. `file_send_start` fails with:

```text
ambiguous_resume_state
```

and reports the candidate transfer IDs.

Symlinked journal manifests are not trusted.

## Deterministic compression

Preparation reads the source once into independent raw and gzip temporary files,
then selects the smaller representation. DATA and repair read only the selected
snapshot, including Compression.NONE; editing the user file afterwards cannot
change the prepared bytes. Temporary snapshots are removed after the attempt.
Restart still requires an unchanged source, reconstructs a new snapshot and verifies
its wire size/hash/compression/chunk size against the retained journal before reuse.

When gzip is selected, the resumable path creates a deterministic wire stream using a
stable gzip header (`mtime=0`, empty embedded filename). On restart it rebuilds the
wire stream and verifies wire size/hash/compression/chunk size against the sender
journal before reusing the transfer identity.

A mismatch produces a stable resume failure rather than continuing under an invalid
identity.

## RESUME wire extension

The original TODO_037 baseline used version1 with an optional RESUME message.
The current recursive coordinator uses version3 with the same RESUME payload:

```text
MAGIC   = b"FT"
VERSION = 3
RESUME  = message type 6
```

`RESUME` carries:

```text
transfer_id
next_chunk : uint32
```

The receiver sends the earliest chunk it cannot prove durable:

```text
no durable state             -> RESUME_FROM 0
0..816 durable               -> RESUME_FROM 817
0..816 + 818..900 durable    -> RESUME_FROM 817
all DATA durable             -> cursor at chunk_count / proceed to END semantics
```

This is intentionally a coarse restart cursor. It is not a full arbitrary-range SACK.

## META-driven resume flow

Persistent restart flow is:

```text
sender file_send_start(path)
-> matching sender journal revalidated
-> same transfer_id
-> META

receiver
-> NEW / PARTIAL / COMPLETED / conflict decision
-> RESUME_FROM earliest receiver-proven missing chunk

sender
-> seek to requested chunk
-> DATA suffix
-> END

receiver
-> full missing-list service file if holes remain

sender
-> selective repair DATA
-> END

receiver
-> RESULT OK after final verification/publication
```

Only receiver-proven durable state may advance the restart cursor. Sender memory that
"I sent through chunk N" is not proof that the receiver durably owns those chunks.

## MISSING remains final exact repair

END/full-list/RESULT is the current final exact repair contract. A verified full
list drives selective parent repair; the list itself may require recursive repair.

Wrong-length DATA is discarded with `chunk_rejected` while the partial file and
valid chunk bitmap remain intact. Such a DATA does not advance a durable resume
cursor. END/MISSING requests that index if it is still absent. A wrong-length
replay of an already stored chunk does not erase the stored copy. Final wire and
original SHA-256 verification remains mandatory.

Earliest-missing resume may retransmit already-durable chunks after the first hole.
That is acceptable. After END, the existing MISSING range mechanism requests exact
remaining holes and the sender selectively repairs them.

There is still no per-DATA FT1 ACK and no firmware file-aware ACK.

Full pre-DATA arbitrary missing-range SACK/pagination is an optional future
optimization, not part of TODO_034–037 closure.

During local controller boot, control/idle deadlines can use the last verified
PHY without a new command. This prevents an idle sweep from converting expected
boot into receiver_failed. Actual RF admission still requires READY and fresh
readback; unknown PHY or a changed config cannot reuse an old estimate.

## Current peer contract

Both endpoints use the current recursive FT1 protocol. Old peers are not an acceptance
target for this two-node experimental project. A missing RESUME still has a bounded
wait and falls back to a complete pass from chunk 0; this handles lost control on
current peers. The public manager derives the RESUME roundtrip budget from its opaque
transport timing capability instead of a fixed one-second radio wait.

ROOT and service-file control waits are independent. After failure, explicit retry
should start after both peers have settled the previous operation. Retrying the same
ROOT ID while the remote child is still active can collide with that child's late
negative RESULT; the current protocol has no separate ROOT attempt identity.

Invalid `RESUME_FROM` outside the declared chunk count is rejected with
`invalid_resume_request`.

## Agent API operational contract

Use the existing high-level operations only:

```text
file_send_start
file_transfer_observe
file_transfer_cancel
file_transfer_close
```

Do not manually read/base64 the file, emit `/bin` chunks, or implement a per-DATA model
loop.

`file_send_start(path)` may return `resumed:true` when an existing sender journal was
selected. Resume/recovery lifecycle is available through the normal structured transfer
snapshot/events, including states/events such as:

```text
recovering_local_node
resuming
sender_resume_journal_restored
remote_resume
resume_started
resume_handshake_fallback
resume_state_restored
transfer_suspended
local_recovery_started
local_recovery_resumed
```

Normal progress monitoring remains coarse-grained (`status` every few seconds is
sufficient). Do not drain an event window per DATA chunk during active transfer.

Do not delete `.serialterminal-state` or `.part` files as an automatic recovery action.
On `ambiguous_resume_state`, stop and surface the ambiguity; do not pick/delete a
journal silently.

## Validation checkpoint

Automated implementation/hardening checkpoint:

```text
SerialTerminal: dev_tui@2952d1e09ad550a60b25418dd10bb49e4aa73a4c
GitHub Actions: 37158286307 SUCCESS
pytest:         400 passed
```

The automated matrix covers controller lifecycle behavior, bounded local FT1 recovery,
receiver restart state, sparse/out-of-order durable ranges, safe-lag checkpoints,
sender restart identity, deterministic gzip reconstruction, old/new host
compatibility, completed tombstones, invalid resume cursors, ambiguous sender journals,
and symlink/dangling-symlink resume-state hardening.

## Physical validation status

Physical validation is still OPEN. Do not infer hardware PASS from the automated
checkpoint.

Required follow-up includes at least:

```text
USB Chatter node:
active transfer -> deliberate controller reboot while tty may remain open -> recovery

BLE Chatter node:
active transfer -> deliberate reboot/disconnect/reconnect -> recovery

same-process FT1:
interrupt during META / DATA / END -> recover same transfer

persistent FT1:
interrupt transfer -> restart sender ST / receiver ST / both -> same transfer_id,
resume from receiver-proven state, exact final bytes/hash, no duplicate final publish

lost RESULT:
receiver completes/publishes -> sender misses RESULT/restarts -> tombstone completion
```

Record exact SerialTerminal SHA, firmware SHA, node identities, transport, transfer ID,
resume cursor, final hash and result for those runs.

## Protected local machine and outbox continuation — 2026-10-11

The experimental working tree composes one FT1 coordinator with bounded outbox,
RX and control queues. The full isolated-cache host suite passed 543 tests.
Protected local framing is defined in `CHATTER_MACHINE_PROTOCOL_V1.md` and negotiated
by the Chatter profile. LINK_OK proves the existing peer-node ACK, not remote storage.
Physical four-path/reconnect/reset/resume/performance gates remain separate.

On reconnect an idle receiver reopens its machine RX automatically. Outstanding old
requests remain guarded: same-epoch reconnect cannot erase unresolved tickets. Owned
host writes must settle; an observed controller reset or new protected WELCOME epoch
can invalidate the old node slots and permit explicit idempotent FT1 recovery. This
never completes the old ticket as successful and never issues a blind adapter SUBMIT.
A local-only HELLO/QUERY may recover evidence; absent proof fails visibly. Legacy
compatibility retains the weaker echo/firmware-queue limitations documented above.
Close finalizes discarded terminal jobs visibly while preserving published bytes and
completed tombstones; unresolved ownership is retained rather than falsely released.

The BLE-sender physical matrix exposed a missing local outcome with a 29-second
wait before QUERY. The client now queries the same epoch/request after an addressed
full-credit STATUS and 100 ms grace; credit alone never completes a ticket. This
is local cache recovery, not midstream RF repair.

A repeated WELCOME with the same live USB node epoch preserves the monotonically
increasing request counter. Only a fresh epoch resets it; the node outcome cache
is still authoritative after same-epoch reconnect. Regression was reproduced on
frozen v4 and fixed before v5 validation.

## FT1 host metadata bounds

Host metadata resource policy: received chunks are stored as canonical intervals,
not one dictionary entry per chunk. Defaults are65,536 received intervals and4 MiB
per JSON manifest; manager constructor overrides are `max_received_ranges` and
`max_manifest_bytes`. A fragment that would exceed the interval limit fails with
`storage_failed` before writing that DATA, preserving the useful partial and map.
Large manifest reads are bounded and oversized documents are not accepted/written.
LIST has at most `max_received_ranges + 1` ranges, validated before allocation;
service META size is bounded by that representation before decompression. These
limits do not cap sequential file size or the number of successful repair cycles.

Within a live ROOT each creator allocates monotonic child IDs from a random seed;
ROOT receiver uses odd IDs and ROOT sender even IDs. Durable IDs and live contexts
are skipped, and creation is protected by namespace lock plus outgoing lease.
This permits bounded replay history without reusing evicted child identities.

## Live cyclic partial retention

Cyclic retention runs on durable saves/checkpoints, admission and ownership release;
partial growth checks the shared logical byte budget before writing. Defaults:
7 days since state update,32 incoming,32 outgoing,64 completed tombstones and1 GiB
of `.part` files per receive directory. Count/TTL eviction skips active leases,
including another process and the pre-manifest window. Counts include live
identities without a manifest; a new admission fails explicitly if all slots are live.
Under byte-budget or filesystem-free-space pressure, the oldest inactive parts
and their manifests are removed automatically. ENOSPC/EDQUOT during an idempotent
write/checkpoint/publication is retried only after an actual eviction, so retry
is finite. The namespace lock covers capacity checks and the write across processes.
If nothing eligible remains, the transfer fails with storage_failed; it retains
the last useful partial and received proof. Partial writes never advance that proof.
Final downloaded files and user source files are never eviction candidates.
No periodic cleanup timer or `/clean` command is added. Active data alone can
exhaust the budget; the1 GiB storage budget still applies to growing wire files.

## FT1 chunk-space admission

META-derived chunk_count is computed with integer ceiling division and must fit
0..0xffffffff, matching END.chunk_count and RESUME.next_chunk. Invalid wire_size
or chunk_size is rejected before RX records, leases, part files or recursive frame
admission with RESULT invalid_metadata. The sender checks its actual prepared
wire stream before journal/META and reports invalid_metadata if unrepresentable.
Exactly0xffffffff chunks is representable (last DATA index0xfffffffe); larger
counts are rejected without allocating a chunk bitmap. No smaller protocol file
limit or new wire layout is introduced; separate storage/RAM budgets still apply.

## Outgoing peer binding

Outgoing journals and leases are scoped by a stable `peer_key`, stored in each
journal and represented by a SHA-256 filename prefix. Agent uses the selected
`open.device_key`; TUI uses the selected transport's device_key. Generic layers
pass an opaque identity string and do not recognize controller names or key
prefixes. In the fixed two-radio topology this binds work to the local radio path;
it does not discover or authenticate a remote RF peer. Changing remote topology
requires a new binding rather than assuming this key proves remote identity.
The same explicit key supports reconnect/process-restart resume; different keys,
including USB/BLE paths with distinct keys, never merge automatically.

Candidate selection, journal update and deletion verify the binding. Two peer
keys can use the same source and transfer_id without sharing a journal or lease.
Same-key concurrent owners of one identity are rejected until the lease releases.
Global outgoing count/TTL still applies across namespaces and preserves live
scoped leases. Old unbound journals are retained for normal retention/inspection
but are not automatically assigned to a peer. Standalone managers without an
explicit key get a per-instance volatile binding: same-instance retry works,
but another instance cannot claim that anonymous sender journal for restart resume.
A cancellation that cannot safely delete its bound journal reports
local_ownership_unsettled and keeps admission until close rather than deleting
foreign state. Incoming wire layout and firmware behavior are unchanged.
