# Node observation

Observed: 2026-09-14T00:04:55Z
Task: `/cancel` on in-flight reliable USER
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@5b98a61716b28d2b127370be94708890e59b5d21
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup

- Sender `LoRa-Chatter-1B44`; peer `LoRa-Chatter-72E0` physically powered off after setup.
- Peer disconnect/reconnect evidence was captured before stimulus.

## Actions

- Sent `CANCEL_INFLIGHT_20260914T` from sender.
- Confirmed USER identity `EC14/31`, physical attempt 1, and `WAIT_ACK`.
- `/cancel` was processed after attempts 2 and 3 had already occurred.

## Evidence

- Firmware emitted `DELIVERY CANCEL user=EC14/31 attempts=3 status=unknown queue_removed=0`.
- Exact SYSTEM output: `[SYS] DELIVERY CANCELLED: status unknown`.
- During the required 30-second post-acceptance observation, no later retry TX or `DELIVERY FAILED` appeared.

## Anomalies / conflicts

- Attempts 2 and 3 began before cancellation acceptance; ordering is preserved in the run report. This does not change the post-acceptance no-further-retry result.

## Final state

- Peer restored and reconnected; both nodes `/chat`, `echo=OFF`, `queued_tx=0`, no pending reliable USER. Sessions closed.

Run bundle: runs/RUN_20260914T000455Z_ack-cancel-inflight/
