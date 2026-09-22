# BLE and host-audio handling

Read this when detailed BLE preflight, BLE instability or coexistence behavior matters.

## Ordinary measured BLE run

Before the run, inspect the host read-only for connected Bluetooth audio endpoints/paths using available tools such as:

```text
bluetoothctl info
wpctl status
pactl list cards
pactl list sink-inputs
```

Look for factual evidence of a connected Bluetooth audio endpoint, A2DP/HSP/HFP profile, Bluetooth sink/source or active audio stream when the host exposes it.

Do not infer a codec/profile/stream that the host output does not show.

If a Bluetooth audio endpoint/path is connected for an ordinary BLE hardware validation:

```text
do not start measured BLE phase
ask operator to disconnect the audio device
do not disconnect it yourself
do not change/restart BlueZ, PipeWire, PulseAudio or WirePlumber
```

If read-only host inspection requires sandbox approval, request only that inspection permission.

## BLE discovery

Discovery is capability-based. A LoRa-looking advertised name is not enough.

A target is usable when standard NUS is advertised or the address has cached confirmed NUS capability.

If an expected BLE node is missing, use the SerialTerminal Bluetooth capability scanner/prober and then repeat discover in the same long-lived agent process.

Permission errors are environment boundaries, not proof that a device does not exist.

## Flapping

Repeated BLE disconnect/reconnect during a measured run is not automatically firmware FAIL.

Stop cleanly when evidence integrity is compromised and classify BLOCKED/INCONCLUSIVE according to the available evidence, especially when host Bluetooth/audio contention is plausible.

## Explicit coexistence scenario

If the operator specifically asks to test BLE while Bluetooth audio remains connected:

- do not block solely because the audio path is active;
- record the factual endpoint/profile/codec/stream evidence available before measurement;
- execute only the requested coexistence scenario;
- do not mutate the host audio/Bluetooth stack;
- do not promote reconnect/flapping to firmware FAIL without independent firmware evidence.

This exception does not change the default ordinary-run preflight.
