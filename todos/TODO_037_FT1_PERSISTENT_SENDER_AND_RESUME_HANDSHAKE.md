# FT1 persistent sender journal and resume handshake TODO

TODO-ID: TODO_037
Status: IMPLEMENTED / PHYSICAL VALIDATION OPEN
Parent: `TODO_033_FT1_RESUMABLE_TRANSFER_AND_CONTROLLER_RECOVERY`
Depends on: `TODO_036_FT1_PERSISTENT_RECEIVER_RESUME_STATE`

## Current implementation status

Automated end-to-end persistent resume is implemented. `file_send_start(path)` remains the explicit trigger; when exactly one valid unchanged-source sender journal matches, SerialTerminal reuses the same `transfer_id`, rebuilds/verifies identical wire representation, sends META and waits for receiver-proven resume state. Multiple matching journals fail explicitly with `ambiguous_resume_state`; changed source content is never sent under the retained old transfer identity.

FT1 v1 now has a backwards-compatible optional `RESUME` message type 6 carrying `next_chunk:uint32`. NEW returns 0, PARTIAL returns the earliest receiver-proven missing chunk, completed tombstones avoid duplicate final publication, and existing END/MISSING/RESULT remains the exact final repair/completion path. New sender -> old receiver uses a bounded timeout then full pass from 0; old sender ignores the optional RESUME from a new receiver. Firmware ACK is unchanged.

Current exact protocol/operational contract is documented in `FT1_RESUME.md`.

Automated implementation/hardening checkpoint:

```text
SerialTerminal: dev_tui@2952d1e09ad550a60b25418dd10bb49e4aa73a4c
GitHub Actions: 37158286307 SUCCESS
pytest:         400 passed
```

Automated coverage includes unchanged-source sender restart, receiver restart state, same transfer ID, sparse earliest-missing resume, deterministic gzip rebuild, invalid cursor rejection, old/new host compatibility, completed tombstone replay, source change, corrupt state, multi-journal ambiguity and resume-state symlink hardening.

**Two-node physical persistent-resume validation has NOT been run.** Sender ST restart, receiver ST restart, both-process restart, sparse physical resume, lost RESULT/tombstone replay and source-change operator cases on actual nodes remain OPEN. Therefore this TODO is not CLOSED.

## Purpose

Complete end-to-end persistent FT1 resume by adding sender-side durable transfer identity/source state and a META-driven resume handshake that consumes the receiver durable state created by TODO_036.

This TODO is the point where persistent resume becomes a complete application protocol:

```text
sender journal
+ receiver durable partial/tombstone state
+ same transfer_id after restart
+ META -> receiver resume decision
+ sender restart from receiver-proven state
+ existing END/MISSING/RESULT completion semantics
```

The preferred first implementation resumes from the receiver's **earliest missing chunk** and retains existing `MISSING` ranges as the exact final selective-repair mechanism.

## Architecture boundary

Resume remains entirely at the FT1 application layer.

Do not modify:

```text
firmware USER ACK format
firmware USER sequence semantics
firmware knowledge of transfer_id/chunk_index
```

Firmware still transports opaque BINARY USER messages reliably one transaction at a time.

FT1 owns file identity, persistence, resume cursor, MISSING and RESULT.

## Sender persistent journal

### Stable transfer identity

A restarted sender must be able to resume the **same logical transfer** with the same `transfer_id` when the source still matches.

Persist enough sender state to validate that claim.

At minimum journal equivalent fields for:

```text
schema_version
transfer_id
source reference/path
original_size
original_sha256
compression selection
wire_size
chunk_size
wire_sha256 / END identity when known
filename / META identity
created/last_activity metadata
state
```

Filesystem metadata such as mtime/inode may be used as optimization hints, not as sole proof of content identity.

### Source revalidation

Before reusing an old transfer ID after restart, prove the source still represents the same FT1 content.

If source content changed, disappeared, became unreadable or produces conflicting META/wire identity:

```text
DO NOT resume under old transfer_id
```

Return a stable local failure or require an explicit new transfer according to the final API contract.

Never silently send changed bytes under an existing transfer identity.

### Deterministic wire representation

Current source preparation uses deterministic gzip (`mtime=0`). Preserve deterministic reconstruction so the sender can rebuild identical wire bytes after restart when compression is selected.

