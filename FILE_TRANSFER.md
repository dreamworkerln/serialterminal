# File transfer / FT1 over Chatter BINARY USER

This document is the maintained engineering contract for file transfer in SerialTerminal.
It explains both sides of the boundary:

- what the Chatter firmware actually guarantees;
- what SerialTerminal/FT1 must implement above that firmware transport;
- how normal delivery, firmware retry, host-side loss, reconnect repair and selective
  chunk retransmission interact;
- how to use the firmware BINARY USER API without depending on TELEMETRY.

The current implementation lives on `serialterminal/dev_tui`. The authoritative firmware
transport contract is maintained in:

```text
lora-sack-protocol
branch: dev_chat_binary
file:   chatter/ARCHITECTURE.md
section: "Binary USER application and file-transfer boundary"
```

Exact FT1 byte encoding is implemented in:

```text
src/serialterminal/file_transfer/protocol.py
```

Exact FT1 state/recovery behavior is implemented in:

```text
src/serialterminal/file_transfer/core.py
```

The Chatter local `/bin` adapter is implemented in:

```text
src/serialterminal/profiles/chatter/binary_user.py
```

If maintained documentation and source ever disagree, do not invent a hybrid protocol:
inspect the exact source checkpoint, resolve the mismatch and update this document.

---

## 1. The mental model

A file is **not** a firmware protocol object.

The firmware knows only how to transport one opaque reliable USER message. File transfer
is an application protocol implemented by the two SerialTerminal processes above that
transport.

```text
Host A / SerialTerminal A
        |
        | FT1: META / DATA / END / MISSING / RESULT
        v
BinaryUserTransport
        |
        | local text envelope: /bin <BASE64>
        v
Node A / Chatter firmware
        |
        | reliable BINARY USER
        | USER ACK / retry / dedup
        v
      LoRa
        |
        v
Node B / Chatter firmware
        |
        | local BINARY presentation
        v
BinaryUserTransport
        |
        | FT1 decode / chunk storage / repair
        v
Host B / SerialTerminal B
```

There are therefore **two separate reliability layers**:

```text
Layer 1: firmware reliable USER
    one BINARY USER
    -> RF ACK
    -> bounded firmware retry if that USER was not ACKed

Layer 2: FT1 file completeness
    META
    -> DATA chunks
    -> END
    -> MISSING if host-visible chunks are absent
    -> selective DATA resend
    -> END again
    -> RESULT
```

Do not collapse these layers into one.

---

## 2. Responsibility boundary

### Firmware owns

The Chatter firmware owns only:

```text
opaque BINARY USER bytes
12-byte Chatter RF header
RF transmit/receive
USER ACK matching
bounded USER retry/backoff
receiver USER deduplication
/bin base64 decode on the local terminal boundary
[BINARY] base64 presentation on the local terminal boundary
```

Firmware does **not** know:

```text
file
filename
transfer_id
chunk_index
META / DATA / END / MISSING / RESULT
compression
SHA-256
missing chunks
selective file repair
filesystem paths
file progress
final file publication
```

An FT1 META/DATA/END/MISSING/RESULT message is just opaque BINARY USER payload bytes to
the firmware.

### SerialTerminal / FT1 owns

SerialTerminal owns:

```text
transfer_id
filename
compression choice
original and wire hashes
chunk sizing
chunk_index
receiver random-access assembly
duplicate DATA validation
END completeness check
MISSING range generation
selective chunk resend
control replay
RESULT success/failure
filesystem safety
progress / TUI / agent API
```

The stable file-level identity is:

```text
transfer_id + chunk_index
```

It is deliberately independent of the firmware USER sequence number.

---

## 3. Chatter firmware local BINARY API

The host-facing firmware API is line-oriented.

### Send opaque bytes

To submit 1..243 raw bytes to the local firmware:

```text
/bin <BASE64>
```

Example conceptually:

```text
raw FT1 bytes
    -> base64(raw FT1 bytes)
    -> "/bin " + base64 + newline
```

The base64 wrapper is **only** a local USB/BLE/SPP text-envelope encoding.

It is not transmitted over LoRa.

### Receive opaque bytes

When the peer firmware receives a NEW BINARY USER, the local host sees a CHAT
presentation shaped like:

```text
< [RSSI/SNR Q] [BINARY] <BASE64>
```

SerialTerminal decodes that base64 back to the original raw BINARY USER payload and
then feeds those bytes to FT1.

### Local TX presentation

After the first successful physical TxDone for a locally submitted BINARY USER, the
sender firmware emits:

```text
> [BINARY] <BASE64>
```

