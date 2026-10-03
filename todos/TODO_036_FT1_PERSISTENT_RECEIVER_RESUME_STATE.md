# FT1 persistent receiver resume state TODO

TODO-ID: TODO_036
Status: IMPLEMENTED / PHYSICAL VALIDATION OPEN
Parent: `TODO_033_FT1_RESUMABLE_TRANSFER_AND_CONTROLLER_RECOVERY`
Depends on: `TODO_035_FT1_SAME_PROCESS_PAUSE_RESUME`

## Current implementation status

Automated implementation is complete. Receiver durable state now lives under the configured receive directory in `.serialterminal-state/`, with schema-versioned incoming manifests, stable `.part` files, received-range checkpoints, suspended timeout semantics, completed tombstones and bounded cleanup.

Durability follows the safe-lag rule: `.part` bytes are fsynced before a checkpoint advances the durable received map; the manifest uses temporary write + file fsync + atomic replace, and the public durable store fsyncs the containing directory where supported. Restart logic uses the durable received map rather than file size, so sparse/out-of-order state is handled correctly.

Filesystem hardening rejects symlinked manifests, symlinked `.part` files, dangling expected `.part` symlinks, unsafe final/tombstone destinations and corrupt/conflicting state. Completed tombstones prevent duplicate final publication after lost RESULT/restart.

Authoritative current behavior and storage layout are documented in `FT1_RESUME.md`.

Automated checkpoint:

```text
SerialTerminal: dev_tui@2952d1e09ad550a60b25418dd10bb49e4aa73a4c
GitHub Actions: 37158286307 SUCCESS
pytest:         400 passed
```

**Physical receiver-process restart validation has NOT been run.** Retained partial state across an actual receiver ST restart on real nodes and tombstone behavior on the physical path remain OPEN. Therefore this TODO is not CLOSED.

## Purpose

Make the FT1 receiver retain resumable partial-transfer state across SerialTerminal process restart.

This TODO owns **receiver-side durability only**:

```text
.part wire data
+ durable manifest / received-chunk checkpoint
+ suspended-transfer lifecycle
+ completed-transfer tombstone
+ bounded cleanup
```

It does not yet implement sender journals or the final META-driven sender resume handshake; those belong to TODO_037.

## Motivation

Current FT1 receiver already writes DATA to a random-access `.part` file, but authoritative received-chunk state lives in RAM. If the SerialTerminal receiver process exits/restarts, the chunk map is lost and failure/close paths may delete the partial file.

Therefore the existing `repairing` mechanism is only same-process.

To support real resume, receiver state must survive:

```text
SerialTerminal crash/restart
host reboot if application-data storage survives
operator restart of ST
long temporary peer absence
lost final RESULT followed by process restart
```

## Existing invariants to preserve

Current FT1 receiver correctness relies on:

```text
transfer_id + chunk_index
random-access writes at chunk_index * chunk_size
identical duplicate DATA -> harmless
conflicting duplicate DATA -> protocol failure
END verification of exact wire SHA-256
materialization/decompression verification of original size + SHA-256
atomic final file publication
safe received filename handling
```

Persistent state must not weaken any of those checks.

## Persistence model

### Durable artifacts

Use one stable application-data location, not arbitrary current working directories.

Conceptually a retained incoming transfer has:

```text
<state-dir>/incoming/<transfer_id>/wire.part
<state-dir>/incoming/<transfer_id>/manifest.json
```

Exact paths/names may differ, but ownership and cleanup must be deterministic.

The receive/output directory for final user files remains conceptually separate from protocol-state storage unless the design explicitly documents a safe reason to colocate them.

### Manifest identity

Persist enough state to reject stale/conflicting resume attempts.

At minimum the durable manifest must encode equivalent information for:

```text
schema_version
transfer_id
full META identity:
    filename
    original_size
    wire_size
    compression
    chunk_size
    original_sha256
expected chunk_count
received chunk bitmap/ranges/checkpoint
wire part identity/path under controlled state root
last_activity / checkpoint metadata
state = receiving | suspended | completed-equivalent where applicable
```

Filename alone is never transfer identity.

`transfer_id` alone is also insufficient if META conflicts; same ID + conflicting metadata must remain a protocol error.

## Received-chunk checkpoint strategy

Do **not** rewrite/fsync a manifest for every ~227-byte chunk.

Use a coalesced policy such as:

```text
checkpoint every N newly accepted chunks
or every T seconds while dirty
plus important lifecycle boundaries
```

Exact values must be chosen by measurement/tests rather than guessed into protocol semantics.

### Safe lag rule

The durable received map may lag actual bytes already written into `wire.part`.

Example:

```text
chunk 100 written to wire.part
process crashes before manifest says chunk 100 present
```

