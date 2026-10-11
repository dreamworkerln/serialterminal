# TODO_041 deep review: FT1 selective repair, flow control, and recovery across SerialTerminal + Chatter

Review date: 2026-10-10

Reviewed revisions:

- `serialterminal/dev_tui` — `ea4a0d8362fa4163e181e4d5a878a6cf80c3a0be`
- `lora-sack/dev_chat_binary` — `1e7cdd53f0e9d8816fb416b6ed8c638f9888c8aa`
- Primary design document: `todos/TODO_041_FT1_FAILURE_RECOVERY_AND_RX_OBSERVABILITY.md`

This is a review/design document only. No production source was modified as part of this pass.

---

## 1. Executive conclusion

The direction selected by TODO_041 is fundamentally correct, but the clean architecture is slightly more precise than “SACK over LoRa”. There are three reliability layers and they must remain separate:

```text
firmware USER/ACK
    = hop-by-hop radio ARQ for one node-to-node USER transaction

FT1 FLOW
    = end-to-end durable cumulative ACK
      + selective NACK/missing ranges
      + receiver credit/backpressure

FT1 END + RESULT
    = end-to-end commit and integrity decision
```

The firmware ACK cannot serve as a file-transfer ACK. It only proves that the peer **node** accepted the RF USER identity. It does not prove that the peer SerialTerminal process saw the BINARY presentation, wrote the file bytes, fsynced them, or persisted the receiver manifest.

The current firmware makes this distinction especially important:

- a new USER is ACKed by the peer node before the host-side BINARY presentation is useful as durable FT1 evidence;
- duplicate firmware USER frames are ACKed but intentionally not presented to the host again (`lora-sack/chatter/src/Scheduler.cpp:1608-1627`);
- `TerminalIo::output()` ignores failures returned by the USB/BLE output queues (`lora-sack/chatter/src/TerminalIo.cpp:1371-1398`), so a radio transaction can succeed while the BINARY line never reaches the receiving ST;
- USB/BLE presentation therefore forms a real post-radio loss boundary, not merely a cosmetic logging boundary.

Consequently, the new FT1 layer is not optional polish. It is the layer that closes an actual correctness gap between “peer radio received it” and “peer application durably owns the chunk”.

The intended user behavior is achievable without changing the firmware wire protocol:

- transient node reboot: resume same FT1 transfer;
- USB unplug/replug: resume same FT1 transfer;
- BLE disconnect/reconnect: resume same FT1 transfer;
- recoverable radio fault: resume same FT1 transfer;
- radio becomes `RADIO_UNAVAILABLE`: retain FT1 state and wait for bounded local recovery/operator `/reboot`, then resume same transfer;
- lost/truncated/bad DATA: preserve every good chunk, pause original streaming when necessary, repair only holes, then continue original stream;
- receiving ST dies or disconnects while receiver node still ACKs radio traffic: sender must eventually stop because receiver-durable credit stops advancing;
- no infinite retry loops: every local recovery, FLOW query, repair exchange, and finalization has a bounded deadline/budget.

I would **accept the TODO_041 architecture direction**, but I would change several details before implementation. The most important corrections are listed below.

---

## 2. What the current system actually guarantees

### 2.1 Firmware USER/ACK is already reliable radio transport, not file reliability

Chatter uses one reliable USER transaction at a time. BINARY is only a flag on the normal USER frame; it is not a different reliability protocol.

The peer duplicate policy is explicit:

```text
NEW       -> ACK + present to CHAT/BINARY host output
DUPLICATE -> ACK + suppress host presentation
STALE     -> no ACK + no presentation
```

See `lora-sack/chatter/include/Reliability.hpp:111-180` and `lora-sack/chatter/src/Scheduler.cpp:1560-1660`.

A logical USER can consume up to five RF starts (`RELIABLE_USER_MAX_ATTEMPTS = 5`). Retries retain the same firmware USER identity. This solves radio ACK loss and radio-level duplicate suppression, but it does **not** solve loss between the receiver node and receiver ST.

### 2.2 Local sender `> [BINARY]` is not remote delivery evidence

On the sending node, BINARY presentation is emitted once after a successful physical transmit path and before completion of the remote ACK transaction (`Scheduler.cpp:781+`). SerialTerminal correctly treats it as local backpressure/controller evidence, not as an application delivery ACK.

This distinction is already documented in the ST Chatter adapter design and is correct.

### 2.3 Peer firmware ACK can succeed while receiver ST gets nothing

This is the strongest cross-repo finding in this review.

On peer receive:

1. firmware classifies USER identity;
2. for NEW and DUPLICATE it schedules ACK;
3. only NEW is presented to the local CHAT/BINARY output;
4. local output can fail after that radio decision.

`TerminalIo::queueUsbText()` is zero-wait: either the full formatted fragment enters the message buffer or it returns false (`TerminalIo.cpp:1065-1088`). `queueBleText()` similarly returns false when the entire message cannot be queued (`TerminalIo.cpp:1164+`). But `TerminalIo::output()` simply calls these methods and ignores their return values (`TerminalIo.cpp:1391-1398`).

Therefore this sequence is legal today:

```text
sender node RF USER
    -> peer node receives USER
    -> peer node schedules/sends ACK
    -> peer node attempts "< [...] [BINARY] ..."
    -> USB/BLE output queue rejects/drops it
    -> sender node considers USER successful
    -> receiver ST never sees the FT1 DATA
```

A retransmission of the **same firmware USER identity** is not sufficient: the peer sees a DUPLICATE, repeats ACK, and suppresses host presentation.

