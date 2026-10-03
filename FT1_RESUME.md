# FT1 recovery and persistent resume

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

If a crash happens after bytes are written but before the manifest advances, the sender
may retransmit those bytes. That is safe because duplicate DATA for the same
transfer/chunk must be identical and is idempotent.

Receiver idle timeout releases current runtime ownership and records suspended durable
state rather than deleting the partial transfer. Runtime history may still surface
`remote_sender_timeout`; that does not mean the durable partial was discarded.

Durable state and final/tombstone paths reject unsafe symlink/path substitution. A
symlinked or dangling expected `.part` path is not followed outside the receive
directory.

## Completed tombstones

After verification and final publication, the receiver stores a completed tombstone
for the transfer identity.

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

When gzip is selected, the resumable path creates a deterministic wire stream using a
stable gzip header (`mtime=0`, empty embedded filename). On restart it rebuilds the
wire stream and verifies wire size/hash/compression/chunk size against the sender
journal before reusing the transfer identity.

A mismatch produces a stable resume failure rather than continuing under an invalid
identity.

## RESUME wire extension

FT1 remains protocol version 1 and uses a backwards-compatible optional message type:

```text
MAGIC   = b"FT"
VERSION = 1
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
-> exact MISSING ranges if holes remain

sender
-> selective repair DATA
-> END

receiver
-> RESULT OK after final verification/publication
```

Only receiver-proven durable state may advance the restart cursor. Sender memory that
"I sent through chunk N" is not proof that the receiver durably owns those chunks.

## MISSING remains final exact repair

The existing END/MISSING/RESULT contract remains authoritative for exact completion.

Earliest-missing resume may retransmit already-durable chunks after the first hole.
That is acceptable. After END, the existing MISSING range mechanism requests exact
remaining holes and the sender selectively repairs them.

There is still no per-DATA FT1 ACK and no firmware file-aware ACK.

Full pre-DATA arbitrary missing-range SACK/pagination is an optional future
optimization, not part of TODO_034–037 closure.

## Compatibility

RESUME is an optional FT1 v1 extension with bounded fallback.

New sender -> legacy receiver:

```text
META
legacy peer sends no RESUME
bounded resume wait expires
sender falls back to full pass from chunk 0
```

The public manager currently uses a 1 second resume-handshake timeout by default.

Legacy sender -> new receiver:

```text
new receiver may emit RESUME
legacy sender ignores the unknown optional control message
legacy sender continues ordinary META/DATA/END
```

Compatibility is therefore intentional host-host behavior; no firmware change is
required.

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
