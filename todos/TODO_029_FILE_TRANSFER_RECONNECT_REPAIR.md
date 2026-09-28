# File transfer reconnect repair TODO

TODO-ID: TODO_029
Status: IMPLEMENTED / PHYSICAL VALIDATION OPEN

## Purpose

Довести уже реализованный FT1 file transfer в SerialTerminal до корректного
восстановления после временного reconnect локальной ноды без повторной передачи всего
файла в обычном случае.

Текущий radio transport в этой задаче — только Chatter reliable USER + обычный ACK.
LoRa SACK не входит в TODO_029: это отдельный будущий проект, отдельная ветка и
отдельный design/validation workstream.

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

Therefore application chunk identity and end-to-end file verification remain required
above the current USER+ACK transport. No SACK behavior is assumed or implemented by
TODO_029.

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
    return repair_too_large; caller may explicitly start a new transfer
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
4. do not automatically enter a whole-file restart loop;
5. let the caller explicitly start a new file_send_start/new transfer_id when desired.

The implementation must define a bounded restart policy or surface a deterministic
failure requiring a new explicit send. It must never create an unbounded automatic
restart loop.

The essential v1 contract is:

~~~text
MISSING fits
    -> selective repair

MISSING does not fit
    -> repair_too_large
    -> explicit new transfer from zero if caller chooses
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

Current Chatter reliable USER ACK/retry owns lower-layer radio delivery.

FT1 owns only:

- transfer/chunk identity;
- on-demand missing-range repair;
- final verified RESULT.

This avoids running a second full stop-and-wait protocol above Chatter reliability.

## Current radio transport scope

TODO_029 is defined only for the current Chatter reliable USER + ACK transport.

Current BinaryUserTransport payload capacity is 200 raw bytes. FT1 consumes the
capacity advertised by the transport abstraction, but this TODO does not design,
simulate, implement or validate any internal radio SACK/batching protocol.

Any future LoRa SACK project must integrate later through a separately defined
transport capability and must not be pulled into the current file-transfer work.

## META / END replay after reconnect

A receiver-side BLE/USB disconnect may hide control messages as well as DATA. In
particular, receiver SerialTerminal may miss the original META or END even though
receiver firmware ACKed those BINARY USER transactions over radio.

Therefore META and END must be idempotent.

~~~text
repeat same META + same transfer_id
    -> preserve existing received DATA state
    -> create receive state if the original META was missed

repeat same END + same transfer_id
    -> if complete: RESULT OK
    -> if incomplete: compute current missing ranges and send one MISSING
~~~

Conflicting repeated META for the same transfer_id is a protocol error.

The sender must not wait indefinitely for RESULT after a radio-ACKed END. After a
bounded application timeout and once its local session is usable, it may replay the
same META and END as a control probe, then wait again for MISSING or RESULT. This
control replay must be bounded and must not become an infinite loop.

Sender-local ambiguous USB/BLE outcome is handled at the FT1 layer by retrying the
same idempotent application message after reconnect. Generic ManagedSession still
must not blindly replay tx_state=unknown.

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
repair failed: missing description exceeded MTU; explicit resend required
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
repair_too_large
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

Implemented on `dev_tui`:

- [x] BinaryUserTransport capability.
- [x] Chatter BINARY USER adapter.
- [x] FT1 META/DATA/END/MISSING/RESULT.
- [x] transport-derived DATA and MISSING capacity sizing.
- [x] compression none/gzip selection.
- [x] streaming hashing and receiver verification.
- [x] transfer_id + chunk_index receiver model.
- [x] out-of-order and duplicate DATA handling.
- [x] filesystem safety and atomic final publication.
- [x] TUI send/cancel/progress integration.
- [x] agent start/observe/cancel/close integration.
- [x] canonical missing-range calculation/coalescing.
- [x] incomplete receiver state retained after END when repair is possible.
- [x] complete missing set encoded into exactly one MISSING; no pagination.
- [x] selective resend of requested DATA chunks followed by repeated END.
- [x] repeated identical META and END are idempotent.
- [x] bounded META+END control replay while RESULT is absent.
- [x] stable `repair_too_large` when one MISSING cannot describe the full set.
- [x] bounded fallback policy: no automatic restart loop; caller explicitly starts a new transfer/new transfer_id.
- [x] in-memory transfer survives local ManagedSession reconnect while the process remains alive.
- [x] generic `tx_state=unknown` is not blindly resent; FT1 may replay the same idempotent message above the generic session boundary.
- [x] structured repair progress/events.
- [x] TUI exposes waiting/repair states and stable repair failure.
- [x] agent API exposes structured repair events without parsing human output.
- [x] FILE_TRANSFER.md / ARCHITECTURE.md / AGENT_API.md / active agent skill updated.

Implementation commits:

```text
9e8db12505963d4e51d4e96a0aaa989b8ad59ed3  file: add FT1 missing-range protocol
e8d435bd17f97e26c68bd54d93859ef956a40772  file: repair missing chunks after reconnect gaps
fa13e058dcc272209649d245e1389956d8d6bde9  test: fix file repair result import
6b17ed299e46e7b9176cdd5cdc09c2ef9f6b7090  file: recover ambiguous local binary delivery
e296fdeff84416b52d139cce0917904f15a084ce  file: expose repair state in tui and agent
```