The current `ChatterBinaryUserAdapter.send_binary()` waits for the exact matching
local presentation. This is a **controller-local submission/backpressure signal**.
The wait is bounded independently from the much longer FT1 remote RESULT timeout.

It means approximately:

```text
"this BINARY USER reached its first successful local RF TxDone"
```

It does **not** mean:

```text
peer firmware ACKed it
peer SerialTerminal saw it
peer wrote the chunk
file is complete
```

That distinction is fundamental.

---

## 4. TELEMETRY is not the file-transfer control plane

Firmware may emit diagnostic lines such as:

```text
DELIVERY WAIT_ACK ...
DELIVERY ACK ...
DELIVERY ACK TIMEOUT ...
DELIVERY RETRY ...
DELIVERY FAILED ...
```

These are useful diagnostics, but FT1 must not depend on them.

File transfer must not:

```text
send /both before transfer
send /chat or /tele to make transfer work
reassert /both after reconnect
restore a previous CHAT/TELEMETRY/BOTH mode after transfer
wait for DELIVERY ACK before every FT1 DATA
use DELIVERY telemetry as chunk truth
```

The operator-selected output mode belongs to the operator.

Current Chatter BINARY presentation is on the CHAT human stream. Before the first
BINARY send of a connection/controller epoch, an unknown mode is queried read-only
through `/help` and its `[SYS] current=...` response. SerialTerminal never sends
`/chat`, `/tele` or `/both` for this preflight. TELEMETRY-only mode therefore fails
deterministically with `binary_presentation_unavailable` before `/bin` is submitted.

A controller reboot is not assumed to imply a USB disconnect: common USB-UART bridges
can stay connected while the ESP restarts. Chatter profile state therefore tracks a
separate controller epoch. If a reset/fatal marker arrives while exact
`> [BINARY]` settlement is pending, that submission becomes ambiguous; the adapter
waits for a new `[SYS] CHATTER READY` and reports `local_controller_reset`. FT1 may
then replay the exact same idempotent META/DATA/END message.

The relevant implementation/design record is:

```text
todos/TODO_030_CHATTER_FT1_NO_TELEMETRY.md
```

---

## 5. Chatter RF BINARY USER format

Chatter protocol v3 uses a 12-byte common RF header:

```text
byte 0      version = 3
byte 1      flags
byte 2..3   session_id
byte 4..5   tx_seq
byte 6..7   report_seq
byte 8..9   report_rssi
byte 10     report_snr
byte 11     report_quality
```

Relevant flags:

```text
0x01 HEARTBEAT
0x02 REPORT_VALID
0x04 ACK
0x20 HEARTBEAT_PONG
0x40 BINARY_USER
```

`BINARY_USER` is a modifier of an ordinary USER frame, not a separate RF service.

A maximum BINARY USER is:

```text
12 bytes  Chatter RF header
243 bytes raw BINARY USER application payload
---------
255 bytes total LoRa frame
```

The 243-byte limit is the capacity visible to FT1.

An RF ACK is 14 bytes: the common 12-byte header plus a 2-byte target-session field.
ACK correlation identifies the USER by:

```text
(sender_session_id, user_seq)
```

The ACK does not know or carry an FT1 `chunk_index`.

---

## 6. Firmware reliable USER retry

The firmware implements bounded stop-and-wait reliability for every USER, including
BINARY USER.

Current firmware bounds:

```text
one active PendingReliableUser
RELIABLE_USER_QUEUE_DEPTH = 8
RELIABLE_USER_MAX_ATTEMPTS = 5
```

A retry reuses the **same logical USER**:

```text
same sender_session_id
same user_seq
same payload bytes
same TEXT/BINARY modifier
```

The firmware is not "resending the last file chunk" in file-protocol terms. It is
retrying the current pending reliable USER transaction. The fact that the opaque
payload happens to contain an FT1 DATA chunk is invisible to firmware.

### ACK timeout

After TxDone the sender waits for an ACK response deadline based on:

```text
ACK time-on-air
+ bounded software response margin
```

The response margin covers implementation costs such as serial formatting, RX polling
and main-loop quanta. It is a timeout tolerance, not a deliberate pre-ACK transmission
delay.

### Retry backoff

After an ACK timeout, if attempts remain, firmware schedules a randomized ToA-based
backoff.

The current policy uses a multiplier capped at 1x / 2x / 4x and a delay of:

```text
minimum = 0.5 * USER_ToA * multiplier
jitter  = 0 .. 1.0 * USER_ToA * multiplier
```

So successive retry windows are approximately:

