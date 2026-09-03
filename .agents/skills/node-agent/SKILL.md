---
name: lora-chatter-nodes
description: Project-specific class-level поведение LoRa-Chatter нод через SerialTerminal agent API. Не является generic SerialTerminal skill.
---

# LoRa-Chatter nodes

Этот skill описывает, как работать с **классом LoRa-Chatter node** через `python3 serialterminal.py agent` и как проверять наблюдаемое firmware/RF behavior.

Он **не является источником истины для SerialTerminal API** и не должен переопределять `.agents/skills/serialterminal-agent/SKILL.md` или [AGENT_API.md](../../../AGENT_API.md). Source of truth для firmware/protocol поведения остаётся соответствующий source checkpoint `lora-sack-protocol` и фактически подтверждённое hardware behavior.

Этот skill не хранит concrete node IDs, MAC/BLE addresses, USB paths, текущие measurements или текущую lab topology. Такие сведения относятся к конкретному run/evidence и обрабатываются по [NODE_SKILL_LEARNING_POLICY.md](../../../NODE_SKILL_LEARNING_POLICY.md).

## Подключение и discovery

Работай через SerialTerminal agent, а не через прямой BLE/LoRa access:

```bash
python3 serialterminal.py agent
```

Если host Bluetooth/D-Bus или sandbox возвращает `Operation not permitted`/другой permission error, это не означает отсутствие устройства. Используй разрешённый окружением способ запуска с необходимыми правами или сообщи о permission boundary.

Обнаружение:

```json
{"id":1,"op":"discover","scope":"auto"}
```

Discovery отражает **текущую доступность transports**, а не постоянную inventory нод. В одном run могут быть доступны BLE, USB serial или другие поддерживаемые transport paths, а в другом часть из них может отсутствовать.

Для определения физической ноды используй `/id`. Если два transport paths сообщают одну и ту же node identity, считай их двумя путями к одной физической ноде, а не двумя отдельными нодами.

Открывай каждую нужную физическую ноду как отдельную long-lived session по текущему `device_key`, полученному из discovery. Не хардкодь конкретные addresses или session IDs из предыдущих запусков.

При `open` с `auto_id=true` SerialTerminal отправляет `/id` как connect preamble после connect/reconnect до публикации session как connected.

## BLE-потоки и получение данных

BLE LoRa-Chatter session имеет два независимых потока:

- `chat` — человекочитаемый вывод, команды и сообщения;
- `telemetry` — машинная телеметрия и диагностические события радиоканала.

При открытии BLE session SerialTerminal сам подписывается на telemetry characteristic. Отдельную команду подписки через agent API отправлять не нужно.

Для реактивной работы используй `wait_events`. Для нескольких sessions храни отдельный cursor на каждую session и после каждого ответа продолжай именно с возвращённым объектом `cursors`.

`wait_events` может оставаться pending, пока тот же agent process принимает обычные команды. Ответы JSONL могут приходить не в порядке запросов, поэтому всегда сопоставляй их по request `id`.

`timeout_ms` — только максимальная длительность конкретного long-poll, а не protocol constant.

BLE notification boundary не является границей текстовой строки. Если одна строка разбита на несколько RX events, склеивай соседние fragments по session/stream/seq до завершения строки.

## Что считать подтверждением

`send_line`/`send_bytes` с `state=queued` подтверждает только постановку данных в reconnect-safe TX queue.

Последующее событие `tx_state=written` подтверждает только успешный вызов transport `write()`.

Ни `queued`, ни `written`, ни локальная строка отправителя с префиксом `>` сами по себе не доказывают peer delivery.

Higher-level доставку подтверждай peer RX/telemetry/application-level evidence.

## USER-передача между нодами

Для обычной проверки radio delivery используй уникальный payload и последовательный сценарий:

```text
Node A send USER payload
→ wait for real peer RX on Node B
→ only then Node B send another USER payload
→ wait for real peer RX on Node A
```

Успешный peer receive обычно подтверждается комбинацией:

- telemetry `RX USER`;
- chat-строкой вида `< [RSSI/SNR Q] payload`;
- совпадением уникального payload.

RSSI/SNR/Q являются measurements конкретного run и не должны превращаться в постоянные expected values skill.

## Одновременные передачи и half-duplex

LoRa-канал между нодами half-duplex, поэтому близкие по времени передачи могут столкнуться.

Для обычного acceptance/smoke используй последовательные передачи с подтверждённым peer RX.

Для отдельного concurrency/collision test можно намеренно поставить TX в независимые queues разных sessions. SerialTerminal способен обслуживать такие sessions независимо, но radio outcome оценивай только по RX/telemetry, а не по факту локального queue/write.

## Режимы вывода

Команды переключают human-console routing:

```text
/chat  -> OUTPUT CHAT
/tele  -> OUTPUT TELEMETRY
/both  -> OUTPUT BOTH
```

