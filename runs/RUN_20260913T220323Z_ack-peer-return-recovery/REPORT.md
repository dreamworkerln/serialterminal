# ack-peer-return-recovery

Result: FAIL

Firmware: unknown
Firmware repository: dreamworkerln/lora-sack-protocol
SerialTerminal exact SHA: 5b98a61716b28d2b127370be94708890e59b5d21

Sender: LoRa-Chatter-1B44 (session s1)
Powered-off/returned peer: LoRa-Chatter-72E0 (session s2)

## Setup

- Fresh dynamic discovery found the two BLE transports; no prior identifiers or paths were reused.
- `/id` confirmed `LoRa-Chatter-1B44` and `LoRa-Chatter-72E0`.
- Both sessions were connected with `queued_tx=0`; both were set to `/both`.
- ECHO was not enabled in this run (`echo_req=0`, `echo_rep=0` in observed telemetry).
- The operator confirmed that `LoRa-Chatter-72E0` was physically powered off before USER injection.

## Transaction evidence

- Payload: `PEER_RETURN_20260914T0945Z`.
- Logical USER identity: `EC14/12` (sender session `s1`, firmware user sequence `12`).
- First physical attempt: `TX USER seq=12 frame=38B user=26B attempt=1/5 OK`.
- First WAIT_ACK: `DELIVERY WAIT_ACK user=EC14/12 attempt=1/5 timeout=1856ms queue=0`.
- First timeout: `DELIVERY ACK TIMEOUT user=EC14/12 attempt=1/5`.
- Retry/backoff: `DELIVERY RETRY user=EC14/12 next_attempt=2/5 in=1221ms`.
- The sender observed attempts 1/5, 2/5, 3/5, 4/5, and 5/5. Every retry retained `seq=12`, identity `EC14/12`, frame/user sizes `38B/26B`, and the same payload; total physical attempts were 5/5.
- `>` presentation occurred once, on attempt 1; no semantic peer CHAT USER or matching ACK was observed.

## Peer return and outcome

- After attempt 3 timeout/retry evidence, the operator was asked to power on `LoRa-Chatter-72E0`; the operator then confirmed it was powered on. The agent log does not timestamp human chat messages, so the exact wall-clock timestamps of the request and confirmation are not reconstructible from the immutable SerialTerminal logs; their order is preserved here.
- The peer session showed `disconnected`, `reconnecting`, then connect-preamble `/id` and `connected`; reconnect identity was confirmed as `LoRa-Chatter-72E0`.
- Reconnect completed only after the sender had already emitted `DELIVERY FAILED user=EC14/12 attempts=5/5` and `[SYS] DELIVERY FAILED: no ACK`.
- No peer RX USER disposition or peer ACK evidence was observable. No sender matching ACK or final DELIVERY ACK was observed.

## Verdict checks

- Initial physical peer-off before attempt 1: PASS by operator confirmation.
- Initial WAIT_ACK and ACK timeout before return: PASS.
- Pending USER identity/payload across retries: PASS.
- Peer returned before bounded final failure: FAIL; reconnect was observed after final failure.
- Existing USER completed with matching ACK: FAIL.
- No more than 5 physical attempts: PASS (exactly 5/5).
- `DELIVERY FAILED` absent: FAIL; it was observed.
- Final queue/retry state: PASS; final status for both sessions reported `connected`, `queued_tx=0`, and no pending retry remained.
- Safe final state: both nodes were returned to `/chat`, ECHO remained off, sessions were closed, and the single agent process terminated through EOF.

## Post-delivery observation

Observation continued after failure and after peer reconnect. No later retransmission or pending retry appeared. Both final status calls reported `queued_tx=0`.

Run bundle contains the exact `serialterminal.log` and `serialterminal.console.log` copied from the single agent process; neither was reconstructed.