```text
0.5 .. 1.5 USER ToA
1.0 .. 3.0 USER ToA
2.0 .. 6.0 USER ToA
```

with the 4x scale capped for later attempts.

There is no file-specific retry timer in firmware.

---

## 7. What happens when an RF packet is lost

Consider one FT1 DATA message embedded in one BINARY USER.

### Case A: the LoRa USER itself is not received

```text
Sender ST
  -> Sender firmware
       -> USER attempt #1 --X--> Receiver firmware
       <- no ACK
       -> timeout/backoff
       -> same USER attempt #2 ----> Receiver firmware
                                      -> NEW USER
                                      -> local [BINARY] presentation
                                      -> ACK
```

The firmware handles this automatically.

SerialTerminal does not need to request that chunk merely because one RF attempt was
lost.

The receiver host normally sees the BINARY USER once, when a retry finally arrives as
a NEW USER.

### Case B: receiver gets USER, but RF ACK is lost

```text
Sender firmware -> USER ----> Receiver firmware
                               -> NEW
                               -> presents BINARY to Receiver ST
                               -> ACK --X-->

Sender firmware times out
Sender firmware -> same USER retry ----> Receiver firmware
                                         -> DUPLICATE
                                         -> do NOT present BINARY again
                                         -> ACK again
```

Firmware receiver deduplication prevents a radio retry from becoming a duplicate
application delivery.

The duplicate is ACKed again because the previous ACK may have been lost.

### Case C: all firmware attempts for one DATA fail

After five unsuccessful physical attempts, firmware gives up that USER transaction.

FT1 does **not** need DELIVERY telemetry to learn this immediately.

Later DATA messages may still proceed. When the receiver eventually gets END, it sees
the missing `chunk_index` and sends FT1 MISSING. The sender SerialTerminal then
retransmits that exact DATA chunk as a **new** BINARY USER transaction.

This is the transition from firmware-level recovery to file-level recovery.

---

## 8. Why firmware ACK does not prove file delivery

A firmware ACK proves only:

```text
peer firmware received the USER
```

It does not prove:

```text
peer SerialTerminal was connected
peer SerialTerminal received the local BINARY presentation
peer SerialTerminal stored the DATA chunk
the file is complete
```

The receive order is conceptually:

```text
LoRa USER received
    |
    v
firmware dedup / receive policy
    |
    +--> create RF ACK obligation
    |
    +--> attempt local USB/BLE BINARY presentation
    |
    +--> service RF ACK
```

If BLE/USB disappears at the wrong moment, the receiver firmware can successfully ACK
the USER while the receiver SerialTerminal never gets that BINARY presentation.

Therefore:

```text
firmware USER ACK success != receiver-host file-chunk delivery
```

This is the primary reason FT1 needs stable chunk identity and MISSING repair.

There is an additional subtle consequence: if the sender firmware later repeats the
same USER because its ACK was lost, the receiver firmware recognizes that USER as a
DUPLICATE and intentionally suppresses the second local presentation. Firmware retry
cannot be used as host-side replay.

Host-side repair must create a **new firmware USER transaction** carrying the same FT1
`transfer_id + chunk_index`.

---

## 9. FT1 v1 common header

Every FT1 message is raw bytes carried inside one BINARY USER payload.

All integer fields use network/big-endian byte order.

The common header is exactly 12 bytes:

```text
offset  size  field
0       2     magic = ASCII "FT"
2       1     version = 1
3       1     message_type
4       8     transfer_id (uint64)
```

Python struct:

```text
>2sBBQ
```

Message types:

```text
1  META
2  DATA
3  END
4  RESULT
5  MISSING
```

A sender allocates a non-zero 64-bit `transfer_id` that is unique among retained
transfers in that process.

---

## 10. META

META establishes file identity and the wire representation.

Layout after the 12-byte common header:

```text
original_size      uint64
wire_size          uint64
compression        uint8
chunk_size         uint16
original_sha256    32 bytes
filename_len       uint8
filename           filename_len UTF-8 bytes
```

Compression values:

```text
0  NONE
1  GZIP
```

With a 243-byte BINARY USER capacity, the maximum META filename payload is currently
179 UTF-8 bytes.

META is deliberately idempotent:

- identical META for the same `transfer_id` is a replay, not a new transfer;
- conflicting META for an existing `transfer_id` is a protocol error.

---

## 11. Compression and source preparation

Before transmission, the sender streams the source file through deterministic gzip:

```text
gzip mtime = 0
```

while computing the original SHA-256.

The sender then compares sizes:

```text
if gzip_size < original_size:
    wire representation = gzip
    compression = GZIP
else:
    wire representation = original file
    compression = NONE
```

