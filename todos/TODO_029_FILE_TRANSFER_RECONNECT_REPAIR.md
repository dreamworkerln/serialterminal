# File transfer reconnect repair TODO

TODO-ID: TODO_029
Status: PARTIAL

## Purpose

Довести уже реализованный FT1 file transfer в SerialTerminal до корректного
восстановления после временного reconnect локальной ноды без повторной передачи всего
файла в обычном случае.

Главный failure mode:

~~~text
remote sender
    -> LoRa DATA
    -> local receiver firmware
    -> radio USER ACK succeeds
    -> local firmware output
    X USB/BLE connection to receiver SerialTerminal is temporarily disconnected
~~~

Radio transport считает USER доставленным, но receiver Python не получил file chunk.

File transfer должен обнаружить такую дыру по application chunk identity и запросить
повтор только отсутствующих chunks.

Если описание всех текущих дыр не помещается в один application message текущего
transport MTU, FT1 v1 не пакетирует MISSING: файл передаётся заново с chunk 0 как
новый transfer.

## Current implementation checkpoint

Current branch checkpoint:

~~~text
dev_tui@cfa42f67dc248dfcefc783884cd93efd1e2e9195
GitHub Actions 36372713417 SUCCESS
compile PASS
static analysis PASS
complexity PASS
tests PASS
~~~

На этом checkpoint уже реализованы:

- generic BinaryUserTransport abstraction;
- Chatter profile binary USER adapter;
- local /bin BASE64 -> raw bytes mapping;
- [BINARY] BASE64 -> raw bytes receive mapping;
- link settlement through existing Chatter reliable USER telemetry;
- FT1 META/DATA/END/RESULT;
- uint64 transfer_id;
- uint32 DATA chunk_index;
- transport-advertised payload capacity;
- 184-byte FT1 DATA content under current 200-byte Chatter BINARY USER MTU;
- gzip-or-none streaming preparation;
- SHA-256 verification;
- out-of-order receiver storage;
- idempotent identical duplicate DATA;
- safe receiver filenames/temp storage/atomic final publish;
- TUI file-send/cancel/progress integration;
- structured agent file-transfer start/observe/cancel/close operations.

Current durable documentation explicitly says reconnect resume is not implemented.
Current protocol has no MISSING message. END with missing chunks currently terminates
the receive as a missing_chunks failure.

This TODO changes that v1 boundary for temporary local transport reconnect while the
same SerialTerminal process remains alive.

## Deployment topology invariant

Do not design this as if one SerialTerminal instance normally controls both radio
nodes.

Development may temporarily run two nodes on one PC, but real topology is:

~~~text
host A <-> local node A <------ LoRa ------> local node B <-> host B
   ST A                                                     ST B
~~~

Each SerialTerminal sees only its own local node/session.

File recovery must therefore be an end-to-end application protocol between ST A and
ST B, carried through the two firmwares. It must not depend on one coordinator having
direct visibility of both local USB/BLE connections.

## Firmware contract

Authoritative firmware-side design is tracked separately in:

~~~text
lora-sack-protocol
dev_chat_binary
chatter/todos/TODO_011_FILE_TRANSFER_TRANSPORT_REPAIR.md
~~~

Current firmware checkpoint used by this TODO:

~~~text
dev_chat_binary@259260589432d7fa429020ea82a3e47843d7b46e
Chatter CI 36368553637 SUCCESS
~~~

Current Chatter contract:

~~~text
BINARY USER application payload capacity = 200 raw bytes
BINARY USER uses the same USER session/seq + ACK/retry/dedup
base64 exists only on local host<->firmware text boundary
LoRa payload is raw bytes
~~~

SerialTerminal source work must not modify firmware from this TODO.

## Problem: link ACK is not end-to-end file delivery

Existing Chatter binary settlement proves:

~~~text
sender firmware received matching peer USER ACK
~~~

It does not prove:

~~~text
receiver SerialTerminal process consumed that BINARY USER
~~~

A receiver-local BLE/USB disconnect can therefore create file holes even though every
corresponding radio USER was ACKed successfully.

Future LoRa SACK has the same boundary:

~~~text
firmware-to-firmware delivery can succeed
while
firmware-to-host delivery can be temporarily absent
~~~

Therefore application chunk identity and end-to-end file verification remain required
above both transports.

## Target FT1 message set

Extend FT1 from:

~~~text
META
DATA
END
RESULT
~~~

to:

~~~text
META
DATA
END
MISSING
RESULT
~~~

All FT1 messages remain compact binary application payloads.

Do not use JSON on the BINARY USER radio payload. JSON/text is acceptable for logs,
agent responses or debugging presentation only.

## Stable DATA identity

Every DATA message already has:

~~~text
transfer_id : uint64
chunk_index : uint32
payload
~~~

Preserve that format/identity.

Receiver completeness is defined from the set of received chunk_index values, not
from an assumed contiguous stream offset.

Receiver remains idempotent:

~~~text
same transfer_id + same chunk_index + identical bytes
    -> harmless duplicate

same transfer_id + same chunk_index + different bytes
    -> protocol failure
~~~

## Receiver reconnect behavior

Transfer state remains in process memory while the SerialTerminal process is alive.

During a temporary receiver-local USB/BLE reconnect:

~~~text
receiver ST process remains alive
receiver local ManagedSession reconnects
peer firmware may continue receiving radio DATA and returning USER ACKs
receiver Python may miss those BINARY USER notifications
~~~

After reconnect, later DATA chunk IDs and END allow the receiver to compute the exact
missing set.

Example:

~~~text
have 0..100
missing 101..106
have 107..872
missing 873
have 874..1900
missing 1901..1904
~~~

Do not restart the file merely because the local transport reconnected.

## MISSING representation

MISSING represents missing chunk ranges compactly.

Use the existing FT1 common header containing transfer_id, followed by a compact binary
body.

Preferred v1 shape, consistent with current uint32 chunk indexes:

~~~text
range_count : uint8
repeated range_count times:
    start_chunk : uint32
    count       : uint32
~~~

A range (start=101,count=6) means chunks 101..106.

Zero count is invalid.

Ranges must be canonicalized before encoding:

- sorted ascending;
- non-overlapping;
- adjacent missing chunk IDs coalesced into one range;
- all referenced chunks inside the declared END chunk_count.

The exact implementation may use equivalent fixed-width binary packing if tests prove
the same contract, but do not replace ranges with verbose JSON.

## One-message MISSING rule

FT1 v1 supports exactly one application message for the complete current missing set.

No:

~~~text
MISSING part 1
MISSING part 2
MISSING part 3
~~~

No pagination/reassembly state.

Before sending MISSING:

~~~text
encoded = encode_missing(...)
capacity = BinaryUserTransport.payload_capacity

if len(encoded) <= capacity:
    send one MISSING
else:
    selective repair is not supported for this missing set
    restart the file from chunk 0 as a new transfer
~~~

Under current Chatter:

~~~text
capacity = 200 raw bytes
~~~

The 200-byte limit includes the FT1 common header and MISSING body.

The file-transfer layer must use the advertised transport capacity and must not
hard-code 200 or a future 32*200 value.

## Oversized MISSING fallback

If the complete current missing set cannot fit one MISSING message:

1. do not fragment MISSING;
2. terminate the current transfer cleanly;
3. communicate a stable application failure/result such as repair_too_large;
4. start/retry the file from chunk 0 as a new transfer_id;
5. do not loop indefinitely if the same condition repeats.

The implementation must define a bounded restart policy or surface a deterministic
failure requiring a new explicit send. It must never create an unbounded automatic
restart loop.

The essential v1 contract is:

~~~text
MISSING fits
    -> selective repair

