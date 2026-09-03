---
name: lora-chatter-nodes
description: Project-specific наблюдаемое поведение LoRa-Chatter нод через SerialTerminal agent API. Не является generic SerialTerminal skill.
---

# LoRa-Chatter nodes

Этот файл сохраняет project-specific знания, полученные при работе с двумя BLE-подключёнными LoRa-Chatter нодами через `python3 serialterminal.py agent`.

Он **не является источником истины для SerialTerminal API** и не должен переопределять `.agents/skills/serialterminal-agent/SKILL.md` или [AGENT_API.md](../../../AGENT_API.md). При переносе Chatter-specific automation в `lora-sack-protocol` этот материал следует перенести туда как hardware/protocol skill.

## Подключение

Работай через SerialTerminal agent, а не через прямой BLE/LoRa access:

```bash
python3 serialterminal.py agent
```

Если host Bluetooth/D-Bus или sandbox возвращает `Operation not permitted`/другой permission error, это не означает отсутствие устройства. Используй разрешённый окружением запуск с необходимыми правами.

Обнаружение:

```json
{"id":1,"op":"discover","scope":"auto"}
```

Наблюдавшиеся устройства:

```text
BLE LoRa-Chatter-1B44  44:1B:F6:8D:B7:A9
BLE LoRa-Chatter-72E0  E0:72:A1:D5:4C:15
```

В discovery также появляется USB serial endpoint:

```text
/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B8F072180-if00
VID:PID=1A86:55D3
```

Это не третья радионода. Открытие USB endpoint дало сессию с одним потоком `main`, а `/id` и `/help` вернули `LoRa-Chatter-1B44` и тот же human-console interface, что у BLE-ноды `44:1B:F6:8D:B7:A9`. Поэтому USB и BLE-адрес `1B44` следует считать двумя transport paths к одной физической ноде, если они доступны одновременно.

Открытие каждой физической ноды создаёт отдельную живую session. В проверке использовались `s1` для `1B44` и `s2` для `72E0`:

```json
{"id":2,"op":"open","device_key":"ble-address:44:1b:f6:8d:b7:a9"}
{"id":3,"op":"open","device_key":"ble-address:e0:72:a1:d5:4c:15"}
```

Обе sessions подключались как `state=connected` и имели потоки `chat` и `telemetry`. При `open` с `auto_id=true` SerialTerminal отправляет ноде `/id` как connect preamble.

## BLE-потоки и получение данных

Устройство имеет два независимых BLE-потока:

- `chat` — человекочитаемый вывод, команды и сообщения;
- `telemetry` — машинная телеметрия и диагностические события радиоканала.

При открытии session SerialTerminal сам подписывается на telemetry characteristic. Отдельную команду подписки через agent API отправлять не нужно. Notifications принимаются в фоне и складываются в session event buffer.

Для реакции на новые данные держи `wait_events` pending. После его ответа обработай события и сразу выдай следующий `wait_events` с возвращёнными `cursors`, если наблюдение должно продолжаться.

Используй независимый cursor для каждой session:

```json
{"id":10,"op":"wait_events","cursors":{"s1":123,"s2":456},"timeout_ms":5000}
```

Для ожидания только сообщений:

```json
{"id":11,"op":"wait_events","cursors":{"s2":123},"timeout_ms":5000,"kinds":["rx"],"streams":["chat"]}
```

`timeout_ms` — максимальная длительность одного long-poll request, а не protocol constant и не серверный push. `wait_events` остаётся pending, пока тот же agent process может принимать обычные запросы, например `send_line`. Пустой результат с `timed_out=true` означает только, что за это окно новых подходящих событий не было.

Не считай `send_line` доставкой: `state=queued` означает только постановку в reconnect-safe TX queue. Последующее TX-событие `tx_state=written` означает успешный transport `write()`. Доставку по радио подтверждай RX-событием на peer-ноде или соответствующей радиотелеметрией.

Локальный вывод отправителя с префиксом `>` не подтверждает приём peer-нодой; принятый peer-текст обычно имеет вид `< [RSSI/SNR Q] ...`.

## Одновременные передачи и half-duplex

LoRa-канал между нодами работает в half-duplex, поэтому близкие по времени передачи могут столкнуться.

Для обычной проверки гарантированной двунаправленной доставки используй последовательный сценарий: отправь с первой ноды, дождись подтверждённого RX на второй, затем отправь ответ в обратную сторону.

Для явного concurrency/collision test одновременная передача с разных sessions допустима и может использоваться намеренно. SerialTerminal способен независимо поставить TX в очереди разных sessions; фактический radio outcome определяется поведением LoRa/firmware и должен оцениваться по RX/telemetry, а не только по локальным `>` строкам.

## Передача сообщений между нодами

Обе ноды наблюдались как связанные точка-точка по LoRa. Обычная передача выполняется строкой через `send_line`:

