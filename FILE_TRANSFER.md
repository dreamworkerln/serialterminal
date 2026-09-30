# File transfer over binary USER

SerialTerminal file transfer is an application protocol above an opaque reliable binary
message transport. The current bundled implementation uses the Chatter `BINARY USER`
capability, but file semantics do not live in `ManagedSession`, Serial/BLE/SPP
transports, or the Chatter firmware.

## Layering

```text
FileTransfer / FT1
        |
        v
BinaryUserTransport
        |
        v
ChatterBinaryUserAdapter
        |
        v
ManagedSession / Serial-BLE-SPP transport
```

The Chatter adapter is the only layer that knows the local firmware text envelope:

```text
TX: /bin <BASE64>
RX: < [RSSI/SNR Q] [BINARY] <BASE64>
```

Base64 exists only on the local USB/BLE/SPP textual boundary. The LoRa BINARY USER
payload and the `BinaryUserTransport` payload are raw bytes.

A locally queued line or a transport `tx_state=written` is not radio delivery.
`ChatterBinaryUserAdapter` waits for the existing reliable USER settlement:

```text
DELIVERY WAIT_ACK user=<id>
...
DELIVERY ACK user=<same-id>
```

`DELIVERY FAILED` is a link failure. FT1 does not add a second per-DATA ACK or
retransmission protocol.

For Chatter, those settlement records are TELEMETRY output while BINARY USER
presentation is CHAT output. Therefore an FT1 transfer takes a profile-owned output
mode lease: before TX or RX work starts, the Chatter adapter switches the local
controller to `BOTH` and waits for `[SYS] OUTPUT BOTH`. It remembers the previously
tracked CHAT/TELEMETRY/BOTH mode and restores it when the transfer completes, fails or
is cancelled. If the local Serial/BLE/SPP connection generation changes while the
same transfer remains alive, the adapter reasserts `BOTH` before the next BINARY
message. FT1 itself only invokes a generic optional binary-transport lifecycle hook
and does not know these Chatter commands.

## FT1 framing

All FT1 messages begin with a compact 12-byte common header:

```text
magic      2 bytes   "FT"
version    1 byte    1
type       1 byte
transfer   8 bytes   uint64
```

Types:

```text
META
DATA
END
MISSING
RESULT
```

`META` contains the original filename, original size, wire/compressed size,
compression method, negotiated DATA chunk size and SHA-256 of the original file.

`DATA` adds a uint32 chunk index to the common header. The file-data capacity is
computed from `BinaryUserTransport.payload_capacity`; it is not hard-coded to the
current Chatter limit. With the current 243-byte BINARY USER payload, FT1 DATA carries 227 bytes
of file data.

`END` contains the expected chunk count and SHA-256 of the wire stream.

`MISSING` is an on-demand repair request. Its body contains one uint8 range count
followed by canonical `(start_chunk:uint32, count:uint32)` ranges. The complete
current missing set must fit one binary application payload; FT1 v1 does not paginate
or fragment MISSING.

`RESULT` is sent by the receiver only after application-level completion or failure.
Sender `completed` therefore means remote verified completion, not local write of the
last chunk.

## Compression

The sender streams the source through deterministic gzip while hashing it. The gzip
stream is used only when it is smaller than the original file; otherwise
`compression=none` sends the original bytes. Large files are not loaded wholly into
RAM.

The receiver verifies the wire size and wire SHA-256 before decompression. It then
streams decompression, checks the declared original size and original SHA-256, and
publishes the final file only after all checks succeed.

## Receiver filesystem safety

Default receive directory:

```text
./files
```

When running from a source checkout/editable install, this is the `files` directory
in the SerialTerminal source root next to `pyproject.toml`. Packaged installs without
that source root fall back to `./files` in the launch directory. The directory is
created on demand on both Linux and Windows.

Human TUI and agent may override it with:

```bash
--receive-dir <directory>
```

Remote filenames are treated only as basenames. Absolute paths, path separators,
`..`, drive/path syntax, NUL and control characters are rejected.

Incoming wire data is written to a hidden temporary file. A failed, cancelled or
truncated transfer must not appear under the final filename. Verified completion uses
an atomic `os.replace()`. Existing final names are not overwritten; a unique
`name (N).ext` destination is chosen.

## Ordering, duplicates and reconnect repair

Receiver storage is indexed by:

```text
transfer_id + chunk_index
```

DATA may arrive out of order. Repeating the same chunk with identical bytes is
idempotent; the duplicate is not counted twice. A duplicate index carrying different
bytes fails the transfer.

After an `END`, an incomplete receiver keeps its in-process transfer state and
computes the exact missing chunk set. If its canonical ranges fit one MISSING message,
the sender retransmits only those DATA chunk indexes and repeats the same idempotent
END. Another repair round is allowed if a repaired DATA message is itself missed.

Repeated identical META and END are idempotent. A bounded sender control timeout may
replay the same META+END so a receiver that missed either control message can recreate
or re-evaluate its state and answer with MISSING or RESULT.

This is in-process reconnect repair, not persistent resume. If SerialTerminal exits or
restarts, FT1 v1 starts a new transfer from chunk zero. LoRa SACK remains a separate
future transport project.

## Progress and completion

Core progress is toolkit-independent and reports:

```text
transfer_id
direction (TX/RX)
filename
state
original_bytes
wire_bytes
chunks_total
chunks_completed
bytes_completed
percentage
final_path / failure when applicable
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

Exactly `100%` is reserved for `completed`. Even after all DATA bytes have crossed
the binary transport, progress remains below 100% until the sender receives remote
`RESULT OK`.

The sender leaves `compressing` as soon as source preparation is finished. The
blocking META reliable-USER settlement is part of `sending`, so a slow or missing
META ACK is no longer presented as a false `compressing 0%` state.

## TUI

File controls are exposed only when the selected profile supplies a
`BinaryUserTransport` capability. The generic terminal therefore remains an ordinary
controller-agnostic terminal.

For the bundled Chatter profile:

```text
F5  choose/start file send
F6  cancel active file transfer
```

The TUI displays a determinate progress bar, filename, TX/RX direction, byte/chunk
counts, state, final path or failure. Incoming transfers appear through the same
progress model.

## Agent API

High-level operations are documented in `AGENT_API.md`:

```text
file_send_start
file_transfer_observe
file_transfer_cancel
file_transfer_close
```

The agent does not manually base64-encode chunks or parse human progress output.

## Version 1 reconnect boundary

FT1 v1 supports temporary local Serial/BLE/SPP reconnect repair while the same
SerialTerminal process and transfer state remain alive. It does not provide persistent
resume after process death/restart, directory transfer, multi-file archives, or
multiple simultaneous transfers on one session.

The generic session still does not blindly retry a `tx_state=unknown` side effect.
It only exposes reusable per-TX outcome and connection-generation primitives. The
profile/file layers may replay the same idempotent FT1 message when local delivery
became ambiguous, preserving the existing transfer_id/chunk_index identity.

If all missing ranges do not fit one MISSING payload, the receiver returns stable
`repair_too_large`. The current bounded policy does not enter an automatic whole-file
restart loop: the current transfer fails and the caller explicitly starts a new
`file_send_start`, producing a new transfer_id and retransmitting from chunk zero.
There is no MISSING pagination.

The fast path adds no per-chunk file ACK:

`META -> DATA... -> END -> RESULT`.

The firmware remains unaware of filenames, compression, chunks, filesystem paths,
SHA-256, progress, MISSING, or other FT1 message types.
