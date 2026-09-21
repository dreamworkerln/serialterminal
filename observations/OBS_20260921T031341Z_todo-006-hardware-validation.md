# Node observation

Observed: 2026-09-21T03:13:41Z
Task: TODO_006 link-quality / heartbeat diagnostic hardware validation
Result: BLOCKED
SerialTerminal: dreamworkerln/serialterminal@1c8b42830780d65b0f5daefd4d23275ac7c56ac7
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup

- Discovery found two physical USB Chatter transports and two BLE transports.
- USB sessions used `profile=chatter`; identities were `LoRa-Chatter-72E0` and `LoRa-Chatter-1B44`.
- Host audio preflight showed no connected Bluetooth audio endpoint or active Bluetooth audio stream.

## Finding

The mandatory exact checkpoint gate blocked the measured phase. Both nodes reported:

```text
[SYS] FIRMWARE Chatter git=6c08084891f4940dcbe804c0c4ef26feea9b4eb5 state=clean env=esp32-s3-n16r8
[SYS] FIRMWARE IMAGE validation_sha256=740e4cf6fcbcd2679b26265aff0f058087844d927d39459a5ee1bd45e86f891d status=OK slot=0
[SYS] BUILD META toolchain_sha256=d837e37bb188244de843b7c03ea81f34e501d879a501cb5342129e2338eeb4af pio=6.2.0
```

The required source SHA was `ad92394135f7d97de6045ed66ebdd46db23236d7`; the
reported source, image, and toolchain identities did not match the expected release.
No RF behavior validation was attempted. Sessions were closed cleanly.

Run bundle: runs/RUN_20260921T031341Z_todo-006-hardware-validation/
