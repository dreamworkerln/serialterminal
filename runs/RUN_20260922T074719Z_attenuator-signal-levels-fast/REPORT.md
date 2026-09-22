# Fast attenuator signal-level repeat

Result: PASS. BLE audio preflight showed no Bluetooth audio path. Both nodes
confirmed 2 dBm, 470 MHz, SF12 and BW125 before USER transmission.

- A `LoRa-Chatter-1B44` -> B `LoRa-Chatter-72E0`:
  `ATTEN-FAST-A2B-20260922T074719Z` received at -86.0 dBm / +10.2 dB SNR;
  matching ACK completed on attempt 1/5.
- B `LoRa-Chatter-72E0` -> A `LoRa-Chatter-1B44`:
  `ATTEN-FAST-B2A-20260922T074719Z` received at -82.0 dBm / +9.0 dB SNR;
  matching ACK completed on attempt 1/5.

All `observe` requests used `timeout_ms: 1000`; no 15- or 30-second observation
timeouts were used. Sessions were closed after measurement. The exact paired
agent logs are included in this RUN.
