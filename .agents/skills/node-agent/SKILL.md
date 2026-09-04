---
name: lora-chatter-nodes
description: Project-specific class-level правила работы и проверки LoRa-Chatter нод через SerialTerminal agent API.
---

# LoRa-Chatter nodes

Этот skill содержит только reusable правила работы с **классом LoRa-Chatter node** и project-specific acceptance criteria.

Generic SerialTerminal workflow, JSONL schema, sessions, cursors, `wait_events`, transport errors и queue/write semantics бери из [serialterminal-agent](../serialterminal-agent/SKILL.md) и [AGENT_API.md](../../../AGENT_API.md). Не дублируй их здесь.

Firmware/protocol authority — актуальные source/docs `dreamworkerln/lora-sack-protocol` соответствующего Chatter checkpoint. Правила reliable USER ниже относятся к текущему ACK-capable Chatter checkpoint; если задача явно проверяет старый best-effort checkpoint, используй его собственный source/docs contract.

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
/help        show current command set
/id          show canonical node identity
/chat        human console CHAT
/tele        human console TELEMETRY
/both        human console BOTH
/echo        toggle diagnostic echo mode
/cancel      stop current reliable USER retry, or remove one unsent queued USER
/cancel all  stop current reliable USER retry and clear queued USER messages
/reboot      reboot ESP32 controller
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

CHAT не является protocol log. Для USER сохраняется compact human design:

```text
> text
< [RSSI/SNR Q] text
```

Первый успешный physical USER TX печатает `>` один раз. Retry не создаёт дополнительных `>` lines. Успешный matching ACK молчит в CHAT.

ACK, `WAIT_ACK`, attempt number, timeout, backoff, retry/defer, queue depth, ACK matched/unmatched и duplicate/stale classification относятся к TELEMETRY. В CHAT/SYSTEM reliability должна всплывать только как actionable outcome, например delivery failure, cancellation или queue-full rejection.

После обычного smoke верни output mode в `/chat`, если задача не требует другого финального состояния.

## Local command matching и payload

Для распознавания local command firmware нормализует только boundary whitespace/control bytes. Если строка не распознана как local command, в USER/ECHO payload должен идти исходный текст, а не нормализованная копия.

Для USER/ECHO agent tests отправляй payload длиной `1..200` UTF-8 bytes включительно.

Не считай локальное распознавание команды радиопередачей.

## Reliable USER delivery

Текущий ACK-capable Chatter использует bounded stop-and-wait для USER traffic:

```text
one reliable USER in-flight
N reliable USER waiting in bounded queue
```

Пока один USER находится в `WAIT_ACK` или retry backoff, новые USER lines могут приниматься в reliability queue. Local controls остаются отдельной lane и не должны намеренно блокироваться за этой очередью.

Logical USER identity:

```text
(sender_session_id, user_seq)
```

Retry обязан повторять тот же identity и тот же payload. ACK подтверждает именно этот USER identity; passive peer report, SerialTerminal `queued`, transport `written` и локальный `>` ACK не заменяют.

Current hardware-validation policy в firmware:

```text
maximum physical USER attempts = 5
reliable USER queue depth = 8
```

Это configurable implementation policy, а не вечные wire-protocol constants. Если firmware source/docs отличаются, source/docs являются authority.

Для обычного bidirectional smoke используй уникальные payloads и последовательный сценарий:

```text
A sends USER
-> require peer USER/application evidence on B
-> require matching ACK/delivery evidence on A
-> B sends another unique USER
-> require peer USER/application evidence on A
-> require matching ACK/delivery evidence on B
```

Для нормального reliable USER PASS сильное evidence включает обе стороны: peer действительно показал/принял уникальный USER, а sender получил matching ACK для того же logical USER. Не повышай только локальный `>` или transport write до delivery PASS.

Half-duplex simultaneous TX может привести к collision. В reliable checkpoint это отдельный concurrency/retry scenario: collision допустим как промежуточное событие, но bounded randomized retries должны в итоге развести обмен или закончиться явным failure после лимита.

Локальный firmware marker `>` означает подтверждённый local physical TxDone + успешное возвращение TX path к RX, но **не доказывает peer delivery**.

Не превращай RSSI/SNR/Q конкретного run в expected constants.