```json
{"id":20,"op":"send_line","session":"s1","text":"hello from node 1"}
```

Получатель в `chat` обычно показывает строку вида:

```text
< [-22/+12 Q100] hello from node 1
```

BLE notification boundary не является границей текстовой строки. При необходимости склеивай соседние RX-фрагменты одного потока по `seq` до завершения строки.

В приведённом примере вывод соответствует примерно `RSSI=-22`, `SNR=+12`, `Q=100%`.

## Режимы вывода

Команды переключают, какие категории устройство выводит в BLE-console:

```text
/chat  -> OUTPUT CHAT
/tele  -> OUTPUT TELEMETRY
/both  -> OUTPUT BOTH
```

Практически наблюдалось:

- после `/chat` подтверждение `OUTPUT CHAT` пришло в `chat`;
- после `/tele` подтверждение `OUTPUT MODE ... state=TELEMETRY` пришло в `telemetry`;
- после `/both` подтверждения `OUTPUT BOTH` пришли и в `chat`, и в `telemetry`.

Эти команды меняют маршрутизацию вывода на BLE-потоках, а не сам факт существования LoRa-связи между нодами.

## Echo-режим

`/echo` переключает echo-mode:

```json
{"id":21,"op":"send_line","session":"s1","text":"/echo"}
```

Подтверждение включения:

```text
[SYS] ECHO MODE ON
```

В echo-mode обычный текст превращается в радиотестовый `ECHO_REQUEST`, а удалённая нода отвечает `ECHO_REPLY`.

На отправляющей ноде наблюдался вывод:

```text
> [ECHO TX] echo test from node 1
< [ECHO -24/+10 Q100] echo test from node 1
```

На удалённой ноде в telemetry при этом фиксировались:

```text
RX ECHO_REQUEST
RSSI=-22.0 dBm SNR=+10.8 dB Q=100%
TX ECHO_REPLY
OK time=1976 ms guard=500ms
```

Таким образом, echo — протокол проверки радиодоставки и round trip, а не только локальное отображение введённого текста. Для обычной передачи сообщений выключи его повторным `/echo`; после этого удалённая нода снова получает сообщение как `RX USER` и показывает его с RSSI/SNR.

## Перезагрузка ноды

`/reboot` действительно перезагружает ESP32 controller. Вызывай его только при явном намерении перезагрузить устройство.

Через USB serial на ноде `1B44` наблюдалась последовательность:

```text
[SYS] REBOOTING
rst:0xc (RTC_SW_CPU_RST)
[SYS] CHATTER NODE LoRa-Chatter-1B44
[SYS] CHATTER READY
```

Через BLE та же команда сначала дала `USER REBOOT` и `[SYS] REBOOTING`, после чего BLE-session прошла состояния:

```text
disconnected -> reconnecting -> connected
```

После восстановления `ManagedSession` автоматически отправила connect preamble (`/id`), а нода снова объявила себя `LoRa-Chatter-1B44`. Поэтому кратковременное BLE-отключение во время перезагрузки ожидаемо; отдельную session заново открывать не нужно, если `ManagedSession` уже держит этот `device_key`.

## `/help` и доступные команды

Проверенная команда `/help` вернула:

```text
/help     show this help
/id       show node identity
/chat     human console CHAT
/tele     human console TELEMETRY
/both     human console BOTH
/echo     toggle echo mode
/reboot   reboot ESP32 controller
```

Также устройство сообщает raw controls:

```text
0x31 / 14 31 -> CHAT
0x32 / 14 32 -> TELEMETRY
0x33 / 14 33 -> BOTH
0x65 / 14 65 -> ECHO toggle
```

Наблюдались Android BLE macros с LF: `/help`, `/id`, `/chat`, `/tele`, `/both`, `/echo`, `/reboot`.

`/reboot` не используй без отдельного явного намерения: это реальная перезагрузка ESP32 controller.

## Диагностические признаки

Telemetry содержит, среди прочего, счётчики `TX ok`, `RX ok`, `user`, `echo_req`, `echo_rep`, `crc`, `hdr`, `bad`, `readerr`, `Q`, `drops`, а также диагностические блоки `SESSION`, `DIO0_TX`, `RX_POLL`, `PEER_REPORT` и `RX/TX ECHO_*`.

Успешную проверку радиоканала подтверждай совокупностью признаков:

1. `send_line` принял строку (`queued`);
2. на отправителе появилось TX-событие `written`;
3. на получателе появился `RX USER`/сообщение или `RX ECHO_REQUEST`;
4. для echo появился `TX ECHO_REPLY` и итоговый `OK`;
5. RSSI/SNR/Q позволяют оценить качество радиоканала.

Не делай вывод о доставке только по `queued` или только по `written`: они подтверждают локальную очередь/transport write, но не приём peer-нодой.
