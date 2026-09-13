# Node observation

Observed: 2026-09-13T15:51:02Z
Task: dual-ble-hci-disconnect
Result: PASS
SerialTerminal: dreamworkerln/serialterminal@c9c6d4099c3532494bac8bfecb9fead37e27fe1e

При двух одновременно открытых BLE sessions в одном SerialTerminal agent process обе sessions оставались connected 341.026 секунд idle без spontaneous ST disconnect/reconnect. HCI trace и Bluetooth journal недоступны из sandbox, поэтому причина ранее наблюдавшихся disconnect не установлена.

Run bundle: runs/RUN_20260913T155102Z_dual-ble-hci-disconnect/
