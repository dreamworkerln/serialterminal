# Hardware observation: normal USER ACK flow

- Date: 2026-09-04 UTC
- Transport: BLE; sessions `s1` and `s2`; output mode BOTH; echo OFF on both.
- A: `LoRa-Chatter-1B44` via `44:1B:F6:8D:B7:A9`; B: `LoRa-Chatter-72E0` via `E0:72:A1:D5:4C:15`.
- Initial relevant state: `user=0`, `err=0`, `pending=0` observed in periodic telemetry.
- Baseline cursors before 1A: A=188, B=161.
- Exact write to A: `ack-normal-A-001` (tx_id=5; queued then written).
- A CHAT exact protocol excerpt: `DELIVERY QUEUED source=2 bytes=16 waiting=1/8 in_flight=0`; `TX USER seq=0 frame=28B user=16B attempt=1/5 OK`; `> ack-normal-A-001`; `DELIVERY WAIT_ACK user=86F8/0 attempt=1/5 timeout=1856ms queue=0`; `PEER_REPORT our_seq=0 RSSI=-33 dBm SNR=+10 dB Q=100%`; `RX ACK session=D648 seq=0 ack_to=86F8/0 frame=14B RSSI=-28.0 dBm SNR=+7.8 dB Q=100%`; `DELIVERY ACK user=86F8/0 attempts=1/5 elapsed=1456ms queue=0`.
- B CHAT exact application/protocol excerpt: `RX USER session=86F8 seq=0 frame=28B user=16B RSSI=-33.0 dBm SNR=+9.5 dB Q=100% disposition=0`; `< [-33/+10 Q100] ack-normal-A-001`; `TX ACK seq=0 ack_to=86F8/0 frame=14B OK time=1157 ms guard=500ms`.
- The same protocol lines were also present in TELEMETRY.
- Result: A->B application delivery and matching ACK succeeded with no retry/failure, but ACK/WAIT_ACK/seq/session/attempt details polluted CHAT; presentation contract mismatch, so gate stopped before 1B.
- Final status: both sessions connected, `queued_tx=0`; no further events after cursors A=287, B=281.
