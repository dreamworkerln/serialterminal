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
RESULT
```

`META` contains the original filename, original size, wire/compressed size,
compression method, negotiated DATA chunk size and SHA-256 of the original file.

`DATA` adds a uint32 chunk index to the common header. The file-data capacity is
computed from `BinaryUserTransport.payload_capacity`; it is not hard-coded to the
current Chatter limit. With a 200-byte BINARY USER payload, FT1 DATA carries 184 bytes
of file data.

`END` contains the expected chunk count and SHA-256 of the wire stream.

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
~/Downloads/SerialTerminal
```

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

## Ordering, duplicates and future SACK

Receiver storage is indexed by:

```text
transfer_id + chunk_index
```

DATA may arrive out of order. Repeating the same chunk with identical bytes is
idempotent; the duplicate is not counted twice. A duplicate index carrying different
bytes fails the transfer.

This makes the file layer suitable for a future SACK or resume implementation without
changing its fundamental identity model.

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
decompressing
completed
failed
cancelled
```

Exactly `100%` is reserved for `completed`. Even after all DATA bytes have crossed
the binary transport, progress remains below 100% until the sender receives remote
`RESULT OK`.

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

## Version 1 scope

FT1 v1 deliberately does not implement reconnect/reboot resume, directory transfer,
multi-file archives, or multiple simultaneous transfers on one session.

A v1 transfer is never silently restarted from byte zero after an ambiguous
disconnect. Its `transfer_id` and indexed DATA model are intended to support a
separately specified resume handshake later, once controller reconnect/session
semantics are defined.

The firmware remains unaware of filenames, compression, chunks, filesystem paths,
SHA-256, progress, or FT1 message types.
