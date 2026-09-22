# Node observation

Observed: 2026-09-22T06:10:29Z
Task: reliable USER retransmission after controlled ACK loss
Result: BLOCKED
SerialTerminal: dreamworkerln/serialterminal@fedfa29d5c8b07613e49e9425bbc2bbc5b74c165
Firmware: dreamworkerln/lora-sack-protocol@6c08084891f4940dcbe804c0c4ef26feea9b4eb5

Both BLE physical nodes, `LoRa-Chatter-1B44` and `LoRa-Chatter-72E0`, reported clean source provenance `6c08084891f4940dcbe804c0c4ef26feea9b4eb5`, not the required clean `5996d55ee9289aee2b02583bd0eabb20a1e322ff`. Therefore no measured LoRa RF baseline, ACK-loss retry, duplicate-suppression, or five-attempt exhaustion scenario was started.

The executor left both nodes with heartbeat and diagnostics off, echo-loop stopped, and confirmed radio power 2 dBm. The run recorded no forensic gaps or transport reconnect/flapping.

Run bundle: runs/RUN_20260922T061029Z_reliable-user-ack-loss-retry/
