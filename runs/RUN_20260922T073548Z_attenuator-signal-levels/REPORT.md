# Attenuator signal-level check

Result: PASS

Two physical BLE Chatter nodes were checked with operator-installed attenuators.
Both nodes were set to and confirmed at 2 dBm, 470 MHz, SF12, BW125; heartbeat,
diagnostic mode, and echo-loop were off/stopped.

- A `LoRa-Chatter-1B44` -> B `LoRa-Chatter-72E0`, payload
  `ATTEN-A2B-20260922T073548Z`: B received USER at RSSI -87.0 dBm, SNR +10.5 dB,
  Q 0%; A completed matching ACK on attempt 1/5.
- B `LoRa-Chatter-72E0` -> A `LoRa-Chatter-1B44`, payload
  `ATTEN-B2A-20260922T073548Z`: A received USER at RSSI -82.0 dBm, SNR +9.8 dB,
  Q 100%; B completed matching ACK on attempt 1/5.

The reverse ACK receive levels were A: -86.0 dBm / +8.2 dB and B: -89.0 dBm / +9.2 dB.

An initial local-command burst on A produced `INPUT QUEUE FULL dropped=1`; the
missing `/config` was resent individually and confirmed before RF transmission.
No USER payload was affected. Both sessions were closed and both nodes were
left at 2 dBm.