After restart, receiver may request/reaccept chunk 100 again. This is safe because identical DATA replay is idempotent.

The reverse is **not** acceptable:

```text
manifest claims chunk present
but durable wire bytes are absent/corrupt
```

Write/checkpoint ordering must ensure the manifest never advances beyond safely persisted file state according to the selected durability contract.

Do not infer received chunks from file size alone; random-access/sparse writes can create holes.

## Crash-safe manifest updates

Use temporary-write + atomic replace or an equivalent crash-safe mechanism.

Required properties:

- malformed/truncated latest manifest does not cause publication of a file;
- old valid state can be recovered where feasible;
- no symlink/path traversal allows a manifest to point outside controlled state storage;
- schema/version mismatch is handled deterministically;
- unknown fields/version policy is explicit.

Whether manifest file data requires fsync and directory fsync depends on the selected durability guarantee, but the contract must be documented and tested rather than assumed.

## Suspended incoming transfers

A peer timeout or local process restart must no longer imply automatic deletion of a resumable partial.

Introduce durable state equivalent to:

```text
receiving
-> interruption / sender timeout / graceful process shutdown
-> suspended
```

A suspended transfer:

- retains partial bytes and manifest;
- releases active session ownership/lease;
- does not block unrelated later session activity forever;
- is discoverable by a later matching META/resume handshake;
- is subject to bounded retention/cleanup.

Current `remote_sender_timeout` behavior must be revisited so resumable state is not destroyed merely because the sender disappeared temporarily.

## Receiver restart restoration

On startup/session initialization, do not blindly reactivate every retained transfer as a live session owner.

Instead:

```text
scan/validate bounded state index
-> load resumable metadata as dormant/suspended records
-> claim active session ownership only when matching protocol work resumes
```

Corrupt or conflicting records must be quarantined/rejected/cleaned according to a deterministic policy, not silently trusted.

Startup scanning must have explicit resource bounds so thousands of stale files cannot create unbounded startup cost.

## Completed-transfer tombstones

Receiver must retain a compact durable record for recently completed transfers.

Motivation:

```text
receiver accepts all DATA
-> END verifies
-> final file atomically published
-> RESULT OK sent
X sender misses RESULT / sender ST restarts
-> sender later replays same transfer META/END
```

Receiver must be able to answer completion again instead of creating a second destination file or retransferring the whole file.

A completed tombstone must contain enough identity to prove the replay is for the same transfer, including equivalent META/END identity and final completion state.

Do not rely on final filename alone.

Tombstones also require TTL/count/resource cleanup bounds.

## Filesystem safety

Persistent resume expands the attack/error surface. Preserve and extend existing safety rules for:

```text
path traversal
symlink replacement
manifest path tampering
state-root escape
stale transfer IDs
corrupt JSON/schema
wrong partial file
unexpected file type
unbounded disk consumption
```

Any reopened path must be derived/validated inside the controlled state root.

Do not persist raw BINARY/base64 logs or source contents in JSON manifests.

Final publication still requires full FT1 integrity verification. A valid resume manifest is not proof that the final file is correct.

## Cleanup/resource policy

Define bounded retention for:

```text
suspended incoming transfers
partial bytes
completed tombstones
corrupt/quarantined state if retained
```

At minimum consider:

```text
max age / TTL
max count
max total retained bytes
explicit user/API delete/cancel
LRU/oldest cleanup only when not active
```

Never delete an actively owned transfer merely to satisfy background cleanup without a documented failure transition.

## TUI / agent visibility

Expose resumable receiver states sufficiently for diagnostics and later resume UX:

```text
receiving
suspended
restored dormant state
completed tombstone retained
expired/cleaned
persistent-state error
```

Do not flood normal TUI with per-checkpoint journal noise.

Agent/API may need bounded list/inspect/cleanup operations later; if added, schemas must remain explicit and must not expose arbitrary filesystem paths for mutation.

## Relationship to TODO_037

TODO_036 creates durable receiver truth.

It does **not** decide the complete sender resume protocol.

TODO_037 will consume this durable state through META-driven negotiation and will own:

```text
sender journal
source revalidation
resume_from / equivalent FT1 message
reusing same transfer_id after sender restart
both-sides restart flow
```

## Scope

TODO_036 includes:

- controlled persistent state directory;
- schema-versioned receiver manifest;
- durable `.part` ownership;
- coalesced received-chunk checkpoints;
- crash-safe manifest replacement/order;
- suspended-transfer state;
- restart restoration of dormant partial records;
- completed-transfer tombstones;
- bounded cleanup/TTL/count/bytes;
- filesystem/symlink/path safety;
- diagnostics/TUI/agent visibility as needed;
- automated crash/restart tests;
- physical receiver-ST restart validation.

## Non-goals

TODO_036 does **not** include:

