# TODO_005 exact-provenance release confirmation

Observed: 2026-09-18T13:55:49Z
Result: PASS

## Request and provenance

- Hardware-test executor run; no source, documentation, skill, TODO, handoff, or firmware changes; no flashing.
- Dynamic discovery found two USB and two BLE transports. One long-lived SerialTerminal agent owned all four sessions and logs.
- USB/BLE pairing by `/id`: `LoRa-Chatter-72E0` USB `5B8F021956` ↔ BLE `E0:72:A1:D5:4C:15`; `LoRa-Chatter-1B44` USB `5B8F072180` ↔ BLE `44:1B:F6:8D:B7:A9`.
- Both USB `/version` responses were exactly: `[SYS] FIRMWARE Chatter git=a7eed47ecae5b21d8c7a72901e2d403c3329cd8e state=clean env=esp32-s3-n16r8`.
- SerialTerminal: `dreamworkerln/serialterminal@ab36ca2405f6cf8dd1a4ce572e96c8de918a754f`.
- Firmware evidence: `dreamworkerln/lora-sack-protocol@a7eed47ecae5b21d8c7a72901e2d403c3329cd8e`, reported by both physical nodes with `state=clean`.

## Host preflight and setup

- Bluetooth audio preflight was read-only. Paired WH-1000XM5 was `Connected: no`; PipeWire showed only built-in audio, with no Bluetooth sink/source or Bluetooth audio stream.
- All sessions opened with `profile=chatter`; output was confirmed `current=CHAT echo=OFF`.
- `/cancel all` was used before measurement and during final cleanup; no ECHO or fault injection was used.

## Measured scenario

- A → B payload `TODO005-A2B-20260918-1`: physical TX `attempt=1/5 OK`; B presented the peer USER exactly once; matching ACK completed `DELIVERY ACK user=26DB/1 attempts=1/5`; no `DELIVERY FAILED`.
- B → A payload `TODO005-B2A-20260918-1`: physical TX `attempt=1/5 OK`; A presented the peer USER exactly once; matching ACK completed `DELIVERY ACK user=CFEC/2 attempts=1/5`; no `DELIVERY FAILED`.
- Both directions had `queue=0` at delivery completion. No unexpected reconnect occurred during measured phase. No `send-outcome-unknown`, forensic gap, or cursor expiry was recorded.

## Final state and evidence

- `/cancel all` and `/chat` completed after measurement; all four sessions were closed normally.
- Exact paired SerialTerminal logs are `serialterminal.log` and `serialterminal.console.log` in this bundle.
- Matching standalone/run-bound OBS is recorded because this is release-closing exact-provenance evidence.