Compression is therefore opportunistic. Incompressible files are not made larger just
to claim compression.

The implementation does not load a large file wholly into RAM. It streams source
preparation and hashing in blocks.

Two hashes exist for different purposes:

```text
META.original_sha256
    hash of the final original file

END.wire_sha256
    hash of the actual transmitted wire stream
    (compressed stream when GZIP is used, otherwise original bytes)
```

The receiver verifies both.

---

## 12. DATA

DATA layout:

```text
12 bytes  FT1 common header
4 bytes   chunk_index uint32
N bytes   chunk payload
```

With the current Chatter BINARY USER capacity:

```text
243 byte BINARY USER capacity
-12 byte FT1 common header
- 4 byte DATA chunk_index
--------------------------------
227 bytes maximum file/wire data per full DATA message
```

The DATA chunk size is negotiated in META and must not exceed the local
`BinaryUserTransport` capacity.

The receiver writes DATA by:

```text
offset = chunk_index * meta.chunk_size
```

so DATA may arrive out of order.

### DATA duplicate rules

If the receiver already has the same `chunk_index`:

- same bytes: idempotent duplicate; keep one copy;
- different bytes: fail with `invalid_chunk`.

This makes deliberate FT1 replay safe while detecting corruption/protocol conflicts.

---

## 13. END

END layout:

```text
12 bytes  FT1 common header
4 bytes   chunk_count uint32
32 bytes  wire_sha256
```

Total current END payload size:

```text
48 bytes
```

END means:

```text
"the sender has finished the current DATA pass;
 this is the expected chunk count and wire-stream hash"
```

END does **not** mean the receiver must already have every DATA message.

END is the point where receiver-side completeness is evaluated.

Repeated identical END is idempotent.

---

## 14. Receiver assembly and completeness

After META, the receiver creates a hidden temporary wire file and tracks received
chunk indexes. Incomplete incoming state also has a bounded inactivity lifetime:
current META/DATA/END activity refreshes the deadline, and after 120 seconds with no
FT1 activity the receiver fails that transfer with `remote_sender_timeout`, removes
the temporary state and releases the one-transfer session lease.

For each DATA:

1. validate that `chunk_index` is within the META-derived chunk count;
2. validate the exact expected length for that index;
3. seek to the chunk offset;
4. write bytes to the temporary wire file;
5. record that index as present.

The final chunk may be shorter than `meta.chunk_size`; all earlier chunks must have
exactly `meta.chunk_size` bytes.

When END arrives, the receiver computes:

```text
missing = every index in 0 .. chunk_count-1 that was not received
```

If `missing` is empty, verification begins.

If `missing` is non-empty, FT1 enters selective repair.

---

## 15. MISSING: requesting arbitrary chunks

This is the mechanism for asking the **peer SerialTerminal** to retransmit arbitrary
file chunks.

It is not a firmware command.

The receiver SerialTerminal creates an FT1 MISSING message and sends it through the
same generic firmware API:

```text
MISSING raw bytes
    -> base64
    -> /bin <BASE64>
    -> local firmware
    -> reliable BINARY USER
    -> peer firmware
    -> peer SerialTerminal
```

### MISSING layout

```text
12 bytes  FT1 common header
1 byte    range_count
then range_count times:
    4 bytes start_chunk uint32
    4 bytes count       uint32
```

Missing indexes are canonicalized into contiguous ranges.

Example:

```text
missing indexes:
7, 8, 9, 15, 16

canonical ranges:
(start=7,  count=3)
(start=15, count=2)
```

With a 243-byte application capacity:

```text
243 - 12 - 1 = 230 bytes available for ranges
230 / 8 = 28 complete ranges
```

So FT1 v1 can encode at most 28 disjoint missing ranges in one MISSING message at the
current Chatter capacity.

FT1 v1 has no MISSING pagination.

If the complete missing set cannot fit one MISSING message, the transfer fails with
`repair_too_large`. A full resend is an explicit new transfer with a new
`transfer_id`; the implementation must not silently invent pagination or an endless
whole-file restart loop.

---

## 16. How selective resend works

When the sender SerialTerminal receives MISSING:

1. validate every requested range against the known `chunks_total`;
2. keep the same FT1 `transfer_id`;
3. seek directly to every requested `chunk_index` in the prepared wire stream;
4. emit only those DATA messages;
5. keep each DATA's original `chunk_index`;
6. send END again.

Example:

```text
Receiver has:
0 1 2 3 4 5 6 _ _ _ 10 11 12 13 14 _ _ 17 ...

Receiver -> MISSING:
    (7,3)
    (15,2)

Sender resends:
    DATA chunk=7
    DATA chunk=8
    DATA chunk=9
    DATA chunk=15
    DATA chunk=16

Sender then sends:
    END
```

If one of the repair DATA messages is itself lost, the next END causes another MISSING
round.

Current default bound:

```text
FILE_MAX_REPAIR_ROUNDS = 8
```

The important identity distinction is:

```text
FT1 identity stays:
    same transfer_id
    same chunk_index

firmware transport identity may be new:
    new user_seq
```

That new firmware USER identity is intentional. It ensures receiver firmware treats
the repaired DATA as NEW and presents it to the receiver host instead of suppressing
it as a duplicate radio retry.

---

## 17. Firmware retry vs FT1 repair: decision table

| Failure/loss | Who repairs it? | Mechanism |
| --- | --- | --- |
| One LoRa USER attempt is not received | Sender firmware | Same reliable USER is retried automatically |
| RF ACK is lost | Sender + receiver firmware | Sender retries same USER; receiver recognizes DUPLICATE, re-ACKs, suppresses duplicate host presentation |
| All firmware attempts for one DATA fail | Receiver ST + sender ST | END exposes missing chunk; MISSING asks peer ST to resend that DATA |
| Receiver firmware got USER but receiver host missed local USB/BLE presentation | Receiver ST + sender ST | Firmware ACK is insufficient; END/MISSING repairs the host-visible hole |
| Sender local USB/BLE write becomes ambiguous/disconnects | Sender ST | Bounded replay of the same idempotent FT1 message |
| META never reaches receiver host | Sender ST control replay | Re-send identical META + END; receiver reconstructs state and requests missing DATA |
| END is lost | Sender ST control replay | Re-send identical META + END |
| MISSING is lost | Sender ST control replay causes reevaluation | Receiver sees repeated END and sends MISSING again |
| RESULT is lost | Sender ST control replay + completed receiver replay | Repeated META/END causes completed receiver to send RESULT again |
| SerialTerminal process dies | Not resumable in FT1 v1 | Start a new transfer with a new transfer_id |

This table is the practical answer to "who resends what?"

---

## 18. Local ambiguous-send replay

The generic `ManagedSession` must not blindly retry an ambiguous physical write.

However, FT1 messages are designed to be idempotent where replay is required.

The file layer currently allows bounded replay of the **same encoded FT1 message** when
the Chatter binary adapter reports:

```text
local_tx_unknown
local_disconnect
```

Current default:

```text
FILE_MAX_LOCAL_MESSAGE_REPLAYS = 4
```

This is not firmware RF retry.

It is host-side recovery across the local Serial/BLE/SPP boundary.

For DATA, replay remains safe because the receiver keys it by
`transfer_id + chunk_index` and verifies duplicate bytes.

---

## 19. Control replay

After all DATA and END are sent, the sender waits for either:

```text
RESULT
or
MISSING
```

There is intentionally no per-DATA FT1 ACK.

If neither outcome arrives within the control replay interval, the sender replays:

```text
same META
same END
```

Current defaults:

```text
FILE_CONTROL_REPLAY_INTERVAL_S = 30
FILE_MAX_CONTROL_REPLAYS       = 3
FILE_RESULT_TIMEOUT_S          = 3600
```

Why replay both?

### META was lost

Receiver may have ignored DATA/END because no transfer existed. Replayed META creates
the transfer, and replayed END immediately exposes all missing DATA through MISSING.

### END was lost

Receiver already has DATA; repeated END triggers verification or MISSING.

### MISSING was lost

Repeated END makes the incomplete receiver compute and send MISSING again.

### RESULT was lost

A receiver that already completed the transfer recognizes identical replayed META/END
and can send RESULT OK again without rebuilding or duplicating the final file.

This is why META and END must be idempotent.

---

## 20. RESULT

RESULT is the application-level completion/failure message.

Layout:

```text
12 bytes  FT1 common header
1 byte    failed flag: 0=success, 1=failure
1 byte    result code
1 byte    reason_len
N bytes   UTF-8 reason
```

At the current 243-byte capacity, the reason field can occupy at most 228 bytes.

Known result codes include:

```text
ok
busy
invalid_metadata
invalid_chunk
missing_chunks
wire_hash_mismatch
decompression_failed
original_hash_mismatch
storage_failed
cancelled
protocol_error
remote_failed
repair_too_large
```

The sender is `completed` only after receiving remote:

```text
RESULT OK
```

Not after:

```text
local /bin write
local > [BINARY] presentation
firmware RF ACK
last DATA
END
```

