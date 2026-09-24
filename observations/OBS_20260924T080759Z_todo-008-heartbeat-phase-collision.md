# Node observation: TODO_008 heartbeat phase collision

Observed: 2026-09-24T08:07:59Z  
Task: focused canonical two-node physical revalidation  
Result: PASS

Both BLE Chatter nodes reported firmware
`0fa01bd7a220d25101716bc84089a21e714739b9`, clean, with image validation OK.
Runtime was `04756c38a41dae8ebac063fed584a066187071b6`.

Scenario A at 470 MHz / SF12 / BW125 ran for at least 180 s. Symmetric starts
produced paired collisions and NRP, followed by observed recovery telemetry
`recovery=1 jitter<=1156ms` and `recovery=2 jitter<=2312ms`. Successful peer
PING/PONG exchange resumed without manual dephasing. The longest paired-NRP
chain was 2 cycles; the supplied pre-fix chain was 11 cycles. CRC and HDR
failures were not observed.

Scenario B at 470 MHz / SF7 / BW500 ran for at least 90 s. Both directions
successfully exchanged heartbeat traffic. Occasional paired NRP produced
bounded `recovery=1 jitter<=11ms` and `recovery=2 jitter<=22ms`; no persistent
paired lock, runaway rate, CRC/HDR failure, or fatal radio error was observed.

Final node state: heartbeat OFF, diagnostic OFF, echo loop stopped, no pending
delivery, power 2 dBm, frequency 470 MHz; sessions closed.

Run bundle: runs/RUN_20260924T080759Z_todo-008-heartbeat-phase-collision/
