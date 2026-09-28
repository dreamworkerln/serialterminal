# Node observation

Observed: 2026-09-28T02:20:47Z

Task: Generic `chatter.reliable_user` hardware sweep, 1200 samples

Result: INCONCLUSIVE

SerialTerminal revision: unknown

Firmware revision: unknown

Run bundle: `runs/RUN_20260928T022047Z_chatter-reliable-user-1200/`

## Setup

Both BLE Chatter nodes were opened in one SerialTerminal process as `s1`
(LoRa-Chatter-1B44) and `s2` (LoRa-Chatter-72E0). Their pre-run `/config`
responses matched: 470 MHz, SF7, BW 500 kHz, 2 dBm; heartbeat OFF, retry ON
(5 attempts), diagnostics OFF.

## Actions and completion

One generic `chatter.reliable_user` job used frequency 470000000 Hz, SF7,
2 dBm, bandwidths 125000/250000/500000 Hz, payloads 1/200 bytes, directions
`s1>s2` and `s2>s1`, and exactly 100 repetitions per coordinate. The plan was
3 × 2 × 2 × 100 = 1200 samples. `sweep_id=sw1` reached `state=completed` with
`completed_samples=1200` of `total_samples=1200`, then was closed using
`sweep_close`. No additional sweep was run; measured samples were not sent with
manual per-sample `send_line` calls.

## Outcome and evidence

RF quality is INCONCLUSIVE. No RF-quality or anomaly classification is asserted.
The run bundle contains the complete raw `serialterminal.log` and
`serialterminal.console.log` from the agent process.

## Final state

Both nodes were restored to the pre-run radio configuration, confirmed by final
`/config` responses, and both sessions were closed. The SerialTerminal process
exited with status 0.
