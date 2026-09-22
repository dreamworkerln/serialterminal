# Reliable USER ACK-loss retry hardware run

## Result

Overall verdict: **BLOCKED**. The exact physical-firmware provenance gate failed before any measured LoRa RF traffic. Scenario 1 and Scenario 2 were not started; this run makes no reliability-behavior finding.

## Requested target and exact revisions

- SerialTerminal: `dreamworkerln/serialterminal@fedfa29d5c8b07613e49e9425bbc2bbc5b74c165`.
- Required firmware source checkpoint: `5996d55ee9289aee2b02583bd0eabb20a1e322ff`, clean.
- Node-reported source checkpoint for both participating nodes: `6c08084891f4940dcbe804c0c4ef26feea9b4eb5`, clean. This does not meet the required target.

## Hardware and transport

- A (intended USER sender): `LoRa-Chatter-1B44`, BLE session `s1`.
- B (intended USER receiver / ACK sender): `LoRa-Chatter-72E0`, BLE session `s2`.
- USB Serial was not available for both physical nodes; the two discovered Chatter paths were BLE.
- BLE audio preflight: `bluetoothctl devices Connected` returned no connected device. `wpctl status` listed only local ALSA audio devices, no Bluetooth sink/source/endpoints and no active audio stream. No host Bluetooth/audio service was changed.

## Physical firmware provenance

A `/version`:

```text
[SYS] FIRMWARE Chatter git=6c08084891f4940dcbe804c0c4ef26feea9b4eb5 state=clean env=esp32-s3-n16r8
[SYS] FIRMWARE IMAGE validation_sha256=740e4cf6fcbcd2679b26265aff0f058087844d927d39459a5ee1bd45e86f891d status=OK slot=0
[SYS] BUILD META toolchain_sha256=d837e37bb188244de843b7c03ea81f34e501d879a501cb5342129e2338eeb4af pio=6.2.0
```

B `/version`:

```text
[SYS] FIRMWARE Chatter git=6c08084891f4940dcbe804c0c4ef26feea9b4eb5 state=clean env=esp32-s3-n16r8
[SYS] FIRMWARE IMAGE validation_sha256=740e4cf6fcbcd2679b26265aff0f058087844d927d39459a5ee1bd45e86f891d status=OK slot=0
[SYS] BUILD META toolchain_sha256=d837e37bb188244de843b7c03ea81f34e501d879a501cb5342129e2338eeb4af pio=6.2.0
```

The image and toolchain lines are preserved as runtime evidence, but neither replaces the required source Git SHA. Because both canonical source lines differ from the required SHA, the measured USER/ACK phase was prohibited.

## RF and protocol scenarios

- Initial RF config for a measured baseline: not entered; no USER/ACK/ECHO/heartbeat/diagnostic RF traffic was sent.
- Baseline: not measured.
- Controlled asymmetric RF condition: not created.
- Scenario 1, lost ACK → retry → eventual success: **BLOCKED**, not started.
- Scenario 2, all ACKs lost → five-attempt exhaustion: **BLOCKED**, not started.
- Logical USER identities, attempt counts, ACK timeouts, same-seq retry, duplicate suppression, repeated ACK, eventual matching ACK, five-attempt exhaustion, and CHAT presentation counts: not measured.

## Safe final state and evidence integrity

Both nodes accepted the local cleanup commands and reported:

```text
[SYS] HEARTBEAT OFF
[SYS] DIAG already OFF
[SYS] ECHO LOOP already stopped
[SYS] POWER 2 dBm SAVED
[SYS] CFG RADIO power=2 dBm freq=470 MHz sf=12 bw=125 kHz
[SYS] CFG LINK heartbeat=OFF retry=ON attempts=5 diag=OFF
```

Sessions were closed through the same long-lived agent process, then that process was stopped. Final power is A=2 dBm and B=2 dBm. The exact forensic and companion logs are included unchanged. No `forensic_gap`, transport reconnect, or BLE flapping occurred in the relevant precondition/cleanup interval.

## Limitation

The blocking condition is physical firmware provenance only. No firmware failure is asserted, and no source or firmware change was made.
