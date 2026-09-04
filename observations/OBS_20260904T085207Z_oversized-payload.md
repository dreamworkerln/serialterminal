# Node observation

Observed: 2026-09-04T08:52:07Z
Task: Передача 400-символьного payload между двумя LoRa-Chatter нодами
Result: FAIL
SerialTerminal: dreamworkerln/serialterminal@19795a1ffc9bd9b8ac7d69749a7d007bfd38b34c
Firmware: dreamworkerln/lora-sack-protocol@unknown

## Setup
- Discovery обнаружил BLE-ноды `LoRa-Chatter-1B44` и `LoRa-Chatter-72E0`.
- Открыты сессии `s1` и `s2`; обе находились в состоянии `connected`, streams: `chat`, `telemetry`.
- Передача выполнялась с `s1` (`LoRa-Chatter-1B44`) на `s2` (`LoRa-Chatter-72E0`).

## Actions
- Через `send_line` отправлено ровно 400 символов `A` сессии `s1`.
- Ожидались TX/RX-события на обеих сессиях.

## Evidence
- Agent response: `{"state":"queued","tx_id":1}`.
- На `s1` зафиксировано `tx_state=written` для `tx_id=1`.
- На `s1` получено telemetry: `INPUT TOO LONG source=2 maximum=200 bytes`.
- На `s1` получено chat: `[SYS] INPUT TOO LONG: max 200 bytes`.
- На `s2` RX-событие с переданным payload не обнаружено.

## Anomalies / conflicts
- Expected: 400-символьный payload передан с одной ноды на другую.
- Observed: firmware отклонила ввод локально из-за лимита 200 байт; радио-передача не состоялась.
- Impact: peer delivery не подтверждена.

## Final state
- Обе BLE-сессии оставлены открытыми и оставались `connected`.
- Изменение echo/output mode не выполнялось.

## Evidence pointer
- Ключевые agent JSONL responses и RX/TX excerpts сохранены в этой записи.