After rebuild, validate expected wire size/hash before using the old transfer ID.

The implementation may cache/retain prepared wire data for performance, but persistent cache lifecycle and cleanup must be bounded and explicit.

## Sender journal lifecycle

The sender journal should transition conceptually through states such as:

```text
prepared / active
suspended
awaiting_remote_result
completed
failed/non-resumable
expired/cleaned
```

Exact names may differ.

Do not delete sender identity merely because a local transport/controller outage occurred.

Keep enough state until application-level completion is proven by remote RESULT or a deterministic terminal decision is made.

## Resume discovery / operator contract

Do not automatically start sending files in the background merely because SerialTerminal starts and finds an old journal.

Resume must have an explicit, understandable user/API trigger.

Possible final designs include:

```text
file_send_start(path) detects matching resumable journal and resumes
```

or:

```text
file_send_resume(transfer_id/path)
```

The exact API is to be selected during implementation, but it must avoid surprising implicit sends and must be deterministic for agents.

If `file_send_start(path)` can match multiple journals or source identity is ambiguous, fail/select explicitly rather than guessing.

## META-driven resume handshake

### Principle

Sender always establishes/resumes identity by sending the same idempotent META first.

Receiver evaluates durable state for that `transfer_id` and META identity.

Receiver must distinguish:

```text
NEW
    no matching prior state

PARTIAL
    matching suspended durable state

COMPLETED
    matching completed tombstone

CONFLICT
    same transfer_id but metadata does not match durable state
```

### Preferred initial response: earliest missing chunk

For NEW/PARTIAL, return FT1 application state equivalent to:

```text
RESUME_FROM chunk_index
```

where `chunk_index` is the earliest chunk receiver durable state cannot prove present.

Examples:

```text
no previous chunks       -> RESUME_FROM 0
chunks 0..816 present    -> RESUME_FROM 817
0..816 and 818..900 have -> RESUME_FROM 817
all chunks durable       -> resume cursor at end / proceed to END semantics
```

Exact message type and byte encoding must be explicitly designed and versioned before implementation.

Do not overload `RESULT` in an ambiguous way and do not overload firmware ACK.

If an existing FT1 message can cleanly encode the same contract without semantic confusion, document the decision and add compatibility tests. Otherwise add a dedicated resume/control message.

## Why earliest-missing is the first implementation

The initial resume handshake intentionally favors simplicity/correctness over minimal duplicate traffic.

Example durable receiver state:

```text
0..816 present
817 missing
818..900 present
```

Receiver returns:

```text
RESUME_FROM 817
```

Sender may retransmit 818..900. Receiver already guarantees identical duplicate DATA is harmless.

After resumed suffix transmission:

```text
END
-> receiver computes exact remaining holes
-> MISSING ranges
-> sender selective repair
-> END
-> RESULT OK
```

This gives:

```text
resume speedup from durable prefix
+ exact correctness from existing MISSING repair
```

without requiring a complex bitmap/paged-SACK protocol in the first version.

## Completed receiver tombstone path

If receiver has matching completed durable state:

```text
META replay after sender restart
-> receiver recognizes completed transfer
-> sender receives completion/result semantics
-> no DATA retransmission
```

If protocol requires END replay before RESULT for consistency, that behavior must be explicit and bounded. The key requirement is that lost RESULT/process restart does not duplicate the final file or force full resend.

## No receiver state case

If sender has a resumable journal but receiver reports no durable partial state, behavior must be deterministic.

Preferred safe behavior is generally:

```text
same transfer_id + matching META
receiver starts from RESUME_FROM 0
sender resends from chunk 0
```

because the logical transfer identity/content is unchanged.

If implementation instead requires a new transfer ID in a specific conflict/expiry condition, that distinction must be explicit and must not silently fork identities.

## Protocol/versioning

Adding resume negotiation may change FT1 wire protocol semantics.

Before implementation choose one explicit compatibility strategy:

```text
bump FT1 VERSION
or
add a backwards-compatible optional message/feature negotiation with unambiguous fallback
```

Do not accidentally send a new message type to an old peer and infer behavior from silence unless the timeout/fallback contract is documented and tested.

