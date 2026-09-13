# ack-peer-off-bounded-failure

Result: FAIL

Firmware: unknown

## Revisions and setup

- SerialTerminal: `dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21`
- Firmware repository: `dreamworkerln/lora-sack-protocol`; Firmware: unknown
- Dynamic discovery produced two BLE transport paths. Fresh sessions were opened in one SerialTerminal agent process; no saved IDs, MACs, or session IDs were used.
- Canonical sender: `LoRa-Chatter-1B44` (s1).
- Canonical physically powered-off peer: `LoRa-Chatter-72E0` (s2).
- Both nodes were identified with `/id`, set to `/both`, and setup status showed connected with `queued_tx=0`. No `/reboot` or firmware action was performed.

## Stimulus and reliable USER evidence

- Unique payload: `PEER_OFF_FAIL_20260914T0001`.
- One logical USER identity: `EC14/11` (sender session-local protocol identity); no additional USER was sent during the transaction.
- Physical attempts, all with the same `seq=11`, `frame=39B`, `user=27B`, and the same payload bytes:
  - 2026-09-14T00:38:29.485+03:00: attempt 1/5, `TX USER`, then `WAIT_ACK`, timeout 1856 ms.
  - 2026-09-14T00:38:34.570+03:00: attempt 2/5, `TX USER RETRY`, same `seq=11`, then `WAIT_ACK`, timeout 1856 ms.
  - 2026-09-14T00:38:41.543+03:00: attempt 3/5, `TX USER RETRY`, same `seq=11`, then `WAIT_ACK`, timeout 1856 ms.
  - 2026-09-14T00:38:54.503+03:00: attempt 4/5, `TX USER RETRY`, same `seq=11`, then `WAIT_ACK`, timeout 1856 ms.
  - 2026-09-14T00:39:04.447+03:00: attempt 5/5, `TX USER RETRY`, same `seq=11`, then `WAIT_ACK`, timeout 1856 ms.
- ACK timeout/backoff evidence: next attempts were `2/5 in=1249ms`, `3/5 in=3161ms`, `4/5 in=9137ms`, and `5/5 in=6071ms`; these deferrals were not counted as physical attempts.
- Final timeout at 2026-09-14T00:39:06.337+03:00 was followed by `DELIVERY FAILED user=EC14/11 attempts=5/5 ... queue=0` and exact system outcome `[SYS] DELIVERY FAILED: no ACK`.
- Physical attempt count was exactly 5/5. No attempt 6 occurred. The reliable queue was `queue=0` in every transaction status line and sender final status reported `queued_tx=0`.
- Expected peer BLE/Serial transport loss was observed after physical power-off: s2 reported disconnected/reconnecting. This is expected fault consequence.

## CHAT presentation

- The payload was presented as `> PEER_OFF_FAIL_20260914T0001` exactly once.
- No retry produced another `>` line; same logical identity and payload remained stable.
- FAIL condition: reliability internals (`TX USER RETRY`, `DELIVERY WAIT_ACK`, `DELIVERY ACK TIMEOUT`, and `DELIVERY RETRY`) were also emitted on the sender human-console `chat` stream, not telemetry-only as required. The exact final `[SYS] DELIVERY FAILED: no ACK` was present.

## Post-failure and cleanup

- Observation continued for more than 30 seconds after final failure; no attempt 6, same-identity TX, WAIT_ACK, or retry/backoff appeared.
- After explicit human confirmation, `LoRa-Chatter-72E0` was powered on and reconnected through the normal transport lifecycle. `/id` again reported `LoRa-Chatter-72E0`; no peer-return delivery recovery was tested and the old payload was not resent.
- Both nodes were set to `/chat`; final statuses were connected with `queued_tx=0`. Echo was not enabled or toggled.
- Both sessions were closed and the single agent process was terminated via EOF. The exact forensic and companion logs in this bundle are copied from that process.

## Verdict

FAIL: bounded failure, identity/payload stability, five physical attempts, final failure, queue cleanup, and no-sixth-retry requirements passed; CHAT presentation contract failed because reliability internals appeared in `chat` output.
