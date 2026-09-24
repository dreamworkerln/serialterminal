# TODO_006 one-sided diagnostic physical validation

Observed: 2026-09-24T08:50:42Z. Result: INCONCLUSIVE.

## Identity

Single long-lived SerialTerminal agent process, BLE, `s1` = node A
`LoRa-Chatter-1B44`, `s2` = node B `LoRa-Chatter-72E0`.

Both nodes reported firmware `0fa01bd7a220d25101716bc84089a21e714739b9`,
`state=clean`, and image validation `OK`. Runtime:
`04756c38a41dae8ebac063fed584a066187071b6`.

PHY was 470 MHz / SF7 / BW500 kHz / 2 dBm.

## Measurements

### Phase 1

B heartbeat was enabled while A remained off. B produced 10 local 12B PINGs
and 10 successful correlated PONGs; A answered each observed baseline exchange.
The baseline local B cadence was approximately 5 seconds.

### Phase 2

A diagnostic activity produced 37 observed local PINGs with `frame=225B`
(seq 136--172). B received 37 diagnostic-sized PINGs and transmitted 37
correlated `frame=225B` PONGs. A received 36 matching PONGs; the diagnostic
summary reported `TX=92 RX=90 CRC=1 HDR=0 NRP=1` over its 30-second window.

Representative exchange:

```text
A TX HEARTBEAT PING seq=141 frame=225B
B RX HEARTBEAT PING session=E130 seq=141 frame=225B
B TX HEARTBEAT PONG seq=141 frame=225B request=E130/141
A RX HEARTBEAT PONG request=E130/141 frame=225B
```

B `/config` during activity was `heartbeat=ON ... diag=OFF`. No B local
12B PING was observed during the 225B diagnostic-PING window, consistent with
suppression/rescheduling of the competing low-priority local candidate.

Host-observed event deltas for sequential A 225B PING telemetry were
min/avg/max `944.8 / 1005.0 / 1080.2 ms` across 36 intervals. These are
SerialTerminal receipt timestamps, not RF start timestamps; node output did
not expose exact RF start timestamps. Therefore the strict 1000 ms
start-to-start floor cannot be conclusively established from this evidence.

### Phase 3

A `/diag off` produced `DIAG OFF`; A final pre-diagnostic state was restored
as `heartbeat=OFF, diag=OFF`. B remained unchanged and then resumed local
12B heartbeat PING/PONG independently. First resumed B PING was seq 173,
approximately 4.1 s after A's diagnostic stop command output (about 4.6 s
after the last diagnostic PONG receipt). The resumed exchanges were
successful.

Final state checks before cleanup showed A `heartbeat=OFF, diag=OFF` and B
`heartbeat=ON, diag=OFF`. Cleanup then set both nodes to heartbeat OFF,
diagnostic OFF, echo-loop stopped, cancelled pending delivery, power 2 dBm;
both final configs confirmed the state and sessions closed.

## Gate summary

- Matching 225B PONG: PASS.
- B remained local `diag=OFF`: PASS.
- B heartbeat remained logically ON during one-sided diagnostic: PASS.
- Evidence of B heartbeat suppression during peer activity: PASS (no B local
  PING in the 225B window; normal PINGs resumed afterward).
- Finite B resume after A stopped: PASS.
- Persistent collision/recovery lock: not observed; one diagnostic NRP and one
  CRC were reported, with no fatal radio error and no sustained failure.
- Diagnostic 1000 ms start-to-start floor: INCONCLUSIVE because exact RF
  start timestamps were not exposed; host receipt proxy included sub-1000 ms
  deltas.

The overall result is INCONCLUSIVE solely on the cadence evidence boundary.
No firmware source or firmware documentation was consulted.

The forensic log and companion console log are exact finalized artifacts from
the single agent process. No explicit stdout/history replay or second agent
launch was performed; an automatic collapsed completion transcript was not
observed.
