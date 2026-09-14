# Focused hardware validation: `/cancel` on in-flight reliable USER

Result: PASS

Firmware: unknown
Firmware repository: `dreamworkerln/lora-sack-protocol`
SerialTerminal: `dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21`

## Hardware and setup

- Canonical sender: `LoRa-Chatter-1B44` (session `s1`).
- Canonical powered-off/returned peer: `LoRa-Chatter-72E0` (session `s2`).
- Both nodes were dynamically discovered; no saved identity or path was used.
- Initial sessions were connected with `queued_tx=0`; `/help` reported `current=CHAT echo=OFF` before `/both` setup.
- Both nodes were placed in `/both`. Telemetry visible there was treated as telemetry, not semantic CHAT pollution.
- Peer transport evidence after physical power-off: `s2` state `disconnected` at `2026-09-14T03:01:14.122+03:00`, then `reconnecting` at `2026-09-14T03:01:14.422+03:00`.

## Stimulus and exact evidence

- Payload: `CANCEL_INFLIGHT_20260914T`.
- Host acceptance was `send_line state=queued`, followed by `tx_state=written`; these were not used as physical-TX proof.
- Exact first physical USER TX evidence: `TX USER seq=31 frame=37B user=25B attempt=1/5 OK time=1976 ms` at `2026-09-14T03:01:48.623983+03:00` (chat; telemetry duplicate at `03:01:48.628301+03:00`).
- Exact local semantic CHAT appeared once: `> CANCEL_INFLIGHT_20260914T`.
- Exact logical USER identity: `EC14/31`, i.e. sender session identity `EC14`, `user_seq=31`.
- WAIT_ACK evidence: `DELIVERY WAIT_ACK user=EC14/31 attempt=1/5 timeout=1856ms queue=0` at `2026-09-14T03:01:48.631776+03:00` (chat; telemetry duplicate at `03:01:48.634858+03:00`).
- The retry scheduler had already started attempts 2 and 3 before `/cancel` was processed. These were recorded exactly: attempt 2 TX at `03:01:55.240007+03:00`, attempt 3 TX at `03:02:03.380821+03:00`.
- `/cancel` was queued at `03:02:08.564017+03:00` and physically written at `03:02:08.572933+03:00`; firmware acceptance followed at `03:02:08.644662+03:00`.
- Firmware cancellation state: `DELIVERY CANCEL user=EC14/31 attempts=3 status=unknown queue_removed=0`.
- Exact required SYSTEM output: `[SYS] DELIVERY CANCELLED: status unknown`.

## Post-cancel proof

- Post-cancel raw-event observation remained active for at least 30 seconds; the next sender telemetry snapshot was at `03:02:19.221+03:00`, and the next peer reconnect evidence was at `03:03:19.526+03:00`, covering 70.9 seconds from cancellation acceptance.
- After cancellation acceptance there was no `TX USER RETRY` for `EC14/31`, no attempt `4/5` or `5/5`, no new `WAIT_ACK`, no new retry backoff, no `DELIVERY FAILED: no ACK`, and no `DELIVERY ACK`.
- The post-cancel sender telemetry remained settled; final status returned `connected=true` and `queued_tx=0`.
- The cancellation was not interpreted as definite non-delivery; status remained unknown because the USER had already been physically transmitted.

## Restore and final state

- Peer was physically restored after the 30-second proof and reconnected. Reconnect evidence included `s2 state=connected` and `/id` output `LoRa-Chatter-72E0`.
- Both nodes were returned to `/chat`; `/help` confirmed `current=CHAT echo=OFF` on both nodes.
- Final status for both sessions: connected, `queued_tx=0`. No pending reliable USER, WAIT_ACK, or retry/backoff remained; no resend was performed.
- Both sessions were closed and the single SerialTerminal agent process ended with normal EOF.

## Scope

Only the physically-sent in-flight USER -> `/cancel` -> future retries stop -> status unknown scenario was run. No queued-unsent cancellation, `/cancel all`, queue-full, lost USER, lost ACK, wrong/stale ACK, or ECHO scenario was combined with this run.

Evidence files in this bundle are exact copies of the agent process forensic and companion console logs.
