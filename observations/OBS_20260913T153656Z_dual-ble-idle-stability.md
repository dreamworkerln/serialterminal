# Node observation

Observed: 2026-09-13T15:36:56Z
Task: dual-ble-idle-stability
Result: FAIL
SerialTerminal: dreamworkerln/serialterminal@c9c6d4099c3532494bac8bfecb9fead37e27fe1e

При двух одновременно открытых BLE sessions в одном SerialTerminal agent process spontaneous disconnect/reconnect воспроизвёлся без USER/ECHO или другого ручного трафика: `s1` прошёл `disconnected → reconnecting → connected`; `s2` оставалась connected.

Run bundle: runs/RUN_20260913T153656Z_dual-ble-idle-stability/