Current project does not require backwards compatibility with old firmware, but FT1 is host-host protocol state and two hosts can still run different SerialTerminal revisions. Compatibility behavior therefore must be intentional.

## Interaction with same-process recovery

TODO_035 remains the fast path while process stays alive.

Persistent resume is entered only when state actually crosses a process-lifetime boundary or explicit suspended-journal workflow.

Do not route every short BLE reconnect through disk resume negotiation if in-memory transfer state remains valid.

## Interaction with receiver persistence

Receiver durable state from TODO_036 is authoritative for what can be skipped after sender restart.

Sender must never assume its own `chunks_completed` means receiver durably has those chunks.

Only receiver-proven resume state may advance the restart cursor.

This distinction is fundamental:

```text
sender remembers "I sent through 1000"
!=
receiver proves "0..1000 are durable"
```

## TUI behavior

When an outgoing resumable transfer is selected/started, expose enough information to distinguish:

```text
new transfer
resuming transfer <id>
waiting for receiver resume state
resuming from chunk N
receiver already completed
resume refused due source conflict
```

Normal progress should represent logical file progress, not bytes retransmitted including duplicates unless a secondary diagnostic explicitly exposes retransmit cost.

## Agent API behavior

Machine API must provide deterministic resume control and state.

Depending on selected interface, document exact schemas for either enhanced `file_send_start` or a new resume operation.

Agent-observable events should include equivalent states for:

```text
journal restored
source revalidation start/result
META resume probe sent
resume_from received
resume transmission started
resume conflict
receiver completed tombstone hit
final RESULT
```

Do not require per-chunk model/tool turns.

## Optional future file-level SACK optimization

Full pre-DATA missing-range SACK is **not required** for TODO_037 closure.

After earliest-missing resume is measured, a follow-up may optimize by returning exact missing ranges immediately after META and sending only those chunks.

That follow-up must remain bounded by the FT1 application MTU.

Do not silently add multipart/paginated MISSING state in TODO_037 unless explicitly promoted into scope with its own protocol/validation design.

## Scope

TODO_037 includes:

- sender journal schema/root/lifecycle;
- source identity revalidation;
- deterministic wire reconstruction/verification;
- explicit resume operator/API contract;
- same transfer_id reuse for same logical transfer;
- FT1 META resume negotiation;
- earliest-missing resume cursor;
- sender seek/start from receiver-proven chunk;
- receiver completed tombstone completion path;
- no-state and conflict behavior;
- protocol version/compatibility decision;
- reuse of existing END/MISSING/RESULT completion path;
- TUI/agent resume visibility;
- both-sides process restart tests;
- two-node physical persistent-resume validation.

## Non-goals

TODO_037 does **not** include:

- firmware source changes;
- firmware ACK file offsets;
- LoRa SACK;
- per-DATA FT1 ACK;
- mandatory exact missing-range SACK before DATA;
- MISSING pagination unless separately promoted;
- unbounded background auto-resume on program startup;
- trusting sender progress as receiver durability;
- silently reusing transfer_id for changed source content;
- unrelated throughput pipeline work.

## Recommended implementation slices

Likely commit sequence:

```text
1. sender journal schema/storage + source revalidation tests
2. deterministic wire rebuild/reopen behavior
3. FT1 resume message/version encoding + protocol tests
4. receiver META -> resume decision using TODO_036 durable state
5. sender resume cursor/seek state machine
6. completed tombstone/no-state/conflict flows
7. TUI + agent API resume UX
8. end-to-end restart integration + docs
```

Keep protocol encoding changes isolated/reviewable from filesystem journal code where possible.

## Implementation checklist