Exactly 100% progress is reserved for verified application completion.

---

## 21. Final verification at the receiver

When END finds no missing chunks, the receiver validates in this order:

1. temporary wire-file size equals META `wire_size`;
2. wire-file SHA-256 equals END `wire_sha256`;
3. if compression is GZIP, stream-decompress to another temporary file;
4. final original size equals META `original_size`;
5. final original SHA-256 equals META `original_sha256`;
6. atomically publish the final file;
7. send RESULT OK.

A failed, truncated or cancelled transfer must not appear as a valid final filename.

---

## 22. Receiver filesystem safety

Default receive directory:

```text
./files
```

For a source checkout/editable install this is the repository `files` directory next
to `pyproject.toml`. Packaged installs without that source root fall back to
`./files` in the launch directory.

The TUI/agent may override it with:

```bash
--receive-dir <directory>
```

Remote filenames are treated as basenames only.

Rejected filename content includes unsafe path semantics such as:

```text
absolute paths
path separators
..
drive/path syntax
NUL/control characters
```

Incoming data is written to a hidden temporary file. Successful publication uses
`os.replace()`. Existing final names are not overwritten; a unique
`name (N).ext` destination is selected.

---

## 23. Normal transfer sequence

The normal no-loss fast path is:

```text
Sender ST                         Receiver ST
---------                         -----------

prepare source
compress if smaller
compute hashes

META ---------------------------> create RX state

DATA chunk 0 -------------------> store chunk 0
DATA chunk 1 -------------------> store chunk 1
DATA chunk 2 -------------------> store chunk 2
...
DATA chunk N -------------------> store chunk N

END ----------------------------> check completeness
                                  verify wire hash
                                  decompress if needed
                                  verify original hash
                                  publish file

RESULT OK <----------------------

sender completed
```

There is no FT1 ACK after every DATA.

The underlying firmware still performs its own USER ACK/retry for each BINARY USER
message transparently.

---

## 24. Transfer with a missing chunk

Example where firmware-level delivery ultimately fails for DATA chunk 7:

```text
Sender ST                         Receiver ST
---------                         -----------

META ---------------------------> OK
DATA 0 -------------------------> OK
...
DATA 6 -------------------------> OK

DATA 7
  firmware attempt 1 --X
  firmware attempt 2 --X
  firmware attempt 3 --X
  firmware attempt 4 --X
  firmware attempt 5 --X
  firmware gives up

DATA 8 -------------------------> OK
DATA 9 -------------------------> OK
...

END ----------------------------> detects chunk 7 absent

MISSING (7,1) <-----------------

DATA 7 -------------------------> stored as FT1 chunk 7
                                  but through a NEW firmware USER transaction

END ----------------------------> complete + verify

RESULT OK <---------------------
```

SerialTerminal did not need DELIVERY telemetry to make this work.

---

## 25. Transfer where firmware ACK succeeds but host loses the chunk

This is the important cross-layer failure case.

```text
Sender ST
   |
Sender firmware
   |
   | DATA chunk 42 inside BINARY USER
   v
Receiver firmware
   |
   +----> creates/sends RF ACK successfully
   |
   +--X-> receiver host presentation lost because USB/BLE host is absent
```

From the firmware viewpoint, USER 42 was delivered successfully.

From the file receiver viewpoint, FT1 chunk 42 is absent.

Later:

```text
END
 -> receiver ST sees hole
 -> MISSING requests chunk 42
 -> sender ST resends DATA chunk 42
 -> new firmware USER transaction
 -> receiver ST receives it
 -> END
 -> RESULT
```

This is why a firmware ACK cannot replace FT1 MISSING.

---

## 26. Queueing and backpressure

Firmware permits one active reliable USER plus a bounded queue of accepted USERs.

SerialTerminal's current Chatter adapter does not wait for DELIVERY ACK. It waits only
for the exact local `> [BINARY]` first-TxDone presentation before considering one
`send_binary()` submission locally settled.

This gives bounded controller-local backpressure while allowing firmware reliability
to continue independently.

Consequences:

- FT1 does not intentionally insert a second stop-and-wait ACK layer;
- later file messages are not gated on TELEMETRY;
- if a prior USER later exhausts firmware retries, file-level MISSING can repair the
  resulting hole;
- queue-full or controller rejection remains a local send error, not remote completion.

---

## 27. Base64 sizing and local UART cost

Base64 is local framing overhead only.

For a maximum 243-byte BINARY USER:

```text
raw bytes:      243
base64 text:    324 ASCII bytes
command prefix: 5 bytes  "/bin "
line ending:    typically 1 byte
```

