# Reliable USER ACK-loss retry hardware run

## Result

Overall verdict: **BLOCKED**.

The requested ACK-loss scenarios were not started.  The baseline at the mandatory
2 dBm setting was fully bidirectional, while the available executor interface
provided no safe physical means to introduce and prove the required asymmetric
RF condition (A -> B USER received; B -> A ACK lost).  Increasing A TX power
at the observed very strong close-range link would not establish that asymmetry
and was not attempted.

## Revisions and transport

- SerialTerminal: `dreamworkerln/serialterminal@fedfa29d5c8b07613e49e9425bbc2bbc5b74c165`.
- Transport: BLE; one `profile:"chatter"` session per node in the executor's
  current agent-process segment.
- A / USER sender: `LoRa-Chatter-1B44`, session `s1`.
- B / USER receiver and ACK sender: `LoRa-Chatter-72E0`, session `s2`.
- Firmware A: `[SYS] FIRMWARE Chatter git=608f1cd26d76a1b02d3401cbd17a9b4c9ab44716 state=clean env=esp32-s3-n16r8`.
- Firmware B: `[SYS] FIRMWARE Chatter git=608f1cd26d76a1b02d3401cbd17a9b4c9ab44716 state=clean env=esp32-s3-n16r8`.
- Both `/version` responses also reported `[SYS] FIRMWARE IMAGE validation_sha256=0c3d69eed3557864bfb0004dc2b03364debc5146bfb49c82d50e388fdcc0c159 status=OK slot=0` and `[SYS] BUILD META toolchain_sha256=35a726b162162417e419c64b54b8b7719ff8786a3db12e8f3906120177f2d833 pio=6.2.0`.

## Host and RF preflight

- Bluetooth/audio read-only preflight: known Bluetooth audio devices were
  `Connected: no`; PipeWire showed no Bluetooth sink/source or active audio
  stream.
- On both nodes: `/heartbeat off`, `/diag off`, and `/echo-loop stop` completed.
- Both `/config` responses confirmed `power=2 dBm freq=470 MHz sf=12 bw=125 kHz`
  and `heartbeat=OFF retry=ON attempts=5 diag=OFF`.

## Baseline

Bidirectional baseline passed at 2 dBm / 2 dBm.

- A -> B payload `ACKLOSS-BASE-A2B-20260922T000000Z`: A sent USER
  `80AB/0`, B reported `RX USER session=80AB seq=0`, displayed the payload once
  in CHAT, and transmitted `TX ACK ... ack_to=80AB/0`.  A received matching ACK
  and completed `DELIVERY ACK user=80AB/0 attempts=1/5`.
- B -> A payload `ACKLOSS-BASE-B2A-20260922T000000Z`: B sent USER
  `3723/1`, A reported `RX USER session=3723 seq=1`, displayed the payload once
  in CHAT, and transmitted `TX ACK ... ack_to=3723/1`.  B received matching ACK
  and completed `DELIVERY ACK user=3723/1 attempts=1/5`.
- The observed receive levels for baseline USER traffic were about -28/-27 dBm.
  This shows a strong two-way link, not an evidence-backed loss condition.

## Requested scenarios

| Scenario | Verdict | Evidence boundary |
| --- | --- | --- |
| 1: lost ACK -> retry -> eventual success | BLOCKED | No controlled one-way RF-loss condition was available, so no `ACKLOSS-RECOVER-*` USER was sent. |
| 2: all ACKs lost -> bounded exhaustion | BLOCKED | No controlled one-way RF-loss condition was available, so no `ACKLOSS-EXHAUST-*` USER was sent. |

Therefore no same-seq retry, duplicate suppression, repeated ACK, eventual
delivery after retry, or five-attempt exhaustion was measured.  These are not
firmware failures.

## Forensics and anomalies

- `forensic_gap`: no explicit `forensic_gap` record was found.
- No BLE reconnect/flapping occurred in the current baseline/cleanup interval.
- The supplied fixed `/tmp/reliable-user-ack-loss-retry.log` path already
  contained two earlier agent RUN segments before this executor segment.  The
  copied forensic artifact is the exact unmodified logfile required by the task;
  it contains all three RUN segments rather than a reconstructed subset.  The
  current executor segment is the final RUN, from `2026-09-22T09:19:58.988+03:00`
  through `2026-09-22T09:27:35.069+03:00`.  This contamination is recorded as a
  log-boundary anomaly; it does not supply evidence for either requested scenario.

## Final state

- Both sessions were closed through the agent API before process termination.
- A final `/config` confirmed A power = 2 dBm.
- A final `/config` confirmed B power = 2 dBm.
- Final background state on both nodes: heartbeat OFF, diag OFF, echo-loop stopped.

## Persistent evidence

- `serialterminal.log` is the exact forensic logfile as supplied to the single
  long-lived current agent segment; it is copied without normalization.
- `serialterminal.console.log` is its exact companion log.
- A matching OBS is recorded because this is a BLOCKED run with reusable setup
  and evidence-boundary information.
