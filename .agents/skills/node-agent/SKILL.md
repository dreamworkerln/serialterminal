---
name: lora-chatter-nodes
description: Project-specific class-level правила работы и проверки LoRa-Chatter нод через SerialTerminal agent API.
---

# LoRa-Chatter nodes

Этот skill содержит только reusable правила работы с **классом LoRa-Chatter node** и project-specific acceptance criteria.

Generic SerialTerminal workflow, JSONL schema, sessions, cursors, `wait_events`, transport errors и queue/write semantics бери из [serialterminal-agent](../serialterminal-agent/SKILL.md) и [AGENT_API.md](../../../AGENT_API.md). Не дублируй их здесь.

Firmware/protocol authority — актуальные source/docs `dreamworkerln/lora-sack-protocol` соответствующего Chatter checkpoint.

Не хардкодь concrete node IDs, MAC/BLE addresses, USB paths, session IDs, RSSI/SNR/Q, current topology или текущее состояние конкретного экземпляра.

## Identity и discovery

Canonical node identity имеет вид:

```text
LoRa-Chatter-XXXX
```

Получай identity через `/id`.

Discovery показывает текущие доступные transport paths, а не постоянный inventory. Если разные transports возвращают одну и ту же canonical identity, считай их путями к одной физической ноде.

## Local commands

Основные human-readable commands:

```text
/help     show current command set
/id       show canonical node identity
/chat     human console CHAT
/tele     human console TELEMETRY
/both     human console BOTH
/echo     toggle diagnostic echo mode
/reboot   reboot ESP32 controller
```

При сомнении в доступном command set сначала используй `/help` на подключённой ноде.

Raw local controls существуют как стабильный ABI для transport/UI integration:

```text
14 31   CHAT
14 32   TELEMETRY
14 33   BOTH
14 65   ECHO toggle
```

Для обычных agent tests предпочитай human-readable commands, если задача специально не проверяет raw ABI.

## Human console и machine telemetry

Output mode управляет human console:

```text
/chat   -> CHAT + SYSTEM
/tele   -> TELEMETRY + SYSTEM
/both   -> CHAT + TELEMETRY + SYSTEM
```

SYSTEM остаётся human-console output.

BLE machine telemetry является отдельным background stream и при подписке доступна независимо от `/chat` / `/tele` / `/both`. Не используй переключение human output mode как доказательство наличия или отсутствия RF traffic.

После обычного smoke верни output mode в `/chat`, если задача не требует другого финального состояния.

## Local command matching и payload

Для распознавания local command firmware нормализует только boundary whitespace/control bytes. Если строка не распознана как local command, в USER/ECHO payload должен идти исходный текст, а не нормализованная копия.

Не считай локальное распознавание команды радиопередачей.

## USER radio delivery

`dev_chat` — best-effort protocol без ACK/retry reliability layer.

Для обычного bidirectional smoke используй уникальные payloads и последовательный сценарий:

```text
A sends USER
-> require peer evidence on B
-> B sends another USER
-> require peer evidence on A
```

Half-duplex simultaneous TX может привести к collision, поэтому concurrency test отделяй от обычного delivery acceptance.

Peer delivery подтверждай по фактическому peer RX/application evidence, например совпавшему уникальному payload и соответствующему RX USER event/rendering.

Локальный firmware marker `>` означает подтверждённый local physical TxDone + успешное возвращение TX path к RX, но **не доказывает peer delivery**.

Не превращай RSSI/SNR/Q конкретного run в expected constants.

## Diagnostic ECHO

Echo mode локальный и после boot должен быть OFF.

`/echo` переключает mode. Когда mode ON, новая пользовательская строка передаётся как `ECHO_REQUEST` вместо USER.

Peer на валидный `ECHO_REQUEST` формирует один `ECHO_REPLY`; reply сам не порождает новый reply.

Локальный request удовлетворяется только matching reply по protocol correlation. Stale/unrelated reply не считается успехом.

Для ECHO PASS требуй полную logical chain:

```text
sender TX ECHO_REQUEST
peer RX ECHO_REQUEST
peer TX ECHO_REPLY
sender RX matching ECHO_REPLY
```

Отсутствие matching reply до firmware deadline даёт ECHO failure/no-response; ECHO остаётся best-effort и не ретраится автоматически.

После теста обязательно верни echo OFF, если задача явно не требует оставить его включённым.

## Reboot

`/reboot` перезагружает ESP32 controller. Используй его только для явно заданного reboot/fault/recovery scenario.

Transport disconnect/reconnect во время reboot сам по себе не означает появление новой физической ноды; после восстановления снова проверь canonical identity, если это важно для сценария.

## Radio degraded/fatal semantics

Boot radio init или physical boot-TX POST failure переводит firmware в degraded state `RADIO UNAVAILABLE`: controller и transport могут оставаться доступны, но RF path недоступен.

Это условный hardware/fault state, а не свойство конкретной ноды.

Runtime radio-loss policy отличается от boot degraded behavior: подтверждённый runtime health loss приводит к centralized fatal path и reboot.

Не используй доступность USB/BLE controller transport как доказательство RF health.

Не используй успешный `RegVersion` read как доказательство RF power/output path: это только digital/SPI liveness sample. Для TX truth firmware использует `RegIrqFlags.TxDone`; DIO0 является diagnostic only.

Не выполняй destructive fault injection без явной задачи пользователя.

## Validation outcomes

Для каждого hardware scenario используй фактический результат:

```text
PASS
FAIL
BLOCKED
INCONCLUSIVE
```

Не повышай `queued`, transport `written`, local TX marker или неполный telemetry fragment до higher-level PASS без требуемого protocol/application evidence.

Если behavior расходится с expected contract:

- явно укажи expected vs actual;
- сохрани достаточные evidence/reproduction details;
- рапортуй anomaly/bug candidate;
- не объявляй неожиданное поведение новым правильным contract.

## Safe final state

После обычной hardware validation, если задача не задаёт другое состояние:

```text
echo OFF
output CHAT
opened test sessions closed when no longer needed
```

Главный принцип:

```text
skill = reusable operating/validation rules for the class
run-specific facts belong to evidence, not to this skill
```