The repair must therefore be a **new ST `/bin` submission** carrying the same FT1 `transfer_id/chunk_index`. That becomes a new firmware USER identity while remaining an idempotent FT1 application message.

This is exactly why FT1 identity has to be above firmware USER identity.

---

## 3. What is already good in SerialTerminal

TODO_041 is not starting from zero. Several important foundations are already sound.

### 3.1 Stable application identity

FT1 already uses a stable `uint64 transfer_id` plus `chunk_index`. Sender journals preserve prepared source/wire identity. Receiver manifests persist sparse received ranges. This is the correct identity layer for replay after transport and controller failures.

### 3.2 Existing RESUME is correctly application-level

`protocol.py:102-109` explicitly states that `RESUME` is FT1 application flow control, not a firmware/radio ACK. It reports the earliest receiver-proven chunk the sender should transmit.

That is a good anchor for compatibility and process restart recovery. The new FLOW protocol should extend this concept rather than replace the hardened META/RESUME bootstrap.

### 3.3 Durable ordering in current receiver checkpointing

The current manager fsyncs the partial before atomically advancing the manifest. That ordering is correct: application-level progress must not be advertised before data is durable.

The new design must preserve this ordering even if checkpointing/control emission becomes asynchronous.

### 3.4 Same-process and process-restart resume already exist

Current code distinguishes active receive, suspended receive, sender journal recovery, and terminal records. Idle timeout can suspend and retain a partial rather than deleting it. Matching META can reactivate retained state. Sender process restart validates source/wire identity before resuming.

This machinery should remain the recovery anchor after node/USB/BLE/process restart.

### 3.5 Pipeline is already bounded to two

The current FT1 DATA pipeline intentionally keeps at most two local submissions outstanding. This is an excellent property for the proposed midstream repair scheme: when FLOW asks the sender to pause, at most two already-issued submissions need to be drained/accounted for.

---

## 4. Where current FT1 behavior is still wrong

### 4.1 Many receiver errors still destroy valid accumulated state

`core._fail_incoming()` unlinks the `.part` file (`core.py:1577-1587`). The resumable layer also removes the receiver manifest before delegating to the core failure path. Thus several errors that should be message-level or attempt-level failures can still erase useful progress.

The wrong-length DATA fix in `4ff115e` is a good first correction: a malformed-length chunk now emits `chunk_rejected` and is simply not marked received (`core.py:1281-1297`). Existing good chunks survive.

The same principle needs to be applied carefully to other message-level faults.

### 4.2 Conflicting same-index duplicate is currently destructive

If a chunk index already exists and the incoming same-length payload differs, current code raises `invalid_chunk` and falls into `_fail_incoming()` (`core.py:1299-1326`).

TODO_041 proposes broadly to invalidate/request repeat. I would **change that design contract**.

If two fully valid messages have the same `transfer_id/chunk_index` but different bytes, the receiver does not possess enough truth to know which copy is canonical. An in-message CRC only proves that each message arrived as it was sent; it does not tell which sender version is the legitimate source for this identity.

Recommended rule:

```text
wrong length / bad control CRC / bad DATA CRC
    -> reject this message only
    -> retain all previous durable state
    -> chunk remains missing if no valid copy exists

same index + byte-identical valid data
    -> idempotent duplicate, no-op

same index + different valid bytes
    -> never overwrite the durable copy
    -> retain partial + journal for diagnostics
    -> stop/suspend this transfer attempt as chunk_identity_conflict
```

Automatic resolution of two valid conflicting copies would require an independent per-chunk source truth, e.g. a persistent hash manifest/Merkle structure. `DATA_CHECKED` by itself is not sufficient for that case.

### 4.3 Bad END should not erase the partial

A mismatched `END.chunk_count` currently becomes a transfer failure (`core.py:1369+`) and can delete the partial.

META already established the expected transfer shape. A malformed/conflicting END should normally be treated as a rejected control message:

- retain partial;
- emit observable `end_rejected`;
- wait for/replay a valid END within the bounded control deadline;
- only after recovery budget/deadline exhaustion suspend/fail the current attempt while retaining resumable state.

The existing sender already treats META and END as idempotent control and replays them, so this fits the current protocol model.

### 4.4 Negative remote RESULT is not an immediate sender scheduling input

`feed_binary()` records RESULT/MISSING (`core.py:1034-1049`), but the DATA loops primarily poll `cancel_event`. The pipelined sender can continue feeding DATA after the receiver has already issued a negative RESULT. Physical evidence in TODO_041 confirms exactly that behavior.

The new scheduler must make remote terminal RESULT a top-priority event.

### 4.5 Receiver exceptions are insufficiently observable

`_rx_loop()` catches broad exceptions around handlers and continues without a durable error event (`core.py:1052-1073`). The idle sweep call is outside that handler guard, so an exception there can also kill the RX worker.

The Chatter adapter also intentionally swallows receiver callback exceptions so it does not kill the session notifier. That safety property is reasonable, but FT1 must receive an explicit error/event path rather than silently losing protocol work.

---

## 5. The right meaning of “SACK” here

The user intuition “something like SACK over the existing node protocol” is correct, but the proposed wire format in TODO_041 is actually closer to:

```text
cumulative durable ACK     = durable_prefix
selective NACK             = missing ranges below a proven frontier
receiver advertised credit = sender may not outrun durable_prefix by more than N
```

It does not need per-chunk positive host ACKs, and it should not send one host control frame for every DATA chunk.

This is preferable to classic per-packet application ACK because LoRa is half-duplex and reverse control airtime matters. A batched sparse status every several seconds / on gap pressure gives most of the reliability benefit without destroying throughput.

