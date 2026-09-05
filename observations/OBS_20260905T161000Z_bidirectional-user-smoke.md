# Node observation

Observed: 2026-09-05T16:09:55Z
Task: bidirectional USER smoke through SerialTerminal JSONL agent
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@e6c025805d39c95b959272cb8a9d8c74ddc6eb23
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup
- BLE sessions `s1` = LoRa-Chatter-1B44 (`44:1B:F6:8D:B7:A9`) and `s2` = LoRa-Chatter-72E0 (`E0:72:A1:D5:4C:15`); both connected with `chat` and `telemetry` streams.
- No fault injection; echo remained OFF.

## Actions
- Discovered devices with `discover(scope=auto)` and opened both sessions with default `auto_id=true`.
- Sent `st-check-A-to-B-20260905` from `s1`, then `st-check-B-to-A-20260905` from `s2`, observing both sessions with returned raw cursors.
- Sent `/chat` to both sessions and closed both sessions.

## Evidence
- JSON `send_line` responses accepted both messages as `state=queued`, `tx_id=1`; forensic log later recorded `tx_state=written` for both.
- A→B: `s2` CHAT showed `< [-11/+10 Q100] st-check-A-to-B-20260905`; telemetry showed `RX USER ... seq=2` and `TX ACK ... ack_to=6C42/2`; `s1` showed `DELIVERY ACK user=6C42/2 attempts=1/5 ... queue=0`.
- B→A: `s1` CHAT showed `< [-12/+10 Q100] st-check-B-to-A-20260905`; telemetry showed `RX USER ... seq=3` and `TX ACK ... ack_to=D20F/3`; `s2` showed `DELIVERY ACK user=D20F/3 attempts=1/5 ... queue=0`.
- Companion console log contained matching `[I]` inputs and `[O]` local/peer lines; JSON `observe.result.lines` contained the same completed logical CHAT lines and telemetry lines. Raw JSON `events` preserved BLE chunk boundaries and `data_b64`.
- Final `/chat` response on both nodes: telemetry `OUTPUT MODE source=2 state=CHAT`; CHAT `[SYS] OUTPUT CHAT`.

## Anomalies / conflicts
- none

## Final state
- Both sessions closed cleanly; output mode was returned to CHAT; echo remained OFF.

## Evidence pointer
- `logs/serialterminal-20260905-190638-221907-p153835.log`
- `logs/serialterminal-20260905-190638-221907-p153835.console.log`