- [ ] define sender state root/schema/version;
- [ ] persist transfer_id and full source/META identity;
- [ ] implement strict journal parsing/atomic update;
- [ ] define journal cleanup/TTL/count policy;
- [ ] revalidate source content before old transfer_id reuse;
- [ ] rebuild/verify deterministic compressed wire stream when needed;
- [ ] select explicit resume API behavior;
- [ ] design/version FT1 resume negotiation message;
- [ ] encode/decode exact resume message with payload-capacity validation;
- [ ] receiver maps META to NEW/PARTIAL/COMPLETED/CONFLICT;
- [ ] receiver computes earliest missing from durable received state;
- [ ] sender waits for bounded resume response;
- [ ] sender seeks to requested chunk and resumes DATA;
- [ ] duplicate suffix chunks remain logically harmless;
- [ ] END continues to drive exact MISSING repair;
- [ ] completed tombstone returns completion without duplicate final publish;
- [ ] no-state path deterministically resumes from zero or documented equivalent;
- [ ] source/META conflict returns stable failure;
- [ ] preserve same-process TODO_035 fast path;
- [ ] expose resume state in TUI/agent API;
- [ ] update FILE_TRANSFER.md / AGENT_API.md / agent skill;
- [ ] record exact implementation and validation checkpoints.

## Automated validation matrix

### Sender journal

- [ ] journal round-trip;
- [ ] crash-safe/atomic update;
- [ ] source unchanged -> resumable;
- [ ] source contents changed -> old transfer_id rejected;
- [ ] source missing/unreadable -> stable failure;
- [ ] mtime changes but content identical -> behavior according to content identity contract;
- [ ] deterministic gzip rebuild matches previous wire size/hash;
- [ ] corrupted journal rejected safely;
- [ ] expired journal cleanup bounded.

### Resume protocol

- [ ] NEW -> resume from 0;
- [ ] contiguous prefix -> resume at first missing;
- [ ] sparse partial -> resume at earliest missing;
- [ ] all DATA durable but END absent -> skip DATA and continue completion path;
- [ ] COMPLETED tombstone -> no DATA retransmission;
- [ ] CONFLICT same transfer_id/different META -> stable protocol failure;
- [ ] invalid resume chunk > chunk_count rejected;
- [ ] resume response lost -> bounded META/control replay;
- [ ] duplicate resume response is idempotent;
- [ ] old/new protocol version mismatch follows explicit compatibility policy.

### Restart combinations

- [ ] sender ST restart, receiver ST remains alive;
- [ ] receiver ST restart, sender ST remains alive;
- [ ] sender then receiver restart;
- [ ] receiver then sender restart;
- [ ] both restart after contiguous prefix;
- [ ] both restart with sparse receiver durable state;
- [ ] sender restarts after receiver completed but before sender observed RESULT;
- [ ] host-side controller reboot plus later process restart still resolves correctly.

### Integrity

- [ ] final original bytes exact;
- [ ] final original SHA-256 exact;
- [ ] final wire SHA-256 exact;
- [ ] no duplicate final file;
- [ ] no transfer_id reuse with changed source;
- [ ] receiver durable state, not sender progress, determines skip cursor;
- [ ] existing MISSING repair still handles residual holes;
- [ ] RESULT remains sender completion truth.

## Physical validation

Required two-node scenarios using real SerialTerminal processes:

- [ ] transfer substantial file, restart sender ST, resume and complete;
- [ ] restart receiver ST, resume and complete;
- [ ] restart both ST processes, resume and complete;
- [ ] receiver has sparse partial state, sender resumes from earliest missing and final MISSING repair completes;
- [ ] receiver completed but sender lost RESULT/restarted -> quick completion without duplicate file;
- [ ] source modified after sender restart -> resume refused safely;
- [ ] exact final bytes/hashes for every success case;
- [ ] log exact transfer_id before/after restart to prove identity preservation;
- [ ] capture exact SerialTerminal SHA, firmware SHA, node identities and transport.

## Acceptance criteria

TODO_037 is CLOSED only when:

- sender transfer identity survives process restart under a durable journal;
- source identity is revalidated before transfer_id reuse;
- receiver durable state explicitly determines resume position;
- META-driven resume is versioned/unambiguous and bounded;
- sender resumes at earliest receiver-proven missing chunk;
- residual holes are repaired by existing MISSING semantics;
- completed tombstones avoid duplicate final publication/full retransmission;
- restart of either/both ST processes completes correctly in automated and physical tests;
- TUI/agent expose deterministic resume behavior;
- full CI and required two-node persistent-resume validation pass at exact recorded checkpoints.

Closure of TODO_037 completes the mandatory persistent-resume portion of umbrella TODO_033. Any later exact pre-DATA file-chunk SACK optimization should be measured first and tracked separately unless TODO_033 is explicitly extended.