So the local command is roughly 330 UART bytes.

At 115200 baud, 8N1, that local text envelope has a real transmission cost of roughly
29 ms.

Do not confuse this with LoRa airtime and do not include base64 expansion in the
on-air 243-byte application payload.

The generic Serial RX path must also not add artificial batching latency. The
historical `read(512)` + `timeout=0.20` issue is tracked/implemented under:

```text
todos/TODO_031_SERIAL_RX_LOW_LATENCY.md
```

---

## 28. Preferred SerialTerminal APIs

Most callers should **not** manually construct `/bin` commands or parse BINARY lines.

Use the high-level file-transfer API.

### TUI

For the bundled Chatter profile:

```text
F5  choose/start file send
F6  cancel active file transfer
```

Incoming transfers use the same progress model.

### Agent JSONL

Start:

```json
{"id":60,"op":"file_send_start","session":"s1","path":"/tmp/demo.bin"}
```

Observe:

```json
{"id":61,"op":"file_transfer_observe","session":"s1","transfer_id":"2c0c98db8bfdd7d1","cursor":0,"window":100,"timeout_ms":30000}
```

Cancel:

```json
{"id":62,"op":"file_transfer_cancel","session":"s1","transfer_id":"2c0c98db8bfdd7d1"}
```

Release retained terminal state:

```json
{"id":63,"op":"file_transfer_close","session":"s1","transfer_id":"2c0c98db8bfdd7d1"}
```

The high-level API owns compression, chunking, base64 encapsulation, MISSING repair,
hashing and completion.

A caller must not manually base64/chunk the file in parallel with
`file_send_start`.

---

## 29. Low-level integration contract

If implementing or reviewing a new SerialTerminal frontend/profile adapter, use this
boundary.

### Send one FT1 message

```text
FT1 encoder
    -> raw message bytes <= BinaryUserTransport.payload_capacity
    -> BinaryUserTransport.send_binary(raw)
    -> Chatter adapter base64 encodes raw
    -> send_line("/bin <BASE64>")
    -> wait for exact matching local > [BINARY] presentation
```

Do not wait for DELIVERY TELEMETRY.

### Receive one FT1 message

```text
canonical received line
    -> recognize:
       < [..] [BINARY] <BASE64>
    -> strict base64 decode
    -> raw BINARY payload
    -> FT1 decode_message(raw)
    -> META/DATA/END/MISSING/RESULT state machine
```

Do not feed TELEMETRY into FT1.

### Important correlation rule

Never use firmware `user_seq` as the file chunk identifier.

Use:

```text
transfer_id + chunk_index
```

A selective resend intentionally may carry the same FT1 chunk through a different
firmware `user_seq`.

---

## 30. Progress semantics

Core progress fields include:

```text
transfer_id
direction
filename
state
original_bytes
wire_bytes
chunks_total
chunks_completed
bytes_completed
percentage
final_path / failure
```

States include:

```text
preparing
compressing
sending
receiving
verifying
waiting_result
repair_requested
repairing
decompressing
completed
failed
cancelled
```

Receiving/sending all DATA bytes is not 100%.

`completed` and 100% require final application-level verification.

---

## 31. Reconnect boundary

FT1 v1 supports temporary local Serial/BLE/SPP reconnect repair while the same
SerialTerminal process and transfer state remain alive.

It relies on stable application identity:

```text
transfer_id + chunk_index
```

and idempotent replay.

It does **not** provide persistent resume after SerialTerminal process death/restart.

After process restart:

```text
start a fresh transfer
new transfer_id
send from the beginning
```

Do not claim persistent resume.

---

## 32. Current limits and defaults

Current implementation defaults relevant to file transfer:

```text
Chatter BINARY USER payload capacity     243 bytes
FT1 full DATA file payload               227 bytes
firmware reliable USER max attempts      5
firmware reliable USER queue depth       8
FT1 repair rounds                        8
FT1 local-message replays                4
Chatter local BINARY presentation timeout 30 s
Chatter output-mode query timeout         5 s
Chatter controller READY timeout          15 s
FT1 incoming inactivity timeout           120 s
FT1 control replay interval              30 s
FT1 maximum control replays              3
FT1 overall remote-result timeout        3600 s
FT1 MISSING max disjoint ranges          28 at 243-byte capacity
simultaneous active FT1 transfers/session 1
MISSING pagination                       none
persistent process-restart resume        none
LoRa SACK dependency                     none
```

These values are current implementation defaults, not reasons to duplicate constants
in unrelated UI code. Consume the existing interfaces/constants where possible.

