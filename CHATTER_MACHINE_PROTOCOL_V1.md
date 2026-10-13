# Chatter local machine protocol v1

Experimental implementation contract, 2026-10-11. Scope: host ↔ node over USB or
standard NUS; no changes to opaque radio USER bytes or FT1. Decisions below are
selected for the architecture repair authorized by the operator.

## Encoding and framing

Each record is `/m1 ` + canonical RFC4648 base64 + LF. The binary body is little endian:
`magic[2]=CM, version:u8=1, type:u8, epoch:u64, request:u32, length:u16,
payload[length], crc32:u32`. CRC is CRC-32/ISO-HDLC (reflected polynomial 0xEDB88320,
init/final XOR 0xffffffff) over header and payload. Header=18 bytes, payload ≤243,
body ≤265, encoded record ≤360 bytes excluding LF. Empty payload is allowed only
for control records. SUBMIT/RX carry 1..243 opaque bytes. Prefix and LF are not CRC
covered. Reject malformed base64, unknown version/type, length mismatch, oversize,
truncated CRC and checksum failure before interpreting content.

Input/output parsers bound retained line data, discard oversize until LF, and never
interpret rejected frame tails as USER. During outstanding machine work, human USER admission is rejected on both inputs.
When idle, the same physical owner can still use the human terminal; a competing
input is rejected. Recognized invalid machine candidates never become human USER. The initial HELLO writer supplies a leading LF to terminate
any old line. A new `/m1 ` prefix within a damaged line is a resynchronization point:
drop preceding bytes, restart candidate; do not decode concatenated records as one.
Human output is a separate consumer; machine output always begins on a fresh line.
Output mode CHAT/TELE/BOTH cannot disable machine output. BLE uses NUS primary TX;
no change to characteristic UUIDs. No new stream configuration in generic transports.

## Types

| Value | Type | Payload |
|---|---|---|
|1|HELLO|client nonce u64; epoch=0, nonzero request|
|2|WELCOME|echo nonce u64, window u8=2, capacity u16=243|
|3|SUBMIT|opaque radio USER bytes|
|4|ACCEPTED|empty; reserved local admission, no RF claim|
|5|TX_DONE|empty; first successful physical USER TX, no ACK claim|
|6|LINK_OK|empty; matching existing radio ACK, no remote host/durability claim|
|7|LINK_FAIL|empty; retry exhaustion/build failure; delivery may be unknown|
|8|REJECTED|reason u8: 1 busy, 2 no credit, 3 stale epoch, 4 invalid, 5 unavailable|
|9|RX|opaque radio USER bytes; request=0|
|10|STATUS|host request: empty; node response: available credit u8, drop observations u32, corrupt inputs u32, high water u8|
|11|QUERY|empty; request names prior submission, returns its latest cached outcome|
|12|CLOSE|empty; requires no outstanding submissions|
|13|CLOSED|empty; releases machine owner after response is queued|
|14|UNKNOWN|empty; no retained evidence for queried request; never safe replay proof|
|15|UNAVAILABLE|empty; radio-local recovery exhausted; operator recovery required|

## Identity, ownership, credits

One machine owner across USB/BLE. WELCOME provides a fresh nonzero random node epoch;
all later commands/outcomes must match that epoch and physical owner. Requests increase
strictly from 1 per epoch, never wrap. New HELLO is accepted only when no outstanding
machine work remains; a different connected owner gets BUSY. Repeated HELLO with the
same nonce and owner repeats WELCOME without changing epoch. The host preserves
its next request counter on that repeated WELCOME; only a fresh epoch resets it.
BLE disconnect invalidates
owner access, clears its parser and stops output to that connection, but does not cancel
RF work or return its credit. A reconnect HELLO waits for old work to settle; it cannot
claim earlier outcomes as new successes. Node reboot discards volatile queues and
creates a new epoch. USB has no reliable application-disconnect signal: a new nonce
can rotate idle ownership on that USB source; outstanding work blocks rotation.

Reserve one of exactly two real machine slots before ACCEPTED and before input queue
admission. Credit is returned only when the corresponding radio logical USER settles
LINK_OK/LINK_FAIL/UNAVAILABLE/cancelled UNKNOWN, including removal before RF. Physical
write and TX_DONE do not return credit. Human queue capacity does not create machine
credit. Input queue rejection rolls back reservation and emits addressed REJECTED.
A compact bounded cache retains the latest 16 request outcomes and payload identity
for duplicate validation; duplicate SUBMIT never starts another RF operation. Old or
conflicting IDs are rejected. QUERY is local only and is used after a lost outcome;
there is no mandatory QUERY round trip on normal DATA. Status reports available credit,
not additive grants; host still bounds its own unresolved tickets to two. An addressed
STATUS with both credits available can trigger one early cached QUERY for an
accepted unresolved ticket up to that processed request ID after a
100 ms outcome grace interval. STATUS never settles the ticket itself. If that
QUERY is absent/nonterminal, the bounded near-deadline QUERY remains available;
normal delivered terminal outcomes require no QUERY.

Host completes a ticket only on LINK_OK, or fails it on an addressed terminal result.
No blind retry after unknown write/lost outcome: QUERY with the same epoch/request is
allowed; absent evidence reports unknown and suspends FT1. Reconnect/new epoch fails
old tickets visibly. Old-epoch output cannot close a new request. Automatic controller
reboot is prohibited. Optional legacy compatibility retains explicit echo/queue limits;
version negotiation cannot silently fall back after an ambiguous SUBMIT.

## Queues and output loss

Full messages are queued without waiting in Scheduler/RF paths. Queue overflow, short
USB writes, BLE timeout and stale connection drops increment RAM counters available
through STATUS even if the diagnostic output itself is dropped. The drop count sums
queue/worker observations, not unique records or bytes: one failure may be observed
at more than one boundary. LINK outcomes remain
queryable in the bounded cache. RX is bounded and lossy while the host is absent;
existing FT1 END/MISSING and final SHA detect/repair missing bytes. No promise of
unbounded RAM storage, authenticated messages, power-loss durability in node RAM, or
remote-host liveness before END. Machine metadata is removed before LoRa transmission.

## Validation

Shared golden vectors cover every type, payload sizes 0/1/243, nontrivial epoch/request,
CRC, corruption, fragmentation, truncation, glued records, missing LF, oversize and
resynchronization. Native C++ must match Python bytes. Lifecycle tests cover two-slot
admission, duplicate/conflicting/stale submissions, terminal credit, cached QUERY,
USB/BLE competing owners, reconnect, reset, unavailable, and output queue loss.
Physical four-transport/recovery/performance gates are separate from unit/build PASS.
