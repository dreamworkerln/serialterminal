# Generic `chatter.reliable_user` sweep, 1200 samples

Result: INCONCLUSIVE for RF quality; requested execution completed.

## Setup

Before measurement, both BLE Chatter nodes reported the same `/config` baseline:
470 MHz, SF7, BW 500 kHz, power 2 dBm; heartbeat and diagnostics were OFF, retry
was ON with 5 attempts. Sessions were `s1` (LoRa-Chatter-1B44) and `s2`
(LoRa-Chatter-72E0). Both sessions were opened in one long-lived SerialTerminal
agent process (PID 100323). Initial `open` requests used the wrong field name and
returned `invalid_request`; corrected requests using `device_key` opened both
sessions before measured traffic began.

## Requested plan and execution

One `chatter.reliable_user` generic sweep (`sweep_id=sw1`) used:

- Frequency: 470000000 Hz (470 MHz)
- SF: 7
- TX power: 2 dBm
- Bandwidth axis: 125000, 250000, 500000 Hz
- Payload axis: 1, 200 bytes
- Direction axis: `s1>s2`, `s2>s1`
- Repetitions: exactly 100 per coordinate
- Total requested: 3 × 2 × 2 × 100 = 1200 samples

The API reported `total_samples=1200`, then terminal `state=completed` with
`completed_samples=1200` and `current=null`. The final sweep event cursor and
head cursor were both 1226. The job was closed with `sweep_close`. No other sweep
was started, and no measured sample was sent through a manual per-sample
`send_line` loop.

RF quality is INCONCLUSIVE. This report makes no RF-quality or sample anomaly
classification.

## Restored state and evidence

After the job, both nodes were set back to 470 MHz, SF7, BW 500 kHz; final
`/config` responses confirmed power 2 dBm, heartbeat OFF, retry ON with 5
attempts, and diagnostics OFF. Both sessions were closed. The SerialTerminal
agent process exited with status 0.

- `serialterminal.log` is the complete raw forensic log from the sole agent process.
- `serialterminal.console.log` is its complete companion console log.
