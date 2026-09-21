# TODO_006 hardware validation report

Observed: 2026-09-21T03:13:41Z
Result: BLOCKED

## Scope and gate

This run was a focused physical two-node validation of TODO_006. The required
exact-firmware provenance gate failed before RF behavior measurements. No source,
firmware, tests, documentation, skills, TODOs, branches, or REVIEW_STATE were
modified.

Expected firmware checkpoint:

- source: `ad92394135f7d97de6045ed66ebdd46db23236d7`, state `clean`
- image validation: `c41fb9c932842e696f3c9b22528e23371dd1abc0b5edf28c168de5b2a4c62599`
- artifact: `10608033837`, `chatter-esp32-s3-n16r8-ad92394135f7d97de6045ed66ebdd46db23236d7`
- protocol wire version: v3

## Host and discovery

Read-only PipeWire/audio preflight showed only built-in audio, no Bluetooth
audio device, Bluetooth sink/source, or running audio stream. Discovery found two
USB serial paths and two BLE paths. This run opened the two USB paths with
`profile=chatter`; BLE was not used after the provenance gate was evaluated.

Canonical identities obtained from the physical nodes:

- USB serial `...5B8F021956...` -> `LoRa-Chatter-72E0`
- USB serial `...5B8F072180...` -> `LoRa-Chatter-1B44`

## Exact provenance evidence

Both nodes reported the same non-target firmware:

```text
[SYS] FIRMWARE Chatter git=6c08084891f4940dcbe804c0c4ef26feea9b4eb5 state=clean env=esp32-s3-n16r8
[SYS] FIRMWARE IMAGE validation_sha256=740e4cf6fcbcd2679b26265aff0f058087844d927d39459a5ee1bd45e86f891d status=OK slot=0
[SYS] BUILD META toolchain_sha256=d837e37bb188244de843b7c03ea81f34e501d879a501cb5342129e2338eeb4af pio=6.2.0
```

The source SHA differs from the required `ad923941...`; the running image and
toolchain identities also differ from the supplied release values. Therefore both
exact-provenance gates are `BLOCKED`, despite both nodes being clean and mutually
consistent. This is a mandatory precondition failure, not an RF behavior FAIL.

## Hardware-validation matrix

| Checkpoint | Result | Evidence / boundary |
|---|---|---|
| Exact provenance A | BLOCKED | `/version`: `git=6c080848... state=clean`; required `ad923941...` |
| Exact provenance B | BLOCKED | Same mismatch as A |
| Baseline CFG | NOT RUN | Stopped at mandatory provenance gate |
| USER normal delivery | NOT RUN | Stopped at mandatory provenance gate |
| USER transaction-Q | NOT OBSERVED | No measured phase |
| USER retry physical samples | NOT OBSERVED | No measured phase |
| Heartbeat PING/PONG | NOT RUN | Stopped at mandatory provenance gate |
| Heartbeat directional metrics | NOT RUN | Stopped at mandatory provenance gate |
| Heartbeat no response loop | NOT RUN | Stopped at mandatory provenance gate |
| Heartbeat no retransmission | NOT OBSERVED | No measured phase |
| USER/heartbeat scheduler coexistence | NOT RUN | Stopped at mandatory provenance gate |
| Diag OFF->ON->OFF restore | NOT RUN | Stopped at mandatory provenance gate |
| Diag ON->ON->ON restore | NOT RUN | Stopped at mandatory provenance gate |
| Diag 16B | NOT RUN | Stopped at mandatory provenance gate |
| Diag 32B | NOT RUN | Stopped at mandatory provenance gate |
| Diag 64B | NOT RUN | Stopped at mandatory provenance gate |
| Diag 200B | NOT RUN | Stopped at mandatory provenance gate |
| Diag 255B | NOT RUN | Stopped at mandatory provenance gate |
| Diag non-persistence | NOT RUN | Stopped at mandatory provenance gate |
| LNK monospace presentation | NOT RUN | Stopped at mandatory provenance gate |
| 30s summary | NOT RUN | Stopped at mandatory provenance gate |
| CRC classification | NOT OBSERVED | No measured phase |
| HDR classification | NOT OBSERVED | No measured phase |
| NRP classification | NOT OBSERVED | No measured phase |
| Edge-of-link size behavior | NOT OBSERVED | No measured phase |
| Legacy ECHO sanity | NOT RUN | Stopped at mandatory provenance gate |
| Final USER regression smoke | NOT RUN | Stopped at mandatory provenance gate |

## Actions and final state

The agent performed discovery, opened both USB sessions, obtained `/id` and
`/version`, then closed both sessions. No configuration, heartbeat, diagnostic,
radio, reboot, or RF behavior command was issued. The SerialTerminal process was
terminated cleanly and the exact forensic and companion logs are included in this
RUN.

## Evidence files

- `serialterminal.log` is the exact forensic log from the agent process.
- `serialterminal.console.log` is the exact companion console log from the same process.
- No auxiliary capture was required because the run stopped at provenance precondition.