I would continue calling the design “SACK-like” informally, but internally name the semantics precisely: **durable cumulative ACK + selective missing ranges + credit**.

---

## 6. Proposed end-to-end state model

### 6.1 Sender states

A single FT1 coordinator should own scheduling. Do not grow more nested `_send_chunks_from()` fallback paths.

Recommended logical states:

```text
PREPARING
META_HANDSHAKE
NEGOTIATING_FLOW          optional; bounded fallback to legacy
STREAMING_ORIGINAL
WAITING_FLOW              periodic query / credit stop / receiver pressure
DRAINING_ISSUED           <=2 existing local submissions
REPAIRING
VERIFYING_REPAIR
RECOVERING_LOCAL          USB/BLE/controller/radio-local lifecycle
REHANDSHAKING             META/RESUME + fresh flow session after restart uncertainty
FINAL_DRAIN
WAITING_RESULT
COMPLETED
SUSPENDED_RESUMABLE
CANCELLED
FAILED_UNRECOVERABLE
```

Priority order for the scheduler should be explicit:

1. operator cancel / remote terminal RESULT;
2. local lifecycle recovery;
3. META/FLOW/control handshake;
4. repair work;
5. new original DATA.

`next_original` must be independent of repair cursor. Repair must never rewind/redefine original progress.

### 6.2 Receiver states

Recommended model:

```text
NO_TRANSFER
RECEIVING
CHECKPOINT_PENDING
FLOW_PENDING / REPAIR_REQUESTED
SUSPENDED
FINAL_VERIFYING
COMPLETED
FAILED_PRESERVED
CANCELLED
```

The receiver must separately track:

- bytes/chunks observed in memory;
- bytes/chunks proven durable;
- the highest sender-issued frontier it is allowed to reason about;
- currently requested repair batch.

---

## 7. Receiver truth: memory state is not durable state

TODO_041 correctly distinguishes durable progress conceptually, but implementation should make the split explicit.

Current `incoming.received` is not sufficient as the future FLOW truth because `_handle_data()` writes/flushes and immediately records it in memory (`core.py:1315-1324`), while durable checkpointing happens later in the resumable layer.

Recommended fields:

```text
memory_received_ranges
    chunks written/validated in this runtime

durable_received_ranges
    last receiver snapshot known to have:
      fsync(.part)
      + atomically persisted manifest

durable_prefix
    first chunk not proven durable contiguously

observed_frontier / sender_issued_frontier
    upper bound below which gaps are meaningful
```

If checkpointing is moved to a worker/outbox, use a snapshot barrier:

1. under a short state/storage lock, capture received-range snapshot + generation;
2. fsync `.part`;
3. atomically persist manifest for that captured snapshot;
4. only then publish the snapshot into `durable_received_ranges`;
5. FLOW may advertise only the durable snapshot.

Chunks that arrive while fsync is in progress may incidentally be flushed too, but they must not be *claimed* durable until included in a persisted manifest snapshot. Conservative lag is safe; optimistic durable ACK is not.

If fsync/manifest persistence fails, the old durable snapshot remains authoritative and no FLOW may advance.

---

## 8. Missing-range inference needs an authoritative sender frontier

The receiver must never request chunks the sender has not attempted yet.

Seeing a later valid DATA chunk proves earlier indexes could be holes, so proactive repair based on an observed later index is useful. But that is not enough for tail loss: if the final several original DATA submissions never reach ST, the receiver sees no later DATA from which to infer the missing tail.

Therefore sender FLOW_QUERY/checkpoint control should carry an **issued frontier**, e.g. `next_original` exclusive:

```text
issued_frontier = all original indexes < frontier have been attempted/submitted
```

The receiver computes missing ranges only below a proven frontier and echoes the `covered_frontier` used for that snapshot.

Sender validates every response:

```text
covered_frontier <= sender.next_original
all missing ranges end <= covered_frontier
```

This makes tail loss repairable and prevents stale/corrupt control from asking for future chunks.

For local write-outcome-unknown cases, “attempted/submitted” is the right semantics. It is safe for the receiver to request a repeat of an index that perhaps never left the local host.

---

## 9. FLOW negotiation needs explicit token ownership

TODO_041 proposes `flow_session`, `status_seq`, capability negotiation, and stale-reply defense. The idea is good, but the session-token creator should be unambiguous.

Recommended asymmetric handshake after the existing META/RESUME bootstrap:

```text
sender -> FLOW_HELLO / CAPS_REQUEST
          transfer_id
          fresh sender_nonce
          supported/requested features
          CRC32

receiver -> FLOW_WELCOME / CAPS_RESPONSE
            echo sender_nonce
            fresh receiver-generated flow_session
            selected features
            initial durable snapshot
            CRC32
```

Properties:

- old receiver ignores unknown optional message -> sender times out and falls back to legacy;
- old sender never sends HELLO -> new receiver remains legacy;
- receiver process restart always produces a fresh `flow_session`;
- sender restart always produces a fresh `sender_nonce` and renegotiates;
- stale control from a previous runtime cannot accidentally confirm a current repair.

The exact names can remain `CAPS` if preferred. The important part is **asymmetric request/response and a single defined creator of the flow-session token**.

I would also include a `request_seq` in FLOW_QUERY and echo it in direct responses. Proactive FLOW may use a flag or `request_seq=0`. `flow_session + status_seq` is already fairly strong, but explicit query correlation makes retries and observability much clearer.

---

## 10. Persist transfer semantics; do not persist runtime flow tokens

There are two different classes of state.

### Persistent transfer identity/semantics

These survive process restart:

- `transfer_id`;
- source/wire identity;
- chunk size;
- selected DATA encoding/integrity mode;
- required feature set if the transfer was created in a non-legacy mode.

### Ephemeral runtime control

These must be fresh after negotiation/restart:

- `flow_session`;
- `status_seq`;
- `request_seq`;
- active `repair_id`.

This distinction matters for `DATA_CHECKED`.

Existing retained 227-byte FT1 journals are legacy. They must remain legacy and resume with exactly the same chunking/representation.

For a new transfer, if resilient `DATA_CHECKED` is selected, persist that mode. Do not silently downgrade/change chunk representation halfway through a transfer after restart.

---

## 11. DATA_CHECKED should be part of the resilient mode

Radio CRC protects the RF frame. It does not protect everything after the peer node has decoded it: base64 generation, local output buffering, USB/BLE textual transport, line parsing, and application decode are another path.

A per-DATA application CRC is therefore useful.

Recommended split of negotiated capabilities:

```text
flow_v1
    durable progress + selective repair + credit

checked_data_v1
    per-DATA CRC32, validated before index/payload affects receiver state
```

For new/new peers, the default resilient mode should select both when possible.

At BINARY capacity 243 bytes:

- current DATA payload = 243 - 12 common - 4 index = 227 bytes;
- adding a uint32 CRC gives 223 bytes.

The throughput cost is small (~1.8% payload reduction relative to 227) and is justified by the stronger local-path error localization.

CRC should cover all semantically relevant bytes except the CRC field itself, including transfer identity, type, chunk index, and payload.

Final SHA256 remains mandatory. Per-chunk CRC is early localization, not final file authenticity/integrity proof.

Again: a valid CRC does **not** solve conflicting valid versions of the same chunk identity; see section 4.2.

---

## 12. FLOW/repair must implement real backpressure

This is the behavior the user described, and it is the right behavior.

Normal path:

```text
sender streams original DATA with local window <=2
receiver writes/checkpoints asynchronously
receiver periodically reports durable progress
```

When receiver sees enough pressure:

```text
confirmed gap range pressure
or missing chunk count threshold
or oldest gap age threshold
or sender query/credit boundary
```

it emits FLOW containing durable prefix + bounded missing ranges.

Sender behavior on a repair request:

1. stop issuing **new original** DATA immediately;
2. do not use operator cancel;
3. drain/account for at most the <=2 already-issued local submissions;
4. save `next_original` unchanged;
5. transmit requested repair DATA using original `transfer_id/chunk_index` and identical source bytes;
6. ask/wait for receiver durable status;
7. only after repair is durably closed, continue original DATA at saved `next_original`.

This must be one scheduler, not a nested “replay suffix by recursively invoking normal send loop” design.

---

## 13. Sender periodic QUERY + hard credit is the primary liveness bound

Receiver-initiated FLOW is useful, but it cannot be the only control mechanism. LoRa is half-duplex; reverse control may be delayed/collide, and if receiver ST is dead while receiver node keeps ACKing RF USER, there is no receiver application to proactively send FLOW at all.

Therefore sender must periodically force an end-to-end checkpoint.

The TODO starting values are reasonable experimental defaults:

- FLOW/query around 10 s;
- hard credit around 256 original chunks ahead of durable contiguous prefix;
- proactive gap trigger near 18 ranges / 32 missing chunks / oldest hole around 10 s;
- max local pipeline 2.

But these should be measurement knobs, not protocol constants frozen without field testing.

When periodic query or credit stops the sender:

```text
stop new original
-> drain <=2 issued
-> leave RF opportunity for reverse control
-> send/retry FLOW_QUERY boundedly
-> if valid FLOW arrives: repair/resume
-> if no response: re-handshake or suspend according to policy
```

The hard credit is what prevents this bad scenario from running to the end of a huge file:

```text
receiver ST disconnected/dead
receiver node still alive and ACKing every USER
sender node sees perfect radio delivery
sender ST otherwise would stream the entire file into a black hole
```

---

## 14. Remote protocol preemption must not use `cancel_event`

This is an implementation blocker if not separated.

`ChatterBinaryUserAdapter.send_binary()` maps `cancel_event` to a real `/cancel all` command (`binary_user.py:605-614`). That is operator/controller-global cancellation behavior.

Therefore remote negative RESULT or FLOW repair pressure must not simply “set cancel_event to stop immediately”. Doing so risks cancelling unrelated controller work and violates the TODO ownership requirement.

Add a separate non-destructive scheduler/preemption mechanism, for example:

```text
protocol_pause_event / scheduler_wakeup
```

Semantics:

- stop new DATA issuance;
- wake sender control loop;
- do not send `/cancel all`;
- already-issued <=2 submissions are boundedly drained/accounted;
- operator cancel remains a distinct destructive action.

For a terminal remote RESULT, the sender should stop new DATA immediately and avoid waiting forever for local presentation of already-issued DATA. The exact bounded drain/discard-correlation rule should be explicit in the scheduler contract.

---

## 15. Control messages themselves can be lost; repair must be idempotent

FLOW travels over the same BINARY USER/local presentation path, so it can be lost after a successful radio ACK for exactly the same reason as DATA.

The control protocol must therefore be retryable without ambiguity:

- receiver retains the active repair request until corresponding chunks are proven durable;
- same `repair_id` may be re-sent safely;
- `status_seq` changes only when receiver durable snapshot meaningfully changes (or according to a clearly specified snapshot sequence rule);
- sender may resend QUERY;
- sender never concludes repair from its own local `> [BINARY]` presentation;
- receiver durable FLOW is the proof;
- bounded `MORE_MISSING` batches are allowed;
- repair budget should be based on **lack of durable progress / repeated unchanged exchange**, not simply “N repair batches total”, because a healthy long transfer can legitimately require many batches over time.