Ожидаемое наблюдаемое поведение:

- `/chat` — подтверждение `OUTPUT CHAT` в `chat`;
- `/tele` — подтверждение режима TELEMETRY в `telemetry`;
- `/both` — подтверждение BOTH может быть видно в `chat` и `telemetry`.

Команды output mode меняют маршрутизацию presentation/telemetry, а не сам факт существования LoRa-связи.

После smoke test верни ноду в ожидаемый безопасный mode, обычно `/chat`, если задача не требует другого состояния.

## Echo-режим

`/echo` переключает echo-mode.

Подтверждение включения:

```text
[SYS] ECHO MODE ON
```

В echo-mode обычный текст становится `ECHO_REQUEST`; peer отвечает `ECHO_REPLY`.

Для настоящего ECHO PASS требуй не только локальный ECHO TX, а совокупное evidence:

```text
sender: TX ECHO_REQUEST
peer:   RX ECHO_REQUEST
peer:   TX ECHO_REPLY
sender: RX ECHO_REPLY / correlated ECHO result
```

После проверки обязательно выключи echo повторным `/echo`, если задача не требует оставить его включённым.

Если ECHO_REPLY не подтверждён или evidence неполное, результат должен быть FAIL/BLOCKED/INCONCLUSIVE по фактам, а не guessed PASS.

## Перезагрузка ноды

`/reboot` реально перезагружает ESP32 controller. Используй его только когда задача явно требует reboot/fault/recovery scenario.

Ожидаемые признаки включают:

```text
[SYS] REBOOTING
...
[SYS] CHATTER NODE LoRa-Chatter-<identity>
```

При BLE reboot кратковременный переход session через:

```text
disconnected -> reconnecting -> connected
```

является ожидаемым transport consequence. `ManagedSession` продолжает держать тот же physical `device_key`; после reconnect при `auto_id=true` снова выполняется `/id` preamble. Не открывай новую session только из-за ожидаемого reboot disconnect, если существующая managed session успешно reconnectится.

## Fault scenario: controller доступен, RF power отсутствует

Возможен intentional hardware state, когда ESP32/controller остаётся запитан и transport к нему доступен, а питание radio module/mezzanine отсутствует.

В таком состоянии boot может сообщить:

```text
[SYS] RADIO UNAVAILABLE bootTxSelfTest (-5); RF disabled
```

Это один из возможных fault/degraded scenarios, а не постоянное свойство конкретной ноды.

При такой проверке отличай доступность controller transport от доступности RF path. Не интерпретируй рабочий USB/BLE control path как доказательство исправного RF и не интерпретируй `RADIO UNAVAILABLE` как неисправность самого USB/BLE transport.

Если задача проверяет отсутствие automatic RF recovery после degraded boot, наблюдай требуемое окно и рапортуй только реально увиденное; не превращай длительность одного run в универсальную protocol constant.

## `/help` и доступные команды

Проверенная команда `/help` описывает:

```text
/help     show this help
/id       show node identity
/chat     human console CHAT
/tele     human console TELEMETRY
/both     human console BOTH
/echo     toggle echo mode
/reboot   reboot ESP32 controller
```

Также firmware может сообщать raw controls:

```text
0x31 / 14 31 -> CHAT
0x32 / 14 32 -> TELEMETRY
0x33 / 14 33 -> BOTH
0x65 / 14 65 -> ECHO toggle
```

При сомнении о доступном command set сначала выполни `/help` на фактически подключённой ноде вместо предположения по старому run.

## Диагностические признаки

Telemetry может содержать счётчики и диагностические блоки, включая:

```text
TX ok
RX ok
user
echo_req
echo_rep
crc
hdr
bad
readerr
Q
drops
SESSION
DIO0_TX
RX_POLL
PEER_REPORT
RX/TX ECHO_*
```

Используй их как evidence текущего сценария, но не превращай текущие значения counters/quality в class-level constants.

Для radio validation полезна совокупность признаков:

1. local request принят SerialTerminal queue;
2. transport write выполнен;
3. peer показал соответствующий RX или protocol event;
4. для ECHO наблюдалась request/reply цепочка;
5. measurements подтверждают фактическое состояние канала, но не являются сами по себе критерием identity или постоянной конфигурации.

## Работа с неожиданностями

Если hardware behavior противоречит этому skill или expected result:

- не переписывай skill автоматически;
- явно рапортуй expected vs observed;
- приложи достаточное evidence и reproduction steps;
- пометь результат как anomaly/bug candidate или insufficient evidence;
- дальнейшее обобщение и update skill выполняются reviewer-ом по `NODE_SKILL_LEARNING_POLICY.md`.

Главный принцип:

```text
skill = reusable rules for the class
run evidence = facts about particular objects in a particular experiment
```
