# Diagnostic, reboot and radio-fault scenarios

Read this only when the task explicitly exercises ECHO, reboot, degraded/fatal radio handling or related fault behavior.

## ECHO

Echo mode is local and should be OFF after normal boot.

The /echo command toggles mode. Do not use a toggle as a read-only state probe when the current state is unknown.

When echo mode is ON, a user line becomes ECHO_REQUEST rather than USER.

A valid peer ECHO_REQUEST creates one ECHO_REPLY. Replies do not recursively generate replies.

ECHO PASS requires the complete logical chain:

```text
sender TX ECHO_REQUEST
peer RX ECHO_REQUEST
peer TX ECHO_REPLY
sender RX matching ECHO_REPLY
```

Stale/unrelated reply is not success.

ECHO is best-effort and has no reliable USER retry semantics.

Return echo/echo-loop OFF after the scenario unless the task explicitly requires otherwise.

## Reboot

/reboot restarts the ESP32 controller. Use it only in an explicitly requested reboot/fault/recovery scenario.

Transport reconnect does not by itself prove a new physical node. Re-establish /id when identity matters after reboot.

Do not assume exactly-once reliable USER identity persists across reboot unless current firmware evidence explicitly establishes it.

## Radio unavailable/fatal

Boot radio initialization or boot physical-TX POST failure may leave the controller transport alive while RF is unavailable.

Do not use working BLE/USB control transport as proof of RF health.

A successful SX1278 register/version read proves digital/SPI liveness only, not RF output path.

For current firmware, physical TX truth is based on radio TxDone evidence; DIO0 is diagnostic only.

Runtime radio-loss/fatal behavior can differ from boot degraded behavior. Use the current task-specific firmware source/docs as authority.

Do not perform destructive fault injection unless the operator explicitly requests it.
