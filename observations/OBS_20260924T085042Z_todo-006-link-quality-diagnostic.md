# OBS TODO_006 one-sided diagnostic

Result: INCONCLUSIVE (cadence evidence boundary).

Physical reusable finding: one-sided diagnostic at 225B was observed to be
size-matched end-to-end. Node B remained `heartbeat=ON, diag=OFF`, did not
emit competing local heartbeat PINGs during the A diagnostic window, and
resumed its own normal heartbeat PING/PONG after A stopped. A restored its
pre-diagnostic `heartbeat=OFF` state.

37 A 225B diagnostic PINGs were observed; 36 correlated PONGs were received
by A, with B transmitting 37 matching 225B PONGs. The diagnostic summary
reported one NRP and one CRC, no HDR errors, and no fatal radio errors.

The strict 1000 ms start-to-start cadence gate remains inconclusive because
the available node telemetry exposes no exact RF start timestamps. Runtime
receipt deltas were min/avg/max 944.8/1005.0/1080.2 ms.

Firmware: `0fa01bd7a220d25101716bc84089a21e714739b9`, clean, image validation
OK. Runtime: `04756c38a41dae8ebac063fed584a066187071b6`.

Run bundle: runs/RUN_20260924T085042Z_todo-006-link-quality-diagnostic/