Legacy `MISSING` may remain the final one-message repair format for legacy mode. Do not silently redefine its old full-set semantics.

---

## 16. Process restart and reconnect should re-use META/RESUME, not invent a second resurrection path

Current persisted receiver state is intentionally restored in response to matching META. That is a good property.

After uncertainty that may have included ST process restart, do this:

```text
pause original stream
-> drain local <=2
-> replay META (idempotent)
-> receiver restores retained transfer and sends RESUME / terminal tombstone result
-> negotiate a fresh FLOW session
-> continue same transfer_id
```

Do **not** require a standalone stale FLOW_QUERY to resurrect receiver state from disk. FLOW is runtime control; META/RESUME is the existing durable restart handshake.

This also cleanly handles sender process restart: sender journal validates source, keeps same transfer identity, replays META, accepts receiver-proven resume state, and creates a fresh runtime FLOW session.

---

## 17. USB/BLE/node reboot failure behavior

### 17.1 Sender-side USB unplug/replug

Current `ManagedSession` reconnects and retries queued work. Stable USB identity selection is designed to reconnect to the same device.

One caveat: `SerialTransport.write()` converts any pyserial `write()` or `flush()` error into ordinary `TransportError` (`transports/serial.py:456-464`), while `ManagedSession` treats `TransportWriteOutcomeUnknown` specially and does not blindly retry it (`session.py:664+`). BLE already has explicit unknown-outcome handling for partial fragmented writes.

Thus USB currently cannot distinguish:

```text
nothing was written
vs
some/all bytes reached the controller, then flush/disconnect failed
```

FT1 is mostly safe because replay uses stable application identity, but this can produce duplicate/partial `/bin` commands. I recommend a separate transport hardening change: once serial write may have begun, map failure to `TransportWriteOutcomeUnknown`, matching the BLE philosophy.

This is adjacent to TODO_041, not necessarily a blocker if FT1 replay remains idempotent.

### 17.2 Receiver-side USB unplug/replug

This is exactly where FLOW credit is essential. Peer firmware may continue ACKing RF USER while BINARY presentation is lost locally. Receiver durable prefix stops. Sender eventually reaches query/credit boundary, pauses, and after reconnect repairs only missing FT1 indexes.

No whole-file restart is necessary.

### 17.3 BLE reconnect

BLE already has connection generations, MTU re-resolution, and stale callback protection. FT1 should treat a generation change as local lifecycle uncertainty, replay the same application message within the bounded recovery window, and rely on receiver FT1 dedup/durable FLOW for truth.

### 17.4 Node reboot while USB tty remains

Chatter adapter already separates **controller epoch** from transport generation. This is correct: ESP reboot can occur while USB-UART remains attached.

Sender-side reboot during DATA:

- current submission becomes uncertain/recoverable;
- wait for READY/controller response;
- replay same FT1 DATA identity;
- after wider uncertainty, replay META and renegotiate FLOW;
- never allocate a new transfer_id solely because node rebooted.

Receiver-side node reboot:

- in-flight RF DATA may be lost;
- receiver ST durable state remains;
- after node recovery, FLOW/QUERY reveals holes and repair fills only those holes.

### 17.5 ST process restart

Sender process restart:

- load outgoing journal;
- validate source + prepared wire identity;
- same transfer_id;
- META/RESUME;
- fresh FLOW negotiation;
- continue/repair.

Receiver process restart:

- `.part` + manifest survive;
- fresh META triggers restoration;
- fresh FLOW session token;
- sender cannot accept stale pre-restart FLOW as current proof.

---

## 18. Radio power interruption and `RADIO_UNAVAILABLE`

The firmware recovery contract matters here.

Transient radio faults may be recovered inside firmware and FT1 should simply see delay/replay.

But after bounded radio recovery is exhausted, Chatter intentionally enters `RADIO_UNAVAILABLE` for the current boot. Current firmware explicitly reports:

```text
auto_reboot=disabled reprobe=disabled recovery=manual_reboot
```

and instructs `/reboot` to retry radio init (`lora-sack/chatter/src/RadioUnavailable.cpp:25-37`).

Therefore “pull radio power, restore it later” cannot currently be healed by passive waiting alone once the firmware has entered this state.

Recommended FT1 policy:

```text
local Chatter says RADIO_UNAVAILABLE
    -> stop new FT1 DATA immediately
    -> preserve sender/receiver journal/partial
    -> state = local_radio_unavailable / suspended-recoverable
    -> bounded wait for explicit local recovery action
```

First implementation should either:

1. require operator-authorized `/reboot`, then automatically re-handshake the same FT1 transfer; or
2. introduce a clearly explicit policy allowing at most one bounded local `/reboot` per radio-unavailable recovery episode.

Do **not** reboot a node merely because remote FLOW stopped. Missing FLOW can mean remote ST crash, remote USB/BLE issue, RF path loss, or remote radio failure. Each ST should control only its own local node and only on local evidence.

### `/radio rx-restart`

The new `1e7cdd5` command is useful diagnostics for TODO_015 silent-deaf RX, but it is not a generic FT1 recovery primitive:

- it performs exactly one receive-entry operation;
- it does not TX/reset/reinit/retry;
- it rejects `RADIO_UNAVAILABLE`;
- success only proves register/RX entry, not actual RF reception.

