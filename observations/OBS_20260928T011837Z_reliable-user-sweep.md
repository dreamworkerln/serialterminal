# Node observation

Observed: 2026-09-28T01:18:37Z
Task: Generic reliable USER sweep, sparse payload matrix
Result: INCONCLUSIVE
SerialTerminal: dreamworkerln/serialterminal@7cf0459c4e00a81592d447e0592e83a1142e18d9
Firmware: dreamworkerln/lora-sack-protocol@unknown

Run bundle: runs/RUN_20260928T011837Z_reliable-user-sweep/

## Setup

Two BLE Chatter nodes, identified as `LoRa-Chatter-1B44` (`s1`) and
`LoRa-Chatter-72E0` (`s2`). Baseline `/config` on both was 2 dBm, 470 MHz, SF7,
500 kHz, heartbeat OFF, retry ON (5 attempts), diagnostic OFF.

## Actions

Started one `chatter.reliable_user` job with frequency 470 MHz, SF7, power 2 dBm,
bandwidths 125/250/500 kHz, payloads 1/200 bytes, both directions, and 1000
repetitions per coordinate. The accepted plan contained 12000 samples. The job
reported 1186 completed samples before terminating with `adapter_timeout` during
`sample_settlement`; 10814 planned samples were not executed. No additional sweep
was run.

## Evidence

The full forensic and companion console logs are in the run bundle. Sweep job state
was `failed`; RF quality result is INCONCLUSIVE and was not assessed.

## Anomalies / conflicts

No RF-quality classification was performed. The adapter's `sample_settlement` timeout
does not by itself establish a node disconnect. Both sessions reported connected in
the post-job status check.

## Final state

Both nodes were restored to the captured baseline and verified via `/config`. Both
sessions were closed and SerialTerminal PID 95003 was verified stopped.
