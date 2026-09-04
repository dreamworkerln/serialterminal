# Node observation

Observed: 2026-09-04T13:41:43Z
Task: empty USER and payload-size transmission test
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@91d94d0a536d97e54380eb028dd4845e828cc91a
Firmware: dreamworkerln/lora-sack-protocol@49fcd72a26efa7f9f7029735242fa62d4fe66c1e

## Setup
- BLE sessions s1=LoRa-Chatter-1B44 and s2=LoRa-Chatter-72E0; chat and telemetry subscribed.
- Sequential USER sends from s1 to s2; unique ASCII payloads; no fault injection.

## Actions
- Sent an empty line (`LF`) from s1; waited 5 s for peer chat RX.
- Sent payloads of 1, 8, 32, 64, 128 and 200 UTF-8 bytes, one at a time.
- Checked matching peer RX chat output and firmware TX USER telemetry.

## Evidence
- Empty line: transport `written`, no peer chat RX in 5 s; no USER TX telemetry observed.
- Peer RX matched `A`, 8 B, 32 B, 64 B, 128 B and 200 B payloads; all showed `Q100%`.
- Firmware TX telemetry: `user=1B time=1157 ms`; `user=8B time=1321 ms`; `user=32B time=2140 ms`; `user=64B time=3287 ms`; `user=128B time=5253 ms`; `user=200B time=7711 ms`.
- Host event latency from local `> payload` to peer RX: approximately 8, 50, 53, 56, 53 and 97 ms respectively.

## Anomalies / conflicts
- Empty USER payload is outside the documented 1..200 byte range and was not delivered.