FLOW timeout is excellent end-to-end liveness evidence, but it does not by itself identify which radio/host failed. Automatic `rx-restart` should therefore not be fired blindly from every remote progress timeout.

---

## 19. Chatter rejection errors need typed classification

The Chatter BINARY adapter currently collapses several very different firmware lines into `send_rejected`:

```text
INPUT TOO LONG
SEND QUEUE FULL
RADIO UNAVAILABLE
BINARY ...
TX FATAL
TX FRAME BUILD ERROR
```

TODO_041 recovery needs different policy:

```text
SEND QUEUE FULL
    -> transient backpressure, bounded retry

RADIO UNAVAILABLE
    -> suspend/pause; local radio recovery/reboot required

INPUT TOO LONG / frame build deterministic error
    -> protocol/config bug; do not retry forever

controller reset/fatal lifecycle evidence
    -> controller recovery / re-handshake
```

Keep this classification in the Chatter profile layer; do not leak Chatter strings into generic transport/session code.

---

## 20. Receiver data structure should change before very large files

Current receiver uses a Python `dict[index -> length]` and recomputes `sum(received.values())` after every new chunk (`core.py:1319-1324`).

At 223–227 bytes/chunk, very large files create millions of chunk entries. A 1 GiB file is roughly 4.7–4.8 million chunks, which is unreasonable for a Python dict and also makes repeated O(n) progress summation expensive.

The FLOW design already requires sparse ranges, so use an interval/range set as the canonical memory structure:

- sorted non-overlapping/coalesced ranges;
- O(log n) or amortized efficient insert/merge;
- range count and chunk count tracked incrementally;
- durable and memory maps represented the same way;
- manifest format already naturally maps to ranges.

This is not just optimization; it prevents the reliability feature itself from becoming the scalability limit.

---

## 21. Final verification failure policy

Final SHA256 remains the authoritative whole-file integrity gate.

If final hash/decompression/size validation fails:

- do not publish destination;
- do not delete useful forensic evidence immediately;
- mark the retained state `verification_failed` / untrusted;
- under checked DATA mode this should be rare and treated as a serious invariant failure;
- do not blindly reuse the old bitmap as proof that every chunk is correct.

Selective repair cannot safely guess which CRC-valid stored chunk is wrong from a whole-file hash mismatch. Recovery should either rebuild/re-read under a stronger source manifest or require an explicit full retransmission policy while retaining evidence.

---

## 22. Observability must distinguish sent from durable

Today a sender can display high progress even when receiver has substantially less data. TODO_041 physical evidence already showed this.

Expose at least:

```text
original_issued_chunks / bytes
local_settled_chunks
receiver_durable_prefix
receiver_durable_chunks / bytes
missing_chunks
missing_ranges
active_repair_id
repair_chunks_sent
flow_session
last_flow_age
saved_next_original
pause_reason
local_recovery_state
```

For user-facing progress, either show both:

```text
sent 79.7% / receiver durable 67.5%
```

or make the primary “reliable progress” percentage receiver-durable and show sender-issued separately.

A single “progress” number is misleading once midstream repair/backpressure exists.

---

## 23. Control outbox/concurrency requirements

Current receive handling can synchronously send control from the RX worker (e.g. MISSING from END handling). New FLOW must not turn the RX path into a blocking radio-control path.

Use a dedicated bounded/coalescing FT1 control outbox owned by the per-session FT1 scheduler/coordinator.

Rules:

- RX parsing/writing should remain fast;
- status snapshots may coalesce to the newest durable state;
- terminal RESULT must not be silently coalesced away;
- active repair request must remain replayable until closed;
- disk checkpoint completion is the event that makes a new durable FLOW snapshot eligible;
- one per-local-session scheduler serializes FT1 control/repair/original BINARY submission so control cannot interleave unpredictably with DATA.

---

## 24. Recommended FLOW wire semantics

Exact enum values are not important for this review, but the semantics should be fixed before coding.

Keep existing FT1 VERSION 1 and legacy message encodings unchanged. Add optional unknown-safe message types above current type 6.

A practical shape:

```text
FLOW_HELLO / CAPS_REQUEST
    transfer_id
    sender_nonce:uint64
    feature_bits
    request_seq:uint32
    crc32

FLOW_WELCOME / CAPS_RESPONSE
    transfer_id
    sender_nonce_echo:uint64
    flow_session:uint64        # receiver-generated
    selected_features
    status_seq:uint32
    durable_prefix:uint32
    covered_frontier:uint32
    crc32

FLOW_QUERY
    transfer_id
    flow_session:uint64
    request_seq:uint32
    issued_frontier:uint32
    active_repair_id:uint32
    crc32

FLOW
    transfer_id
    flow_session:uint64
    request_seq_echo:uint32    # 0/flag for proactive FLOW
    status_seq:uint32
    covered_frontier:uint32
    durable_prefix:uint32
    repair_id:uint32
    flags
    range_count
    missing ranges
    crc32
```

Useful flags could include:

```text
MORE_MISSING
REPAIR_COMPLETE
FINAL_READY / NEED_END   (only if this helps final drain semantics)
```

The TODO’s 25-range estimate at 243 bytes is a sensible target; adding query correlation costs a few bytes but still leaves a useful bounded range count.

The codec must validate all arithmetic/ranges before any control message affects sender scheduling.

---

## 25. Proposed repair exchange

One possible concrete exchange:

