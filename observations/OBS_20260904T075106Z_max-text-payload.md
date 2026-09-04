# Node observation

Observed: 2026-09-04T07:51:06Z
Task: maximum accepted text payload length
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@1e2fe8aa1820bd4c5990505b37ba58436c89de18
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup
- BLE sessions to LoRa-Chatter-1B44 (44:1B:F6:8D:B7:A9) and LoRa-Chatter-72E0 (E0:72:A1:D5:4C:15).
- Tests used `send_line`; the terminating LF was not included in the payload byte count.

## Actions
- Sent ASCII payloads from 1B44 to 72E0 at 64, 128, 192, 200, 201, 202, 204, 208 and 224 bytes.
- Sent UTF-8 `Я` payloads from 1B44 to 72E0: 100 characters (200 bytes) and 101 characters (202 bytes).
- Sent a 200-byte ASCII payload from 72E0 to 1B44.

## Evidence
- 200 ASCII bytes were received completely by 72E0; final peer RX fragment ended with `AAAAAAAAAAAAAAAAA\n` and RSSI/SNR/Q was `-30/+10/Q100`.
- 201, 202, 204, 208 and 224 ASCII bytes produced no peer RX within the 20-second wait.
- 100 UTF-8 `Я` characters (200 bytes) were received completely by 72E0; final peer RX fragment ended with `ЯЯЯЯЯЯЯЯ\n`, RSSI/SNR/Q `-30/+9/Q100`.
- 101 UTF-8 `Я` characters (202 bytes) produced no peer RX within the 20-second wait.
- 200 ASCII bytes were received completely by 1B44 from 72E0; final peer RX fragment ended with `BBBBBBBBBBBBBBBB\n`, RSSI/SNR/Q `-30/+9/Q100`.
- Observed maximum accepted text payload in both tested directions: 200 bytes. Host-side UTF-8 encoding was used for the Cyrillic test; firmware encoding contract was not otherwise established.

## Anomalies / conflicts
- none

## Final state
- Echo and output mode were not changed. Test sessions `s3` and `s4` were closed.

## Evidence pointer
- `/tmp/serialterminal-agent-elevated-20260904.log`
