# BLE transport handling

Read this only when BLE discovery, permissions, reconnect or flapping behavior matters.

## BLE discovery

Discovery is capability-based. A LoRa-looking advertised name is not enough.

A target is usable when standard NUS is advertised or the address has cached confirmed NUS capability.

If an expected BLE node is missing, use the SerialTerminal Bluetooth capability scanner/prober and then repeat discover in the same long-lived agent process.

Discovery cache is process-local, so discover and the subsequent open must occur in the same SerialTerminal agent process.

Permission errors are environment boundaries, not proof that a device does not exist. If discovery, scanner/prober, open, subscribe, write or other required BLE access fails because the sandbox/host denies access, request the minimum elevated permission needed for that BLE/D-Bus/device operation and retry it. Do not return `BLOCKED` merely from the first permission error. Use `BLOCKED` only when elevation is unavailable/denied or the approved retry still cannot access the required BLE operation.

If a later BLE operation hits a different permission boundary, request the corresponding narrow permission for that operation as well; do not assume one discovery approval covers every device/D-Bus action.

## Reconnect and flapping

Repeated BLE disconnect/reconnect during a measured run is not automatically firmware FAIL.

If reconnect/flapping prevents complete evidence, stop the affected scenario cleanly and classify it BLOCKED or INCONCLUSIVE according to the evidence actually obtained.

Do not mutate BlueZ or other host Bluetooth services as an automatic recovery action. Host-stack changes require an explicit operator task.

If the task specifically investigates host Bluetooth transport coexistence or interference, record only the environment facts relevant to that requested diagnostic. Do not introduce unrelated host checks into ordinary runs.