## Receiver duplicate и ACK semantics

На NEW USER peer должен показать USER в CHAT один раз и создать ACK obligation.

Если ACK потерялся, sender может повторить тот же USER identity. Такой DUPLICATE не должен повторно появляться в peer CHAT, но peer должен снова отправить ACK.

STALE USER вне recent window не должен заново показываться как пользовательское сообщение и не требует ACK по текущему contract.

ACK сам не ACK-ается. HEARTBEAT и ECHO остаются best-effort и не входят в reliable USER state machine.

Wrong-session, wrong-seq, stale или unrelated ACK не должен завершать текущий pending USER.

## Reliable queue и cancellation

Если reliable USER queue заполнена, новый USER должен быть явно отклонён, а не silently dropped и не представлен как accepted delivery. Ожидаемый SYSTEM outcome:

```text
[SYS] SEND QUEUE FULL: message not accepted
```

`/cancel` имеет две разные semantics:

```text
in-flight USER already physically transmitted
    -> stop future retries
    -> delivery status remains unknown

no in-flight USER, queued unsent USER exists
    -> remove one queued USER
    -> it was not transmitted
```

После хотя бы одного physical TX отменить уже возможную peer delivery невозможно. Поэтому in-flight cancellation не означает «peer точно не получил».

`/cancel all` останавливает текущий reliable USER retry, если он есть, и очищает queued reliable USER messages.

Для cancellation tests проверяй не только SYSTEM text, но и telemetry: после cancellation не должно появляться дальнейших retry TX для отменённого logical USER.

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

Reliable USER имеет приоритет над lower-priority ECHO RF work: pending USER/ACK flow не должен быть обогнан новым ECHO request.

После теста обязательно верни echo OFF, если задача явно не требует оставить его включённым.

## Focused two-node reliability gate

Перед закрытием ACK reliability checkpoint проверь отдельными hardware scenarios как минимум:

```text
normal USER -> ACK
lost USER -> retry -> ACK
lost ACK -> duplicate USER -> no duplicate CHAT -> repeated ACK
simultaneous USER from both nodes -> retries eventually separate or bounded explicit failure
peer off -> bounded retries -> DELIVERY FAILED after configured max attempts
peer returns during retry window -> pending USER can deliver
new USER typed while another waits -> queued and later delivered
queue full -> explicit rejection
/cancel on in-flight USER -> retries stop, status unknown
/cancel on unsent queued USER -> removed before TX
/cancel all -> current retry stopped + queue cleared
wrong-session ACK -> ignored
wrong-seq ACK -> ignored
stale/duplicate ACK -> harmless
heartbeat remains best-effort
ECHO remains independent best-effort diagnostic traffic
```

Для lost USER/lost ACK/wrong ACK scenarios не выдумывай evidence и не подменяй fault injection предположением. Если доступный hardware setup не умеет детерминированно создать нужный fault, пометь scenario `BLOCKED` или `INCONCLUSIVE` и зафиксируй причину. Не выполняй destructive fault injection без явной задачи пользователя.

Для lost-ACK acceptance особенно важно одновременно доказать:

```text
peer CHAT showed USER exactly once
peer telemetry classified retransmission as duplicate
peer sent repeated ACK
sender eventually matched ACK
```

Для peer-off scenario убедись, что retries bounded и после final failure не продолжаются бесконечно.

## Reboot

`/reboot` перезагружает ESP32 controller. Используй его только для явно заданного reboot/fault/recovery scenario.

Transport disconnect/reconnect во время reboot сам по себе не означает появление новой физической ноды; после восстановления снова проверь canonical identity, если это важно для сценария.

Reliability не обещает exactly-once semantics через reboot/NVS persistence. Не переноси pre-reboot pending identity assumptions через reboot без explicit evidence.

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
reliable USER flow settled; no unintended retry left running
output CHAT
opened test sessions closed when no longer needed
```

Если тест намеренно оставил pending/queued USER и требуется очистить его перед завершением, используй documented cancellation semantics и зафиксируй resulting delivery status; не объявляй cancellation доказательством недоставки уже transmitted USER.

Главный принцип:

```text
skill = reusable operating/validation rules for the class
run-specific facts belong to evidence, not to this skill
```
