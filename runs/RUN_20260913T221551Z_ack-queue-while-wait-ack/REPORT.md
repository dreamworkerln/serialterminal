# Focused hardware scenario: additional USER while WAIT_ACK

Result: FAIL
Observed: 2026-09-13T22:15:51Z — 2026-09-13T22:17:40Z
Topic: ack-queue-while-wait-ack
Firmware: unknown (`dreamworkerln/lora-sack-protocol` revision was not independently established)
SerialTerminal: `dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21`

## Nodes and setup

- Sender: `LoRa-Chatter-1B44`, session `s1`, BLE `44:1B:F6:8D:B7:A9`.
- Powered-off/returned peer: `LoRa-Chatter-72E0`, session `s2`, BLE `E0:72:A1:D5:4C:15`.
- Dynamic discovery found both nodes; canonical identities came from `/id` connect preambles.
- Both sessions connected before fault setup and reported host `queued_tx=0`.
- `/both` was used for detailed evidence, then both nodes were returned to `/chat`.
- Echo was not enabled; observed telemetry counters remained `echo_req=0 echo_rep=0`.
- No firmware/source/docs/firmware branches were changed or inspected; no reboot, cancel, resend, interference, or flashing was used.

## Fault and ordering

- The human powered off `LoRa-Chatter-72E0` after setup. SerialTerminal recorded `s2` disconnected/reconnecting before the first USER completed.
- FIRST payload: `QUEUE_WAIT_FIRST_20260914T143200Z`.
- SECOND payload: `QUEUE_WAIT_SECOND_20260914T143200Z`.
- FIRST was accepted as `DELIVERY QUEUED ... waiting=1/8 in_flight=0`, then transmitted as logical identity `user=EC14/14` / `seq=14`.
- FIRST entered `WAIT_ACK` at attempt `1/5`, timed out, and retained the same identity and payload through retries `2/5`, `3/5`, `4/5`, and `5/5`.
- SECOND was injected while FIRST was pending/retrying. Firmware telemetry recorded exactly: `DELIVERY QUEUED source=2 bytes=34 waiting=1/8 in_flight=1`.
- No `TX USER` for SECOND occurred while FIRST was pending. FIRST reached final failure at `DELIVERY FAILED user=EC14/14 attempts=5/5 ... queue=1`.
- The human then powered the peer back on. BLE reconnect completed and `/id` again identified `LoRa-Chatter-72E0`.

## First USER result

- FIRST identity/payload remained stable across all five physical attempts.
- FIRST matching ACK: FAIL — no ACK was received before the bounded retry limit.
- FIRST peer RX / disposition: none observed; the peer returned after FIRST final failure.
- FIRST delivery: FAIL. Exact firmware outcome: `DELIVERY FAILED user=EC14/14 attempts=5/5 ... queue=1`.

## Second USER result

- SECOND was automatically dequeued only after FIRST final failure, not after a successful FIRST ACK.
- SECOND physical TX began afterward as `TX USER seq=15 ... attempt=1/5`; therefore SECOND had no physical TX before FIRST completion, but the required “after FIRST ACK” ordering was not met.
- SECOND logical identity: `user=EC14/15` / `seq=15`.
- SECOND required bounded retry and was delivered on attempt `4/5`.
- Peer RX: `RX USER session=EC14 seq=15 ... disposition=0`.
- Peer semantic CHAT: `< [-30/+9 Q100] QUEUE_WAIT_SECOND_20260914T143200Z` exactly once.
- Peer matching ACK: `TX ACK ... ack_to=EC14/15`; sender matching `RX ACK ... ack_to=EC14/15`.
- SECOND delivery: `DELIVERY ACK user=EC14/15 attempts=4/5 ... queue=0`.

## Acceptance assessment

- First USER entered `WAIT_ACK`: PASS.
- Second USER queued while FIRST pending: PASS.
- Queue depth while FIRST pending: `1/8` waiting USER.
- SECOND TX before FIRST completion: no.
- FIRST delivery with matching ACK: FAIL.
- SECOND transmitted after FIRST successful ACK: FAIL; it was transmitted after FIRST final failure.
- SECOND delivery with matching ACK: PASS.
- Final reliability queue: `0`; no pending `WAIT_ACK`, retry, or backoff observed after completion.
- Semantic CHAT presentation: FAIL for the requested scenario because FIRST was never presented; SECOND appeared once, and host `>` markers appeared once per local payload.
- BLE/transport recovery: PASS with note — peer disconnected while powered off, reconnected after return, `/id` preamble completed, and both sessions ended connected before close.

## Safe final state and evidence

- Both nodes were explicitly set to `/chat`.
- Both sessions reported connected and host `queued_tx=0` before close.
- Post-delivery observation lasted 12 seconds with no new events.
- Sessions were closed and the single agent process terminated normally through EOF.
- Exact source logs are copied without reconstruction as `serialterminal.log` and `serialterminal.console.log` in this run bundle.
- Matching observation is required because this is a required reliability scenario with a FAIL outcome.

