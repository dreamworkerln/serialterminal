# OBS TODO_006 diagnostic size and cadence matrix

Result: PASS.

Physical two-node validation on firmware
`3b386dfa3eae68be057ab9aeec37a89367773839` confirmed diagnostic frame sizes
16/32/64/200/225/255B with size-matched PONGs. At 470 MHz/SF7/BW500, every
same-size local PING-start delta was at least 1,001,830 us; there were no
1,000,000 us floor violations. The 255B exchange completed end to end.

At 470 MHz/SF12/BW62.5, 16B diagnostic PING `start_us` deltas had min/avg/max
5,791,986/5,926,809.27/6,114,038 us, with zero below the supplied 5,276,000 us
duty-derived floor. Node `time=<ms>` was 2639 ms. Cadence acceptance used only
wrap-safe device-side `start_us` deltas.

One 64B NRP occurred and its recovery interval remained above the cadence floor.
Two size changes initially returned BUSY; both were retried only after resetting
diagnostic state and were then accepted. No fatal radio state was reported.

Run bundle: runs/RUN_20260924T105501Z_todo-006-diagnostic-cadence-matrix/
