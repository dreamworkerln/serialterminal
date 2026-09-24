# OBS TODO_006 diagnostic size and cadence matrix

Result: PASS.

Physical two-node validation on exact clean firmware
`3b386dfa3eae68be057ab9aeec37a89367773839` confirmed diagnostic frame sizes
16/32/64/200/225/255B with correlated size-matched PONGs. On
470 MHz/SF7/BW500, the minimum same-size device-side PING-start delta was
1,001,875 us and no delta was below 1,000,000 us. On the separate
470 MHz/SF12/BW62.5 16B point, the minimum delta was 5,791,975 us and no
delta was below the supplied 5,276,000 us floor.

Acceptance used only wrap-safe deltas of firmware `start_us`; host/BLE
timestamps were not used for cadence. A representative 255B and slow 16B
PONG correlation is recorded in the associated RUN report.

Run bundle: runs/RUN_20260924T111917Z_todo-006-diagnostic-cadence-matrix/