MISSING does not fit
    -> whole-file retransmission from zero
~~~

## Sender repair behavior

On one valid MISSING for the active transfer:

~~~text
validate transfer_id
validate ranges against original chunk_count
re-read/reuse prepared wire representation
retransmit only requested DATA chunk_index values
send END again
wait for receiver MISSING or RESULT
~~~

Retransmitted chunks preserve the same file-level transfer_id and chunk_index.

They are new underlying binary USER operations and may therefore use new Chatter USER
sequence identities. File identity must not be confused with firmware USER identity.

## Repeated repair rounds

A MISSING request is never paginated, but the protocol may perform another repair round
if a later END still reveals missing chunks.

Each round independently obeys:

~~~text
entire current missing set must fit one MISSING message
~~~

This keeps recovery simple while allowing a repaired DATA message itself to be lost at
a lower/local boundary.

## Sender-local reconnect

If the sender's local USB/BLE connection reconnects while the SerialTerminal process
remains alive, preserve the active file transfer rather than silently creating a new
file transfer solely because the transport reconnected.

Generic ManagedSession transport semantics remain authoritative:

- known-safe queued transport work follows existing reconnect behavior;
- tx_state=unknown is not blindly retried by generic SerialTerminal;
- the file layer is allowed to rely on its idempotent transfer_id/chunk_index protocol
  and later MISSING/RESULT evidence to resolve file completeness.

If the sender reconnects while waiting for final receiver outcome, END may be repeated
for the same transfer_id as an idempotent end-of-stream prompt so the receiver can
recompute and return its current MISSING or RESULT state. Do not add a separate generic
transport STATUS protocol merely for this case.

Receiver handling of repeated END for the same live transfer must be idempotent.

## Process death boundary

No persistent/torrent-style resume in v1.

Required behavior:

~~~text
temporary local USB/BLE disconnect
+ same SerialTerminal process alive
    -> preserve in-memory transfer
    -> reconnect
    -> repair holes

SerialTerminal process crashes/exits/restarts before completion
    -> no resume contract
    -> start a new transfer from chunk 0
~~~

Do not add persistent received-bitmaps, transfer sidecars, database state or cross-
process resume as part of TODO_029.

Temporary/incomplete files must still never be published as completed files.

## No per-chunk application ACK

Do not introduce:

~~~text
DATA 17
FILE_ACK 17
DATA 18
FILE_ACK 18
~~~

Current transport:

~~~text
Chatter reliable USER ACK/retry
~~~

Future transport:

~~~text
LoRa SACK selective radio retransmission
~~~

Those own lower-layer radio delivery.

FT1 owns only:

- transfer/chunk identity;
- on-demand missing-range repair;
- final verified RESULT.

This avoids running a second full stop-and-wait protocol above Chatter reliability.

## Future LoRa SACK compatibility

Future LoRa SACK is expected to provide one larger opaque application message over a
batch of up to 32 radio packets instead of the current one-USER/200-byte message.

Do not encode a permanent 6400-byte assumption into FT1.

Required abstraction:

~~~text
BinaryUserTransport.payload_capacity
        or successor generic application-message capacity
~~~

Current transport advertises 200.

Future LoRa SACK advertises its actual usable application MTU after its own
headers/overhead are defined.

The same one-message MISSING encoder then naturally fits more ranges.

Layering remains:

~~~text
FT1 external repair:
    host application <-> host application
    fixes missing file chunks / local host-link gaps

LoRa SACK internal repair:
    firmware <-> firmware
    fixes RF packet loss efficiently
~~~

Do not remove file chunk identity merely because SACK exists.

## TUI requirements

Existing file-transfer TUI remains profile-capability-driven and generic TUI code must
not branch on profile == chatter.

Extend user-visible progress/status to make recovery explicit.

At minimum show states/events equivalent to:

~~~text
sending
waiting for remote verification
repair requested: N chunks / R ranges
repairing
restarting from zero because repair description exceeded MTU
completed
failed
cancelled
~~~

Do not show COMPLETE merely because the final DATA/END was locally written.

If whole-file restart is automatic, make that visible to the operator. If the bounded
restart policy requires explicit user action, surface the stable reason clearly.

Receiver TUI must continue showing incoming filename/progress and must not publish a
final path before verification succeeds.

## Agent API requirements

Keep the high-level operations:

~~~text
file_send_start
file_transfer_observe
file_transfer_cancel
file_transfer_close
~~~

Do not require the agent to parse [BINARY] lines or manually encode chunks/MISSING.

file_transfer_observe must expose structured repair progress/events, including enough
information to distinguish:

~~~text
normal sending
waiting_result
missing_detected
repair_requested
repairing
whole_file_restart
completed
failed
~~~

Stable failures should include a machine code and phase.

The JSONL agent process must remain responsive while file transfer waits for reconnect,
MISSING or RESULT, using the existing long-running job/event architecture rather than
blocking the request reader.

## Ownership / generic-core boundary

Preserve ARCHITECTURE.md:

~~~text
FT1
    -> BinaryUserTransport
    -> profile-owned binary adapter
    -> ManagedSession
    -> physical Transport
~~~

Forbidden:

- ManagedSession learning transfer_id/chunk_id;
- generic Serial/BLE/SPP transports parsing FT1;
- generic agent dispatch branching on profile name;
- TUI branching directly on concrete Chatter commands for file protocol;
- firmware-specific BINARY text envelope escaping out of the Chatter profile adapter.

The generic core may expose reusable long-running job/cursor/ownership mechanics, but
file semantics remain in file_transfer and profile capability boundaries.

## Implementation

Already implemented at the current checkpoint:

- [x] BinaryUserTransport capability.
- [x] Chatter BINARY USER adapter.
- [x] FT1 META/DATA/END/RESULT.
- [x] transport-derived DATA payload sizing.
- [x] compression none/gzip selection.
- [x] streaming hashing and receiver verification.
- [x] transfer_id + chunk_index receiver model.
- [x] out-of-order and duplicate DATA handling.
- [x] filesystem safety and atomic final publication.
- [x] TUI send/cancel/progress integration.
- [x] agent start/observe/cancel/close integration.
- [x] current dev_tui CI PASS.

TODO_029 implementation work:

- [ ] add FT1 MISSING message type and codec.
- [ ] add canonical missing-range calculation/coalescing.
- [ ] keep incomplete receiver state alive after END when repair is possible.
- [ ] encode the complete current missing set into exactly one MISSING.
- [ ] reject/avoid MISSING fragmentation.
- [ ] implement selective resend of requested DATA chunks.
- [ ] repeat END after repair.
- [ ] handle repeated END idempotently for a live transfer.
- [ ] define stable repair_too_large result/error semantics.
- [ ] implement whole-file restart/new transfer_id fallback when MISSING does not fit.
- [ ] bound automatic restart behavior; no infinite loop.
- [ ] preserve active in-memory transfer over local ManagedSession reconnect.
- [ ] integrate tx_state=unknown with application repair rather than generic blind resend.
- [ ] add structured repair progress/events.
- [ ] expose repair/restart states in TUI.
- [ ] expose repair/restart states through agent API.
- [ ] update FILE_TRANSFER.md / ARCHITECTURE.md / AGENT_API.md / active agent skill to the final contract.

## Validation

Protocol tests:

- [ ] MISSING binary encode/decode round-trip.
- [ ] one range.
- [ ] multiple ranges.
- [ ] adjacent missing IDs coalesce.
- [ ] invalid/overlapping/out-of-range ranges reject.
- [ ] exact current-MTU boundary.
- [ ] one byte over current MTU selects whole-file restart; no pagination.
- [ ] capacity comes from transport capability, not hard-coded 200.

