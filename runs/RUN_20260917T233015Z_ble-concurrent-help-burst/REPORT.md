# BLE concurrent `/help` burst test

Observed: 2026-09-17T23:33:45Z
Task: Three concurrent `/help` rounds on LoRa-Chatter-1B44 and LoRa-Chatter-72E0.
Result: FAIL

## Setup

- Discovery returned BLE device keys for both requested Chatter nodes.
- Sessions were opened in one SerialTerminal agent process with `profile:"chatter"`.
- `s1` was LoRa-Chatter-1B44; `s2` was LoRa-Chatter-72E0.
- Both sessions exposed `chat` and `telemetry` streams.
- `/chat` was sent to both sessions and each reported `OUTPUT MODE ... state=CHAT` in telemetry plus `[SYS] OUTPUT CHAT`.
- No reboot, power cycle, firmware change, or source change was performed.

## Actions and classifications

The full isolated help shape used for comparison was the complete sequence beginning with `[SYS] CHATTER HELP`, followed by node identity, CHAT OUTPUT, all documented output/mode/command/control/BLE sections, and ending with the BLE client telemetry line.

| Round | Order | LoRa-Chatter-1B44 (`s1`) | LoRa-Chatter-72E0 (`s2`) |
|---|---|---|---|
| 1 | 1B44, then 72E0 | MALFORMED; raw seq 38–98, final help section incomplete/corrupted | COMPLETE; raw seq 13–105 |
| 2 | 72E0, then 1B44 | MALFORMED; raw seq 101–163, sections missing/corrupted | COMPLETE; raw seq 133–225 |
| 3 | same API batch, 1B44 and 72E0 | MALFORMED; raw seq 191–253, lines visibly mixed/truncated | COMPLETE; raw seq 228–320 |

The three `/help` sends per session were accepted and later had `tx_state:"written"`. No new `/help` was sent to a node before its preceding help response had ended in the observed event stream.

## Separate observations

- Forensic gap: none found in the persisted agent log; no `forensic_gap` marker and no cursor expiry.
- Disconnect/reconnect during the burst: none observed. Each session initially transitioned from the normal open-time `reconnecting` state to `connected`; all status checks during and after the test reported `connected`. No later reconnect state appeared before close.
- Same-node command overlap: none observed; each node received one `/help` at a time.
- Transport send outcome: no `unknown` outcome; all six help writes reached `written`.
- Cause: not inferred. This report records only the observed raw events and logical lines.

## Final state and evidence

- Both sessions were explicitly closed through the agent API.
- Nodes were not rebooted or powered off.
- Exact forensic and companion console logs are stored beside this report.
- SerialTerminal source revision: `5354f062afd64750679a4d5562a29a022025a967`.
- Firmware revision: unknown.

