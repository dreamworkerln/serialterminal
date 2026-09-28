# Reliable USER sweep report

Result: INCONCLUSIVE

## Task

Execute one generic `chatter.reliable_user` sweep at 470 MHz, SF7, 2 dBm, for
bandwidths 125, 250 and 500 kHz; payloads 1 and 200 bytes; directions `s1>s2` and
`s2>s1`; exactly 1000 repetitions per coordinate. The requested matrix contains
12000 samples.

## Setup and baseline

- SerialTerminal: `dreamworkerln/serialterminal@7cf0459c4e00a81592d447e0592e83a1142e18d9`
- Firmware provenance: unknown; it was not queried for this task.
- Transport: BLE, one SerialTerminal agent process, sessions `s1` and `s2`.
- Nodes identified via `/id`: `LoRa-Chatter-1B44` (`s1`) and
  `LoRa-Chatter-72E0` (`s2`).
- Pre-run `/config` on both: power 2 dBm, frequency 470 MHz, SF7, BW 500 kHz,
  heartbeat OFF, retry ON (5 attempts), diagnostic OFF.

## Actual plan and execution

The single job `sw1` used adapter `chatter.reliable_user` and this plan:

```json
{
  "constants": {
    "frequency_hz": 470000000,
    "power_dbm": 2,
    "sf": 7
  },
  "axes": [
    {"name": "bandwidth_hz", "values": [125000, 250000, 500000]},
    {"name": "payload_bytes", "values": [1, 200]},
    {"name": "direction", "values": ["s1>s2", "s2>s1"]}
  ],
  "repetitions": 1000,
  "options": {}
}
```

SerialTerminal accepted the plan with `total_samples: 12000`. The terminal progress
reported 1186 completed samples. The job then entered terminal state `failed` with
`adapter_timeout` in phase `sample_settlement`. The remaining 10814 planned samples
were not executed. No second or focused sweep was run.

## RF quality

INCONCLUSIVE; RF quality was not assessed. No CRC, header, ACK, retry, timeout or
other RF-quality classification or point selection was performed.

## Final state

After the sweep, both sessions reported connected. The original configuration was
restored on both nodes and confirmed with `/config`: 2 dBm, 470 MHz, SF7, BW 500 kHz,
heartbeat OFF, retry ON (5 attempts), diagnostic OFF. Both sessions were closed;
SerialTerminal PID 95003 was verified no longer running.

## Evidence

- `serialterminal.log`: exact forensic log from the run process.
- `serialterminal.console.log`: exact companion console log from the same process.