```text
META
<-- RESUME(next_chunk=P)
FLOW_HELLO(nonce, features)
<-- FLOW_WELCOME(session=S, durable_prefix=P, ...)

DATA P
DATA P+1
...

FLOW_QUERY(S, request=17, issued_frontier=900)
<-- FLOW(S, request=17,
         status_seq=41,
         covered_frontier=900,
         durable_prefix=840,
         repair_id=6,
         missing=[842..844, 871, 899])

# sender stops new original; drains <=2 already-issued
DATA[842]
DATA[843]
DATA[844]
DATA[871]
DATA[899]
FLOW_QUERY(S, request=18, issued_frontier=900, active_repair_id=6)
<-- FLOW(... repair_id=6, REPAIR_COMPLETE,
         durable_prefix=900, missing=[])

# resume original at saved next_original=900
DATA 900
...
```

The important property is that the sender never assumes a repair worked because its local node presented `> [BINARY]`. Only a later receiver-durable FLOW closes the repair.

---

## 26. Failure scenario matrix

| Scenario | Desired behavior |
|---|---|
| One truncated/wrong-length DATA | Reject only that message; retain all good chunks; gap repaired midstream. |
| Same-length local-path corruption | `DATA_CHECKED` rejects it before bitmap/frontier update; repair index later. Legacy mode may only detect at final SHA. |
| Same valid index but different bytes | Preserve evidence; do not overwrite; suspend/fail current attempt as identity conflict unless independent chunk truth exists. |
| Sender node reboot | Detect controller epoch; bounded replay; if uncertainty grows, META/RESUME + fresh FLOW session; same transfer_id. |
| Receiver node reboot | Existing ST partial remains; holes revealed by FLOW; repair only missing indexes. |
| Sender USB unplug/replug | Session reconnect; FT1 idempotent replay; bounded local recovery; sender journal retained on timeout. |
| Receiver USB unplug/replug | Receiver durable progress stalls while node may still radio-ACK; sender query/credit pauses; reconnect then repair gaps. |
| Sender BLE disconnect/reconnect | Generation changes; bounded same-message replay; re-handshake if needed. |
| Receiver BLE disconnect/reconnect | Same as USB receive-side; no full restart. |
| Sender ST process restart | Outgoing journal validates source/wire; META/RESUME; fresh flow session; continue same transfer. |
| Receiver ST process restart | Restore `.part`/manifest on META; fresh flow session; repair missing. |
| Receiver ST dies while peer node remains alive | Firmware ACKs are insufficient; hard sender credit/query stops runaway stream. |
| Sender radio transient | Firmware bounded recovery; FT1 sees delay/replay only. |
| Receiver radio transient | Firmware recovery/ACK failures produce gaps; FT1 repair after recovery. |
| Local radio reaches `RADIO_UNAVAILABLE` | Preserve transfer, pause; operator/bounded local `/reboot` policy; then META/FLOW re-handshake. |
| Silent-deaf receiver | FLOW liveness reveals end-to-end stall; `/radio rx-restart` may be a local diagnostic, not automatic proof/fix. |
| FLOW lost | Sender QUERY retry; receiver retains repair state; no false durable progress. |
| Disk full/fsync/manifest failure | Never advance durable FLOW; retain last known durable snapshot; suspend/report storage failure. |
| Negative remote RESULT | Stop new DATA immediately through protocol preemption, not `/cancel all`; boundedly drain/discard issued local work. |
| Recovery deadline exhausted | Stop traffic; retain resumable journal/partial; state becomes suspended/failed-resumable. |
| Explicit operator cancel | Separate destructive policy; may intentionally clean transfer state according to current contract. |

---

## 27. Implementation order I recommend

Do not implement the entire TODO in one giant patch. The safest order is:

### Phase A — make current failure semantics non-destructive

1. classify receiver message-level errors vs transfer identity/storage/final verification failures;
2. retain partial on bad DATA/END/MISSING-control failures where state is still trustworthy;
3. make negative RESULT visible to sender scheduling immediately;
4. remove silent RX-worker failures by emitting explicit terminal/diagnostic events;
5. typed Chatter `send_rejected` reasons.

### Phase B — introduce one sender coordinator before new wire protocol

1. replace recursive/suffix pipeline fallback with a persistent `next_original` scheduler;
2. separate operator cancel from protocol pause/preemption;
3. retain <=2 pipeline bound;
4. add explicit local recovery/re-handshake state.

This gives the new FLOW protocol a stable owner.

### Phase C — add negotiated FLOW without checked DATA first

1. optional HELLO/WELCOME/CAPS handshake;
2. receiver-generated fresh flow_session;
3. periodic QUERY;
4. durable prefix + issued/covered frontier;
5. bounded missing-range batches + repair_id;
6. credit stop;
7. midstream repair and continuation.

Run physical fault tests here before adding more wire variants.

### Phase D — add `DATA_CHECKED`

1. new negotiated checked DATA type/mode;
2. persist selected transfer mode in sender/receiver journals;
3. switch new resilient transfers to ~223-byte chunks;
4. keep all existing retained legacy 227-byte transfers exactly legacy.

### Phase E — observability + policy tuning

1. sent vs durable progress;
2. pause/repair UI;
3. tune query/credit/gap thresholds from actual SF/BW conditions;
4. run reboot/unplug/radio-power matrix repeatedly.

---

## 28. Automated validation required before acceptance

At minimum add deterministic tests for:

### Protocol/codec

- unknown extension ignored by legacy decoder path;
- CRC corruption rejected before any index/frontier/state mutation;
- malformed ranges/count/overflow rejected;
- stale flow_session rejected;
- stale/lower status_seq handled idempotently;
- QUERY correlation/replay;
- bounded `MORE_MISSING` batches.

### Receiver durability