## Validation

Protocol tests:

- [x] MISSING binary encode/decode round-trip.
- [x] one range.
- [x] multiple ranges.
- [x] adjacent missing IDs coalesce.
- [x] invalid/overlapping/out-of-range ranges reject.
- [x] exact current-MTU boundary.
- [x] one range set beyond current MTU returns deterministic no-pagination failure.
- [x] capacity comes from transport capability, not hard-coded 200.

Core/reconnect deterministic tests:

- [x] END with holes produces MISSING instead of immediate terminal failure when it fits.
- [x] sender resends only requested chunk IDs.
- [x] repaired transfer reaches RESULT OK and identical file bytes/SHA semantics.
- [x] duplicate repaired DATA remains idempotent.
- [x] repeated END is idempotent.
- [x] repeated identical META is idempotent; conflicting META is rejected.
- [x] receiver that missed original META recovers from bounded META+END replay.
- [x] receiver that missed original END recovers from repeated END.
- [x] absent RESULT triggers bounded control replay rather than an unbounded wait.
- [x] second repair round works when a repair DATA is missed.
- [x] oversized MISSING terminates with stable `repair_too_large`; no pagination/restart loop.
- [x] deterministic lossy transport simulates receiver-side local-notification gaps while sender delivery continues.
- [x] receiver can miss a contiguous range, receive later chunk IDs, then selectively repair the range.
- [x] same manager/process retains incomplete receiver state across the gap.
- [x] final END requests exactly the missing chunks.
- [x] sender-local ambiguous delivery replays the same idempotent FT1 DATA above generic session semantics.
- [x] generic session exposes per-TX outcome without changing its no-blind-retry `tx_state=unknown` policy.
- [x] waiting-for-result path recovers through bounded idempotent META+END replay.
- [x] process restart has no persistent-resume claim.

UI/API tests:

- [x] TUI renders `waiting_result`, `repair_requested` and `repairing` as explicit recovery states.
- [x] agent observe returns structured repair events.
- [x] agent request reader remains responsive while file-transfer observe is pending.
- [x] cancellation remains covered by existing bounded transfer tests.

Regression gates:

- [x] ordinary TEXT terminal tests unchanged/passing.
- [x] ordinary BINARY USER exact-byte tests still pass.
- [x] no-gap transfer still follows META -> DATA... -> END -> RESULT with no per-chunk FT ACK.
- [x] generic profile remains free of Chatter/file semantics.
- [x] `python -m compileall -q src serialterminal.py tools scripts` PASS in CI.
- [x] ruff/static analysis PASS.
- [x] `pytest -q` PASS: 277 tests at source checkpoint `e296fdeff84416b52d139cce0917904f15a084ce`.
- [x] GitHub Actions `36375238603` SUCCESS on exact source checkpoint.
- [x] source diff/deletion/function-definition review performed for each source commit; no unintended existing definitions removed.

Physical integration — still required separately:

- [ ] two hosts / one local node per host topology, or equivalent independent local-host visibility.
- [ ] receiver-local BLE disconnect during a multi-chunk file while receiver firmware remains on-air.
- [ ] confirm sender firmware continues receiving valid USER ACKs during the receiver-host gap when physically observed.
- [ ] receiver ST reconnects without process restart.
- [ ] selective repair requests only the missing file chunks.
- [ ] final received file SHA-256 equals source.
- [ ] exercise an oversized missing-range set and confirm `repair_too_large` with explicit fresh resend, never MISSING pagination.
- [ ] kill/restart SerialTerminal mid-transfer and confirm v1 starts a fresh transfer rather than claiming resume.

## Findings

The durable file identity remains:

```text
transfer_id + chunk_index
```

Temporary local USB/BLE/SPP disconnects can create an end-to-end file hole even when
the receiver firmware ACKed the corresponding radio USER. FT1 now detects that hole
from receiver chunk identity, requests the complete current missing set in one compact
MISSING message when possible, selectively resends only those DATA chunks, and repeats
END until RESULT or a bounded terminal failure.

Sender-local ambiguity is handled without weakening generic transport safety:
`ManagedSession` still does not blind-retry `tx_state=unknown`; it exposes generic
per-TX outcome and lifecycle-generation primitives, while FT1 replays only the same
idempotent application message.

## Known limitations

- Current Chatter application MTU is 200 raw bytes.
- MISSING v1 is exactly one application message; no pagination.
- Oversized missing-range sets fail with `repair_too_large`; full resend is explicit.
- No persistent transfer resume after SerialTerminal process death/restart.
- No simultaneous multiple transfers on one session.
- LoRa SACK is explicitly out of scope and is not a dependency of FT1 v1.
- Physical BLE reconnect behavior on the two real nodes is not yet validated.

## Result

Automated implementation checkpoint: `dev_tui@e296fdeff84416b52d139cce0917904f15a084ce`
GitHub Actions: `36375238603` SUCCESS
Automated tests: 277 PASS
Reconnect/MISSING repair: IMPLEMENTED / AUTOMATED VALIDATION PASS
Physical reconnect validation: NOT RUN
Additional firmware source work required: NONE
LoRa SACK: OUT OF SCOPE / separate future project
Status: IMPLEMENTED / PHYSICAL VALIDATION OPEN