---

## 33. Common implementation mistakes

Do not implement file transfer as:

```text
DATA
wait DELIVERY ACK telemetry
DATA
wait DELIVERY ACK telemetry
...
```

That adds a host-level stop-and-wait dependency to a transport that already has
firmware USER reliability.

Do not implement:

```text
start transfer -> /both
finish transfer -> restore /chat
```

Human output mode is not an FT1 transport primitive.

Do not implement:

```text
missing chunk -> ask firmware to resend user_seq
```

Firmware has no file/chunk API.

Correct repair is:

```text
receiver ST
  -> FT1 MISSING(transfer_id, chunk ranges)
  -> BINARY USER
  -> sender ST
  -> reread those chunks from prepared wire stream
  -> FT1 DATA with same transfer_id/chunk_index
  -> new BINARY USER transactions
```

Do not use:

```text
firmware ACK == file chunk persisted
```

It is false by architecture.

Do not add a second per-DATA FT1 ACK. FT1 v1 uses END/MISSING/RESULT.

---

## 34. Review checklist for file-transfer code

Before accepting a file-transfer implementation, verify all of the following:

- [ ] firmware is treated as an opaque reliable BINARY USER transport;
- [ ] no file semantics were added to generic Serial/BLE/SPP transport code;
- [ ] no FT1 correctness dependency on TELEMETRY;
- [ ] transfer sends no automatic `/both`, `/chat` or `/tele`;
- [ ] local `> [BINARY]` is treated only as controller-local submission/backpressure;
- [ ] controller reboot can invalidate a pending local presentation without a USB reconnect;
- [ ] replay after controller reboot waits for a new `CHATTER READY`;
- [ ] incomplete incoming transfer state expires after bounded inactivity;
- [ ] remote completion requires FT1 RESULT OK;
- [ ] BINARY payload capacity is taken from `BinaryUserTransport`, currently 243 bytes
      for Chatter;
- [ ] full current DATA capacity is 227 wire/file bytes;
- [ ] base64 exists only on local host<->firmware text boundary;
- [ ] firmware radio retry is allowed to remain transparent to FT1;
- [ ] firmware retries reuse the same USER identity;
- [ ] firmware DUPLICATE is re-ACKed but not re-presented to host;
- [ ] receiver stores DATA by `transfer_id + chunk_index`;
- [ ] identical DATA duplicate is idempotent;
- [ ] conflicting DATA duplicate fails;
- [ ] END computes exact missing indexes;
- [ ] MISSING uses canonical ranges;
- [ ] sender resends only requested chunks;
- [ ] repair keeps FT1 identity but may use new firmware USER sequence numbers;
- [ ] repaired DATA is followed by END again;
- [ ] META and END are idempotent;
- [ ] missing MISSING/RESULT can be recovered through bounded control replay;
- [ ] MISSING pagination is not invented in FT1 v1;
- [ ] `repair_too_large` is handled explicitly;
- [ ] compressed wire stream is used only when smaller;
- [ ] wire SHA-256 and final original SHA-256 are both verified;
- [ ] final file publication is atomic;
- [ ] process restart is not presented as resume;
- [ ] no new per-DATA application ACK was added.

---

## 35. Short version

The complete design can be summarized as:

```text
Firmware:
    reliably move one opaque BINARY USER between nodes
    with ACK/retry/dedup.

SerialTerminal FT1:
    reliably turn many opaque BINARY USER messages into one verified file.

RF loss of one USER:
    firmware retries automatically.

Firmware finally gives up,
or receiver host misses a firmware-delivered USER:
    receiver FT1 discovers the missing chunk after END
    and sends MISSING to peer SerialTerminal.

Peer SerialTerminal:
    resends exactly the requested DATA chunk(s)
    with the same transfer_id/chunk_index,
    but through new firmware USER transaction(s).

Completion:
    only RESULT OK after full hash/decompression/filesystem verification.
```


## 34. FT1 forensic logging

Interactive and agent primary logs record payload-free FT1 lifecycle/send-stage entries.
Typical records include `binary_send_start`, `binary_send_settled`,
`binary_send_replay`, terminal state changes and repair/control events. DATA records carry
`chunk_index`, but never raw FT1 payload or base64. This makes a stalled transfer
distinguishable as META/DATA/END local settlement without enabling `--log-base64`.

During an active TUI transfer, ordinary protocol/BINARY scrollback remains muted, but
critical controller-reset/reconnect lines such as `[SYS] RADIO FATAL ...`,
`ESP-ROM:`, `[SYS] CHATTER READY`, disconnect and reconnect status bypass that mute.
