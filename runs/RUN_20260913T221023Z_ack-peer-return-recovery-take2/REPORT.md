# ack-peer-return-recovery-take2

Result: PASS

Firmware: unknown
Firmware repository: dreamworkerln/lora-sack-protocol
SerialTerminal exact SHA: 5b98a61716b28d2b127370be94708890e59b5d21

Sender: LoRa-Chatter-1B44 (session s1)
Powered-off/returned peer: LoRa-Chatter-72E0 (session s2)

## Setup

- Fresh dynamic discovery found both BLE transports; no prior run identifiers or paths were reused.
- `/id` confirmed `LoRa-Chatter-1B44` and `LoRa-Chatter-72E0`.
- Both sessions were connected with `queued_tx=0`; both were set to `/both`.
- ECHO was not enabled (`echo_req=0`, `echo_rep=0`).
- The operator confirmed `LoRa-Chatter-72E0` physically powered off before injection.

## Reliable USER

- Payload: `PEER_RETURN_TAKE2_20260914T1020Z`.
- Logical USER identity: `EC14/13` (sender session `s1`, user sequence `13`).
- Attempt 1/5: `TX USER seq=13 frame=44B user=32B`, then `WAIT_ACK user=EC14/13 attempt=1/5 queue=0`.
- First ACK timeout and retry start: `ACK TIMEOUT ... attempt=1/5`, then `RETRY ... next_attempt=2/5 in=2412ms`.
- Four ACK timeouts occurred for attempts 1/5 through 4/5; four retry/backoff schedules followed. Retry defer was not observed.
- Every physical retry retained `seq=13`, identity `EC14/13`, frame/user sizes `44B/32B`, and the same payload. Attempts observed: 1/5, 2/5, 3/5, 4/5, 5/5.
- Sender printed `> PEER_RETURN_TAKE2_20260914T1020Z` exactly once; retries produced no additional `>`.

## Peer return and recovery

- After the first timeout/retry evidence at `2026-09-14 01:08:10.326+03:00`, the operator was immediately asked to power on `LoRa-Chatter-72E0`; confirmation was received before recovery observation continued. Human chat request/confirmation timestamps are not emitted by SerialTerminal, so their exact wall-clock values are not present in the immutable logs; order is preserved.
- The peer session recovered through the expected reconnect path, including connect-preamble `/id` and canonical identity `LoRa-Chatter-72E0`.
- The existing pending USER continued; no manual resend, new USER, reboot, or reliability-state manipulation occurred.
- On the peer: `RX USER session=EC14 seq=13 frame=44B user=32B ... disposition=0` (NEW), followed by exactly one semantic CHAT line: `< [-35/+8 Q100] PEER_RETURN_TAKE2_20260914T1020Z`.
- Peer ACK: `TX ACK ... ack_to=EC14/13 frame=14B OK`.
- Sender matching ACK: `RX ACK ... ack_to=EC14/13`.
- Final delivery: `DELIVERY ACK user=EC14/13 attempts=5/5 ... queue=0`.
- No `DELIVERY FAILED` or `[SYS] DELIVERY FAILED: no ACK` appeared.

## Post-delivery and final state

- Observation continued for more than 10 seconds after the delivery ACK. No extra retransmission, WAIT_ACK, or retry/backoff remained; sender telemetry showed queue `0`.
- Both nodes were returned to `/chat`; ECHO remained off.
- Final statuses: both sessions connected and `queued_tx=0`. Sessions were closed and the single SerialTerminal agent process ended normally via EOF.
- Exact forensic and console logs from this agent process are copied into this bundle without reconstruction.