- DATA arrives during checkpoint: only captured snapshot is advertised durable;
- fsync failure cannot advance durable prefix;
- manifest persistence failure cannot advance durable prefix;
- process restart restores exactly advertised durable snapshot;
- wrong-length/bad-CRC chunk does not delete good state;
- invalid END does not delete good state;
- conflicting valid duplicate does not overwrite durable bytes.

### Sender scheduling

- FLOW gap stops new original immediately;
- <=2 already-issued submissions are boundedly drained;
- repair leaves `next_original` intact;
- receiver durable repair closure resumes exactly at saved cursor;
- remote negative RESULT preempts without sending `/cancel all`;
- credit boundary stops stream even while local BINARY presentations keep succeeding;
- missing FLOW triggers bounded QUERY/re-handshake then suspend;
- sender restart preserves transfer identity and selected data mode.

### Lifecycle

- controller reboot without USB generation change;
- USB disconnect/reconnect;
- BLE generation/MTU reconnect;
- write outcome unknown with duplicate-safe FT1 replay;
- receiver ST restart;
- sender ST restart;
- RADIO_UNAVAILABLE classification preserves journal and does not spin.

### Scalability

- sparse range structure with large synthetic chunk count;
- no O(n) `sum(received)` per chunk;
- control range coalescing under fragmented loss.

---

## 29. Physical validation matrix

Automated tests cannot prove the important post-node transport failures. Physical acceptance should deliberately include:

1. USB sender unplug/replug during DATA;
2. USB receiver unplug/replug while peer node continues running;
3. BLE sender disconnect/reconnect;
4. BLE receiver disconnect/reconnect;
5. `/reboot` sender node midstream;
6. `/reboot` receiver node midstream;
7. remove/restore sender radio-module power;
8. remove/restore receiver radio-module power;
9. induce/observe `RADIO_UNAVAILABLE`, then recover with the selected local reboot policy;
10. reproduce silent-deaf RX and verify FLOW stalls rather than falsely showing completion;
11. kill/restart sender ST process;
12. kill/restart receiver ST process;
13. intentionally drop/truncate one BINARY presentation at receiver ST;
14. intentionally lose local sender presentation while allowing chunk delivery;
15. ensure a long transfer can accumulate multiple repair batches without being killed merely by “repair round count”.

For each run record both:

```text
sender issued progress
receiver durable progress
repair ranges/ids
local connection/controller generations
firmware USER/ACK/retry timing
final SHA256
```

Acceptance criterion is not “transfer eventually finished once”; it is that **no recoverable disruption requires restarting from byte zero and no lost/unknown local presentation can produce false durable progress**.

---

## 30. Current baseline test evidence from this review

SerialTerminal targeted regression subset:

```text
114 passed in 5.63s
```

Covered current FT1 protocol/core/resume/restart/journal/pipeline/Chatter lifecycle/session behavior. These are baseline regressions only; they do not validate proposed FLOW/CAPS/DATA_CHECKED because those are not implemented.

A broader serial-transport test collection could not be run in this environment because `pyserial` is not installed (`ModuleNotFoundError: serial`). That is an environment dependency, not a source failure.

Current Chatter source-contract checks run in this review:

```text
terminal input/output source contracts: OK
TX timeout forensic source-contract tests passed
```

TODO_041 physical evidence remains the stronger evidence for the exact post-node presentation failures and continued-sender behavior.

---

## 31. Review decision / changes I would make to TODO_041 before implementation

### Keep

- separate FT1 FLOW above unchanged firmware USER/ACK;
- midstream selective repair before END;
- no per-chunk application ACK;
- durable receiver progress as truth;
- bounded range batches;
- fresh runtime flow session;
- capability negotiation with legacy fallback;
- periodic sender query + hard credit;
- final END/SHA256/RESULT contract;
- max local pipeline 2;
- retained resumable state after recoverable failure.

### Tighten/change

1. **Do not automatically “invalidate and repair” conflicting valid duplicate bytes.** Preserve state/evidence and stop the attempt unless independent chunk truth exists.
2. **Add sender-issued/covered frontier explicitly** so tail loss and “never-sent future” are both handled correctly.
3. **Define who creates `flow_session`**; recommend receiver-generated token in an asymmetric sender HELLO -> receiver WELCOME handshake.
4. **Separate persistent data-mode semantics from ephemeral FLOW tokens.**
5. **Make memory vs durable receiver maps explicit** with a checkpoint snapshot barrier.
6. **Create a non-destructive protocol preemption mechanism**; never map FLOW/remote RESULT to operator `cancel_event`/`/cancel all`.
7. **Treat malformed/conflicting END as recoverable control-message failure**, not immediate partial deletion.
8. **Make periodic QUERY/credit the primary anti-runaway liveness bound.**
9. **Classify Chatter send rejection reasons.**
10. **Use interval/range sets rather than per-chunk dict for large transfers.**
11. **Adopt checked DATA for new resilient transfers**, while preserving legacy retained transfers exactly.
12. **Specify radio-unavailable recovery explicitly**: preserve FT1 state; no automatic reboot based only on remote silence; re-handshake same transfer after authorized/bounded local recovery.
13. **Keep META/RESUME as the process-restart resurrection anchor.** FLOW is runtime state, not persistent resurrection identity.

With those changes, TODO_041 becomes a coherent end-to-end reliable file protocol rather than a collection of repair exceptions. The important architectural outcome is that node reliability and file reliability reinforce each other without being conflated:

```text
LoRa firmware keeps individual USER radio transactions reliable and bounded.
FT1 keeps the whole file transfer durable, resumable, selectively repairable,
and flow-controlled across host/node/process/transport failures.
```

That is the design I would implement.
