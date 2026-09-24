# TODO_006 diagnostic size and cadence matrix

Observed: 2026-09-24T11:19:17Z launch; finalized 2026-09-24T11:37:33Z
Result: PASS

## Identity

Both physical BLE nodes reported firmware
`3b386dfa3eae68be057ab9aeec37a89367773839`, `state=clean`, and image
validation `OK`. Runtime SHA: `04756c38a41dae8ebac063fed584a066187071b6`.
Observation workspace base: `be7b3b184941a3826a9727abbaf3f8d6abee3638`.

Initiator A: `LoRa-Chatter-1B44`; responder B: `LoRa-Chatter-72E0`.

## Fast matrix

PHY was 470 MHz / SF7 / BW500 kHz / power 2 dBm. Cadence deltas use only
wrap-safe differences of A's device-side `start_us` values.

| size | PING | OK/NRP/CRC/HDR | TX ms min/avg/max | start delta us min/avg/max | violations <1,000,000 | size-match |
|---:|---:|---:|---:|---:|---:|:---:|
| 16 | 105 | 104/1/0/0 | 14/14.0/14 | 1,001,875/1,644,056.5/67,597,122 | 0 | yes |
| 32 | 28 | 28/0/0/0 | 19/19.0/19 | 1,001,901/1,003,362.6/1,005,025 | 0 | yes |
| 64 | 85 | 84/1/1/0 | 31/31.0/31 | 1,001,935/1,003,462.1/1,007,131 | 0 | yes |
| 200 | 84 | 82/2/1/0 | 81/81.0/81 | 1,001,985/1,005,250.7/1,079,042 | 0 | yes |
| 225 | 110 | 110/0/0/0 | 90/90.0/90 | 1,002,921/1,004,475.7/1,006,064 | 0 | yes |
| 255 | 30 | 29/1/1/0 | 101/101.1/102 | 1,002,915/1,006,549.4/1,068,039 | 0 | yes |

Diagnostic summaries reported no HDR errors. The 64B and 200B rows include
the observed CRC/NRP recovery counters; the cadence floor remained satisfied.
No fatal radio state, queue drop, or runaway cadence was observed.

Representative 255B exchange: A PING seq 713, `start_us=2938921996`, B RX
frame=255B, B TX PONG request `4176/713` frame=255B, A RX matching PONG.

## Slow point

PHY was 470 MHz / SF12 / BW62.5 kHz / power 2 dBm, diagnostic frame 16B.
There were 12 A PING starts and 12 matching 16B PONGs. TX telemetry
`time=<ms>` was 2639/2639.1/2640 ms. Device-side start deltas were
5,791,975/5,946,262.7/6,047,996 us; count below the supplied 5,276,000 us
floor was 0. Acceptance used only `start_us`, with no host timestamp input.

Representative slow exchange: A PING seq 743,
`start_us=3086066151`, B RX frame=16B, B TX PONG request `4176/743`
frame=16B, A RX matching PONG.

## Final state and evidence

Both nodes ended with heartbeat OFF, diagnostic OFF, power 2 dBm, no pending
delivery, no fatal state, and final PHY 470 MHz / SF12 / BW62.5 kHz. Both
sessions closed cleanly. The forensic log and companion console log are exact
copies from the single long-lived agent process. No explicit post-close
stdout/history replay was requested; the automatic collapsed completion
transcript was present and left collapsed.
