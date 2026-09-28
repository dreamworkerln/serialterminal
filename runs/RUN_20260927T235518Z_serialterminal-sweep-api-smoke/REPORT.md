# SerialTerminal sweep API smoke test

Result: PASS for the requested API availability and lifecycle check.

## Task

Verify that the deployed SerialTerminal runtime accepts and completes a minimal `chatter.reliable_user` sweep. This was an API smoke test, not an RF characterization run.

## Runtime and setup

- SerialTerminal: `dreamworkerln/serialterminal@7cf0459c4e00a81592d447e0592e83a1142e18d9`
- Firmware provenance: unknown; no `/version` result was collected.
- Transport: BLE, both nodes opened in the same long-lived agent process.
- Node A: `LoRa-Chatter-1B44` (`44:1B:F6:8D:B7:A9`), session `s1`.
- Node B: `LoRa-Chatter-72E0` (`E0:72:A1:D5:4C:15`), session `s2`.
- The agent process began with the preceding discovery request. The preserved logs include discovery, both opens, the sweep, and cleanup.

## Sweep

`sweep_start` returned `ok: true`, `state: running`, `sweep_id: sw1`, and `total_samples: 2`. The plan used 470 MHz, 2 dBm, 500 kHz bandwidth, SF7, one-byte payloads, both directions, and one repetition per direction.

`sweep_observe` returned `state: completed` with 2 of 2 samples completed. The event history includes sample identities `118C/0` for `s1>s2` and `EBE8/1` for `s2>s1`. This confirms the API accepted and completed the requested execution loop. One repetition is insufficient to characterize RF quality.

CRC error reports were logged after the sweep completed (first at 02:55:34 local time); a later header error was also logged while the sessions remained open. These events were outside the completed sweep's two sample intervals and are preserved in the forensic log. They do not change the API smoke-test result, and no RF-quality conclusion is drawn.

## Cleanup and evidence

The retained sweep state was closed, both node sessions were closed, and the SerialTerminal process exited. The forensic and companion console logs are exact copies from that process.

RF conclusion: INCONCLUSIVE for characterization; this run was limited to one sample per direction and had CRC/header error reports outside the sample intervals.

No separate OBS is required: this run records an API smoke check and establishes no reusable hardware-behavior finding.
