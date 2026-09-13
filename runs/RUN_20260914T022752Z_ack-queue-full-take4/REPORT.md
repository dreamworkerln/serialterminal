# ack-queue-full-take4

Result: INCONCLUSIVE

Firmware: dreamworkerln/lora-sack-protocol@unknown
SerialTerminal: dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21

## Nodes and setup

- Sender: `LoRa-Chatter-1B44` (session `s1`, BLE `44:1B:F6:8D:B7:A9`).
- Powered-off/returned peer: `LoRa-Chatter-72E0` (session `s2`, BLE `E0:72:A1:D5:4C:15`).
- Both sessions were opened with `profile: "chatter"`; both were connected, `queued_tx=0`, echo `OFF`, and `/both` was confirmed.
- Peer `LoRa-Chatter-72E0` was powered off and later returned. No firmware was flashed and `/reboot` was not used.

## Stimulus and evidence

- In-flight payload: `QFULL4_INFLIGHT_20260914T`, logical identity `EC14/26`. `TX USER ... attempt=1/5` and `DELIVERY WAIT_ACK ... queue=0` were observed.
- Waiting payloads submitted: `QFULL4_WAIT_01_20260914T` through `QFULL4_WAIT_04_20260914T`. The remaining four and the overflow probe were not submitted.
- Firmware acceptance progression observed: `waiting=1/8 in_flight=1`, `waiting=2/8 in_flight=1`, `waiting=3/8 in_flight=1`.
- The first USER reached `DELIVERY FAILED user=EC14/26 attempts=5/5 ... queue=0` before `waiting=8/8`; therefore the required queue-full proof was unavailable and the run is `INCONCLUSIVE`.
- No `INPUT QUEUE FULL` line occurred during this run. The earlier historical telemetry `drops=8` was not used as reliability-queue evidence.
- Overflow payload would have been `QFULL4_REJECT_20260914T`, but it was not sent. No `SEND QUEUE FULL` line exists; no overflow identity, TX, peer RX, or ACK exists.

## Restore and final state

- Peer was powered back on and the session reconnected.
- Accepted USER queue drained naturally after peer return: WAIT payloads 02, 03, and 04 were received and ACKed; final sender status reported `queued_tx=0`.
- Both nodes were set to `/chat`; both final statuses were connected with `queued_tx=0`; output telemetry confirmed `state=CHAT` and console confirmed `echo=OFF`.
- Sessions were closed and the single agent process ended with normal EOF.

Exact logs are copied unchanged from the agent run; the companion console log is not reconstructed.