- sender persistent journal;
- changing `file_send_start` to automatically resume;
- final META resume wire encoding;
- firmware ACK changes;
- per-DATA application ACK;
- LoRa SACK;
- MISSING pagination;
- optimizing transfer throughput;
- storing a second permanent full copy of every sender source.

## Recommended implementation slices

Likely commit sequence:

```text
1. persistent-state schema/root + pure validation tests
2. atomic manifest writer/reader
3. received-chunk checkpoint integration
4. suspended incoming lifecycle + restart restoration
5. completed tombstones
6. bounded cleanup/resource policy
7. API/TUI diagnostics + docs + integration tests
```

Do not combine schema, cleanup and protocol integration into one unreviewable commit.

## Implementation checklist

- [ ] select stable application state root and document ownership;
- [ ] define manifest schema/version;
- [ ] derive all state paths safely from controlled root + transfer identity;
- [ ] implement strict manifest parsing/validation;
- [ ] implement atomic manifest update helper;
- [ ] define durability/write ordering between `.part` bytes and received-map checkpoint;
- [ ] implement coalesced dirty/checkpoint policy;
- [ ] ensure checkpoint lag only causes harmless duplicate retransmission;
- [ ] persist/restore full META identity;
- [ ] persist/restore received chunk ranges/bitmap;
- [ ] convert ordinary peer timeout into suspended durable state where appropriate;
- [ ] release active transfer/session lease when suspended;
- [ ] restore dormant records after process restart without auto-claiming session;
- [ ] implement completed tombstones and identity validation;
- [ ] ensure replay cannot produce duplicate final publication;
- [ ] implement TTL/count/byte cleanup bounds;
- [ ] implement explicit cleanup/cancel semantics;
- [ ] guard against symlink/path/state-root escape;
- [ ] expose bounded diagnostics/state;
- [ ] update FILE_TRANSFER.md and relevant API docs;
- [ ] record exact implementation/validation checkpoints.

## Automated validation matrix

### Manifest/checkpoint

- [ ] create/read round-trip exact state;
- [ ] atomic replacement preserves last valid state under simulated interruption;
- [ ] malformed/truncated manifest rejected safely;
- [ ] unsupported schema version handled deterministically;
- [ ] received map never claims bytes beyond selected durability ordering;
- [ ] checkpoint lag causes duplicate DATA replay but no corruption;
- [ ] sparse `.part` file size is never mistaken for contiguous completion;
- [ ] identical duplicate DATA after restore remains harmless;
- [ ] conflicting duplicate DATA after restore remains fatal.

### Restart points

- [ ] restart after META only;
- [ ] restart after contiguous prefix of DATA;
- [ ] restart with sparse/out-of-order DATA received;
- [ ] restart immediately after a checkpoint;
- [ ] restart after `.part` write but before next manifest checkpoint;
- [ ] restart after all DATA but before END;
- [ ] restart during verification without publishing incomplete file;
- [ ] restart after final file publish but before RESULT is known delivered.

### Tombstone

- [ ] same completed transfer replay is recognized;
- [ ] same transfer_id + conflicting META rejected;
- [ ] replay does not create `filename (1)` duplicate;
- [ ] tombstone expiry/cleanup follows bounds;
- [ ] tombstone cannot point outside state/final-file policy.

### Cleanup/security

- [ ] max-age cleanup;
- [ ] max-count cleanup;
- [ ] max-byte cleanup;
- [ ] active records protected from background deletion;
- [ ] path traversal rejected;
- [ ] symlink substitution rejected/handled safely;
- [ ] corrupt record cannot publish a final file;
- [ ] startup scan bounded under many stale entries.

## Physical validation

At minimum:

```text
receiver ST starts receiving real file
-> receive substantial prefix
-> terminate/restart receiver SerialTerminal process
-> retained partial state survives
-> inspect/restore state correctly
```

Before TODO_037 exists, full automatic sender resume may not yet complete. Physical validation for TODO_036 therefore proves receiver durability and safe restoration; final end-to-end resumed completion is owned by TODO_037.

Also validate completed tombstone behavior with a controlled lost/replayed final control path once the sender-side test harness can replay matching META/END.

## Acceptance criteria

TODO_036 is CLOSED only when:

- receiver partial state survives process restart without trusting file size heuristics;
- durable map/file ordering is crash-safe by documented contract;
- suspended transfers release active ownership but remain resumable;
- corrupt/stale/conflicting state fails safely;
- completed transfer identity survives as bounded tombstone state;
- duplicate final publication is prevented;
- retention is bounded by explicit cleanup policy;
- automated restart/security/resource tests and full CI pass;
- physical receiver-process restart demonstrates retained valid partial state at an exact recorded checkpoint.

Completion of TODO_036 provides receiver-proven durable state for the sender journal and META resume handshake in TODO_037.