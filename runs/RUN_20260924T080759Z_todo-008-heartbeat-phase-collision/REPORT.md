# TODO_008 heartbeat phase collision physical revalidation

Observed: 2026-09-24T08:07:59Z run identity; wall-clock log through 2026-09-24T08:17:33Z
Result: PASS

## Identity and gate

Two BLE `profile: chatter` sessions were used in one long-lived SerialTerminal
agent process. The nodes identified as `LoRa-Chatter-1B44` (s1) and
`LoRa-Chatter-72E0` (s2). Both `/version` results reported:

```text
FIRMWARE Chatter git=0fa01bd7a220d25101716bc84089a21e714739b9 state=clean
FIRMWARE IMAGE validation_sha256=9af98dffa689c6b29f657aca4269c463d0af017011e755b7d40053fc374211ef status=OK slot=0
```

SerialTerminal runtime: `04756c38a41dae8ebac063fed584a066187071b6`.
Observation workspace: `4a5fc3aa27ba805aadf431b302820ff07429da43`.

## Scenario A — reproduced slow PHY

PHY: 470 MHz, SF12, BW125 kHz, power 2 dBm. Measured duration: at least 180 s
after the symmetric heartbeat start. Each node emitted 18 measured PING starts
(seq 0–17). Matching outcome counts were approximately 9 PONG successes and 9
NRP timeouts per node; CRC=0 and HDR=0 were observed. Collision-compatible
paired starts were observed; retained raw start examples were about 20–24 ms
apart. The longest consecutive paired-NRP chain was 2 cycles, versus 11 in the
supplied pre-fix evidence.

Observed recovery telemetry included:

```text
recovery=1 jitter<=1156ms
recovery=2 jitter<=2312ms
```

After paired NRP, subsequent starts diverged enough for successful peer
exchange without manual dephasing. Both RX HEARTBEAT PING/PONG directions were
observed, and later successful exchanges continued. No fatal radio error was
reported.

## Scenario B — faster PHY

PHY: 470 MHz, SF7, BW500 kHz, power 2 dBm. Measured duration: at least 90 s
after the symmetric heartbeat start. Each node emitted 16 measured PING starts
(seq 21–36). Both directions produced successful PING/PONG exchange; matching
NRP events were bounded and no CRC/HDR failures or fatal radio errors were
reported. The longest consecutive paired-NRP chain was 2 cycles.

Observed recovery telemetry included:

```text
recovery=1 jitter<=11ms
recovery=2 jitter<=22ms
```

There was no persistent paired-collision lock and no runaway/high-rate
heartbeat behavior.

## Acceptance summary

The SF12/BW125 pre-fix 11-cycle paired-NRP behavior was not reproduced. The
widened recovery telemetry was observed, recovery was followed by successful
peer exchange without manual dephasing, and the faster PHY remained
bidirectionally responsive. This is a physical PASS for TODO_008 recovery
behavior.

## Final state and evidence

Cleanup confirmed on both nodes: heartbeat OFF, diagnostic OFF, echo loop
stopped, no pending delivery, power 2 dBm, frequency 470 MHz; final configured
PHY remained SF7/BW500 from Scenario B. Both sessions closed normally. No
explicit stdout/history replay or second agent launch was performed. The
terminal UI did not emit a separately observed collapsed completion transcript.

The forensic log and companion console log are exact finalized artifacts from
the single agent process.