Core tests:

- [ ] END with holes produces MISSING instead of immediate terminal failure when it fits.
- [ ] sender resends only requested chunk IDs.
- [ ] repaired transfer reaches RESULT OK and identical SHA-256.
- [ ] duplicate repaired DATA remains idempotent.
- [ ] repeat END is idempotent.
- [ ] second repair round works when still needed.
- [ ] oversized MISSING abandons selective repair and starts/fails into bounded full restart policy.
- [ ] process restart has no resume claim.

Reconnect tests:

- [ ] deterministic fake transport simulates receiver-local disconnect while peer radio delivery continues.
- [ ] receiver misses a contiguous chunk range and later receives higher chunk IDs.
- [ ] same process reconnects and retains in-memory receiver state.
- [ ] final END causes one MISSING and only the missing chunks are retransmitted.
- [ ] sender-local reconnect preserves the active transfer.
- [ ] ambiguous local TX is not blindly retried by generic session semantics.
- [ ] reconnect while waiting for RESULT can recover through idempotent END/outcome replay.

UI/API tests:

- [ ] TUI shows repairing and whole-file-restart state.
- [ ] agent observe returns structured repair events.
- [ ] agent request reader remains responsive during reconnect/repair waits.
- [ ] cancellation remains bounded during sending/repair/wait-result.

Regression gates:

- [ ] ordinary TEXT terminal behavior unchanged.
- [ ] ordinary BINARY USER exact-byte tests still pass.
- [ ] existing file transfer without any gap still follows the fast path and adds no per-chunk FT ACK.
- [ ] generic profile remains free of Chatter/file UI.
- [ ] python -m compileall -q src serialterminal.py tools PASS.
- [ ] pytest -q PASS.
- [ ] GitHub Actions PASS on exact implementation checkpoint.
- [ ] final source diff/deletion/function-definition review required by AGENTS.md PASS.

Physical integration:

- [ ] two hosts / one local node per host topology, or an equivalent setup that does not rely on one ST seeing both nodes.
- [ ] receiver-local BLE disconnect during a multi-chunk file while receiver firmware remains on-air.
- [ ] confirm sender firmware continues receiving valid USER ACKs during the receiver-host gap when physically observed.
- [ ] receiver ST reconnects without process restart.
- [ ] selective repair requests only the missing file chunks.
- [ ] final received file SHA-256 equals source.
- [ ] force a missing-set description that exceeds current application MTU and confirm full restart from chunk 0 rather than MISSING pagination.
- [ ] kill/restart SerialTerminal mid-transfer and confirm v1 starts a fresh transfer rather than claiming resume.

## Findings

Current implementation already chose the correct long-term identity model:

~~~text
transfer_id + chunk_index
~~~

and accepts out-of-order/duplicate DATA. That means reconnect repair can be added
without redesigning file storage.

Current missing behavior is intentionally incomplete for the newly selected contract:
END with missing chunks currently fails the transfer instead of requesting repair.

The physical motivation is not RF loss alone. Receiver firmware can successfully ACK
radio traffic while its local host connection is unavailable. That makes file repair
an end-to-end application concern even when lower-layer radio reliability is perfect.

## Known limitations

- Current Chatter application MTU is 200 raw bytes.
- MISSING v1 is one application message only.
- No MISSING pagination.
- No persistent transfer resume after SerialTerminal process death/restart.
- No requirement for simultaneous multiple transfers on one session.
- Future LoRa SACK MTU is not yet frozen and must be consumed through transport capacity.
- Repeated severe local disconnects may still force whole-file restart when the missing
  set cannot be represented in one MISSING.

## Result

Current implementation base: cfa42f67dc248dfcefc783884cd93efd1e2e9195
Current validation: GitHub Actions 36372713417 SUCCESS
Reconnect/MISSING repair: OPEN
Physical reconnect validation: NOT RUN
Status: PARTIAL
