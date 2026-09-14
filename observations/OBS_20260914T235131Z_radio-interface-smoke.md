# Node observation

Observed: 2026-09-14T23:51:31Z
Task: LoRa-Chatter SerialTerminal radio interface smoke
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@159f7a1ab52fb8f615af33b175545f13e04dd989
Firmware: unknown

## Setup

- Two BLE LoRa-Chatter nodes discovered and opened with `profile:"chatter"`; each exposed `chat` and `telemetry` streams.

## Actions

- Sent unique USER payloads sequentially in both directions.
- Queried `/help`, `/id`, and exercised `/tele`, `/both`, `/chat`.

## Evidence

- Both directions produced peer CHAT, `RX USER`, matching `RX ACK`, and `DELIVERY ACK` at attempt `1/5`.
- A burst of `/help` plus `/id` produced an incomplete/misassembled help line on one session; a fresh single `/help` was complete.

## Anomalies / conflicts

- Burst/timing anomaly requires follow-up isolation between BLE notification loss and presentation/line assembly.

## Final state

- Sessions closed; output mode restored to `CHAT`; ECHO remained `OFF`.

Run bundle: runs/RUN_20260914T235131Z_radio-interface-smoke/
