# Focused hardware scenario: reliable USER queue full

Result: INCONCLUSIVE
Observed: 2026-09-13T22:26:42Z
Firmware: unknown (`dreamworkerln/lora-sack-protocol`)
SerialTerminal: `dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21`

## Setup

- Dynamic discovery found two current BLE devices; canonical `/id` identities were `LoRa-Chatter-1B44` and `LoRa-Chatter-72E0`.
- Sender: `LoRa-Chatter-1B44`.
- Powered-off/returned peer: `LoRa-Chatter-72E0`.
- Both sessions were connected initially, host `queued_tx=0`, `/help` showed `echo=OFF`, and both nodes were set to `/both`.
- One SerialTerminal agent process was used. No source, firmware, reboot, flash, or cancellation command was used.

## Attempted scenario and exact evidence

- In-flight payload: `QFULL_INFLIGHT_20260914T`; firmware identity `EC14/16`; evidence included `TX USER ... attempt=1/5` and `DELIVERY WAIT_ACK ... queue=0`.
- The first in-flight USER reached `attempt=5/5` and `DELIVERY FAILED` before the requested eight waiting payloads could be accepted.
- `QFULL_WAIT_01_20260914T` was then accepted with `DELIVERY QUEUED ... waiting=1/8 in_flight=1`, but became the next in-flight USER (`EC14/17`) and also eventually failed at `5/5`.
- `QFULL_WAIT_02_20260914T` was accepted with `DELIVERY QUEUED ... waiting=1/8 in_flight=0`, then transmitted as `EC14/18` after peer return and received by the peer with matching ACK.
- Requested accepted waiting payloads `01..08` and progression `1/8 -> 8/8` were not established.
- Overflow payload `QFULL_REJECT_<unique>` was not sent. Therefore exact `[SYS] SEND QUEUE FULL: message not accepted` was not observed, and no rejection/non-enqueue/RF-lifecycle claim is made.

## Recovery and final state

- Peer was physically returned by the human and reconnected; transport lifecycle included disconnecting/reconnecting/connected.
- Accepted `QFULL_WAIT_02_20260914T` drained naturally and was delivered; final observed sender status was connected with `queued_tx=0`.
- Both nodes were returned to `/chat`; `/help` showed `echo=OFF` on both.
- Both sessions were closed and the agent process terminated via normal EOF.
- A 10-second post-drain observation window completed without any `QFULL_REJECT` payload, because that probe was never sent.

## Verdict

INCONCLUSIVE. The queue-full acceptance criteria were not exercised: the bounded queue never reached `8/8`, and the explicit queue-full rejection was not produced. The exact forensic and companion logs are preserved in this bundle without reconstruction.
