---
name: lora-chatter-nodes
description: Project-specific class-level правила работы и проверки LoRa-Chatter нод через SerialTerminal agent API.
---

# LoRa-Chatter nodes

Этот skill содержит только reusable правила работы с **классом LoRa-Chatter node** и project-specific acceptance criteria.

Generic SerialTerminal workflow, JSONL schema, sessions, `observe`, cursors, transport errors и queue/write semantics бери из [serialterminal-agent](../serialterminal-agent/SKILL.md) и [AGENT_API.md](../../../AGENT_API.md). Не дублируй их здесь.

Firmware/protocol authority — актуальные source/docs `dreamworkerln/lora-sack-protocol` соответствующего Chatter checkpoint. Правила reliable USER ниже относятся к текущему ACK-capable Chatter checkpoint; если задача явно проверяет старый best-effort checkpoint, используй его собственный source/docs contract.

Не хардкодь concrete node IDs, MAC/BLE addresses, USB paths, session IDs, RSSI/SNR/Q, current topology или текущее состояние конкретного экземпляра.

## Identity и discovery

Canonical node identity имеет вид:

```text
LoRa-Chatter-XXXX
```

Получай identity через `/id`.

Discovery показывает текущие доступные transport paths, а не постоянный inventory. Для BLE имя `LoRa-*` само по себе не является capability signal: обычный SerialTerminal discovery показывает advertised-NUS или cached confirmed-NUS targets. Если ожидаемая BLE-нода отсутствует, сначала подтверди NUS через Bluetooth capability scanner/prober, затем повтори `discover`.

Если разные transports возвращают одну и ту же canonical identity, считай их путями к одной физической ноде.

Каждую Chatter session открывай по возвращённому `device_key` через SerialTerminal agent с явным `"profile":"chatter"`. Не полагайся на generic default profile: именно Chatter profile задаёт controller connect preamble и Chatter BLE stream layout, включая `/id` при connect/reconnect. Отдельного identity/preamble toggle в agent API нет.

## Firmware provenance

Для актуального Chatter firmware не выводи physical firmware provenance из branch name, локального checkout, operator-stated target или предполагаемой прошивки. Получай provenance **с самой физической ноды**.

Новые Chatter builds выводят source provenance при boot и полный integrity/build identity по `/version` (alias `/firmware`):

```text
[SYS] FIRMWARE Chatter git=<40-hex SHA> state=<clean|dirty|unknown> env=<pio-env>
[SYS] FIRMWARE IMAGE validation_sha256=<64-hex> status=<OK|...> slot=<0|1>
[SYS] BUILD META toolchain_sha256=<64-hex> pio=<version>
```

Первая строка остаётся canonical source-provenance line. Вторая и третья строки добавляют running-image и build/toolchain identity; не подменяй одно другим.

Перед measured hardware scenario, после установления identity каждой физической ноды, получи firmware provenance read-only:

```text
предпочтительно:
    уже наблюдённые boot provenance/integrity lines

иначе:
    send_line "/version"
    observe полный блок из доступных [SYS] FIRMWARE / FIRMWARE IMAGE / BUILD META lines
```

Обычно достаточно запросить `/version` по одному стабильному transport каждой физической ноды, предпочтительно USB. SYSTEM output может одновременно появляться и на BLE 0003; не считай одинаковые строки на двух transports двумя разными firmware observations. Сначала свяжи transports через canonical `/id`.

Acceptance для exact physical source SHA:

```text
git=<exact 40-hex> AND state=clean
    -> exact firmware source SHA установлен с самой ноды

state=dirty
    -> reported git SHA только base commit
    -> exact firmware source provenance НЕ установлен

state=unknown OR git=unknown
    -> exact firmware source provenance НЕ установлен

/version unsupported / no canonical response
    -> для старой прошивки firmware provenance остаётся unknown
```

Не называй `state=dirty` exact firmware SHA даже если 40-hex Git value присутствует. В REPORT сохрани каноническую строку целиком как evidence, но canonical run/observation firmware SHA ставь `unknown`.

Для прошивки, которая поддерживает runtime integrity lines, дополнительно различай три разных digest/identity:

```text
git=<40-hex>
    -> exact source commit при state=clean

validation_sha256=<64-hex>
    -> ESP running application image validation digest
    -> это НЕ SHA-256 полного firmware.bin файла

toolchain_sha256=<64-hex>
    -> SHA-256 canonical build/toolchain record
    -> exact resolved build metadata identity

release manifest artifact.sha256
    -> SHA-256 полного firmware.bin
    -> внешний artifact identity; нода его напрямую не сообщает
```

Для exact runtime-image release gate:

```text
node [SYS] FIRMWARE IMAGE status=OK
AND node validation_sha256 == release-manifest artifact.image_validation_sha256
    -> running application image совпадает с ожидаемым ESP image identity
```

Если `status` не `OK`, строка отсутствует у firmware, которая по контракту обязана её поддерживать, или digest не совпадает с ожидаемым manifest — exact runtime-image gate не пройден. До measured behavior phase это precondition failure / BLOCKED, а не RF/ACK behavior FAIL.

Для exact build-metadata gate:

```text
node toolchain_sha256 == release-manifest toolchain.sha256
    -> fwmeta canonical toolchain/build record совпадает с ожидаемым release manifest
```

Mismatch или отсутствующая строка у firmware, которая обязана поддерживать новый контракт, — precondition failure / BLOCKED для exact build-metadata release gate.

При новом integrity-capable firmware сохраняй в REPORT/OBS как exact evidence все три строки `/version`, плюс ожидаемые manifest values, когда они доступны:

```text
source git SHA/state/env
running image validation_sha256/status/running OTA slot
toolchain_sha256 + pio version
expected release-manifest artifact.image_validation_sha256
expected release-manifest toolchain.sha256
external SHA-256(firmware.bin), если он известен из release manifest
```

Не записывай `validation_sha256` в поле `firmware.sha`: canonical `MANIFEST.json -> firmware.sha` schema v1 остаётся source Git SHA или `unknown`. Не записывай `toolchain_sha256` вместо source SHA.

Если measured scenario требует обе физические ноды на одном exact release checkpoint, до измерения проверь доступные уровни provenance:

```text
source:
    node A state=clean, git=<expected SHA>
    node B state=clean, git=<expected SHA>
    A.git == B.git == expected SHA

для integrity-capable release:
    A.status == B.status == OK
    A.validation_sha256 == B.validation_sha256 == expected image_validation_sha256
    A.toolchain_sha256 == B.toolchain_sha256 == expected toolchain.sha256
```

Mismatch, `dirty`, `unknown`, failed integrity status или обязательный digest mismatch до measured phase — это precondition failure / BLOCKED для exact-provenance release gate, а не firmware behavior FAIL. Не перепрошивай автоматически; flashing требует явного operator authorization.

## Host Bluetooth audio preflight

Перед обычным measured hardware scenario, который использует BLE transport, сначала выполни read-only preflight Bluetooth/audio состояния host-машины.

Проверяй не конкретную модель устройства, а любой подключённый Bluetooth audio endpoint: headphones, headset, гарнитуру, speaker или другое Bluetooth audio device. Не определяй audio device только по имени. Используй доступные host evidence, например:

```text
bluetoothctl info
wpctl status
pactl list cards
pactl list sink-inputs
```

или эквивалентные read-only средства текущего Linux audio stack.

Ищи как минимум:

```text
Bluetooth device connected
audio profile / A2DP / HSP / HFP evidence
Bluetooth sink/source
active/running audio stream when available
codec/profile when host reports it
```

Не утверждай конкретный codec, profile или active stream, если host evidence этого не показывает.

Если sandbox не даёт выполнить нужную read-only host inspection, допустимо запросить минимально необходимое sandbox permission для этой проверки. Не используй это разрешение для изменения host Bluetooth/audio subsystem.

По умолчанию, если перед BLE hardware validation обнаружен подключённый Bluetooth audio endpoint или активный Bluetooth audio path/stream:

```text
measured BLE scenario не начинать
-> сообщить оператору, что Bluetooth audio device нужно отключить
-> не отключать устройство самостоятельно
-> не менять BlueZ / PipeWire / PulseAudio / WirePlumber configuration
-> не перезапускать host Bluetooth/audio services
```

Это environmental precondition, а не firmware failure.

Если repeated BLE disconnect/reconnect flapping появляется уже во время measured run, останови scenario чисто и не объявляй это автоматически firmware `FAIL`. При наличии evidence конкурирующего host Bluetooth audio зафиксируй его как environmental factor и классифицируй scenario как `BLOCKED` или `INCONCLUSIVE` в соответствии с доступным evidence.

Исключение разрешено только когда оператор явно просит проверить coexistence с подключённым Bluetooth audio, например после обновления/переустановки Linux или изменения host Bluetooth stack. В таком отдельном coexistence scenario:

```text
не блокируй run только из-за active Bluetooth audio
зафиксируй connected audio device/profile/codec/stream evidence до измерения
выполни только явно запрошенный BLE scenario
не меняй host Bluetooth/audio subsystem
при flapping/reconnect не повышай результат до firmware FAIL без независимого firmware evidence
```

Такой coexistence run проверяет host-environment compatibility и не отменяет default preflight для обычных BLE regression/gate tests.

## Local commands

Основные human-readable commands:

```text
/help        show current command set
/id          show canonical node identity
/version     show source + image/build provenance
/firmware    alias for /version
/power       show persisted SX1278 PA_BOOST setting
/power N     apply + persist NVS power setting (2..17 or 20 dBm)
/freq        show persisted frequency
/freq MHz    apply + persist frequency, dot decimal, 1 kHz precision; extra decimals truncate
/freq-oob    show experimental out-of-band flag
/freq-oob on|off persist range policy; OFF=470..510 MHz
/sf          show persisted SF
/sf N        apply + persist SF 7..12
/bw          show persisted bandwidth
/bw kHz      apply + persist one supported SX1278 BW
/config      show persisted radio config
/config reset restore compiled radio defaults in NVS
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

Для hardware evidence используй два уровня SerialTerminal observation:

```text
firmware logical output           -> observe.result.lines
transport/chunk forensic evidence -> observe.result.events
```

Не склеивай raw BLE chunks вручную, если нужная завершённая firmware line уже присутствует в `observe.result.lines`; exact notification/chunk evidence при этом проверяй по `observe.result.events` и `data_b64`.

При `/both` не делай вывод о semantic CHAT только потому, что telemetry line видна в human console. Учитывай текущий firmware output mode и отдельно существующий machine telemetry stream: одна и та же telemetry semantics может быть представлена в human console и background machine stream независимо.

CHAT не является protocol log. Для USER сохраняется compact human design:

```text
> text
< [RSSI/SNR Q] text
```

Первый успешный physical USER TX печатает `>` один раз. Retry не создаёт дополнительных `>` lines. Успешный matching ACK молчит в CHAT.

ACK, `WAIT_ACK`, attempt number, timeout, backoff, retry/defer, queue depth, ACK matched/unmatched и duplicate/stale classification относятся к TELEMETRY. В CHAT/SYSTEM reliability должна всплывать только как actionable outcome, например delivery failure, cancellation или queue-full rejection.

После обычного smoke верни output mode в `/chat`, если задача не требует другого финального состояния.

## Run evidence publication

После hardware interaction следуй [NODE_OBSERVATION_RECORDING_POLICY.md](../../../NODE_OBSERVATION_RECORDING_POLICY.md). Этот policy является source of truth для `REPORT.md`, optional `OBS_*.md`, `RUN_.../`, manifest, backlog и Git recovery semantics.

Обычный complete hardware run публикуй как immutable run bundle:

```text
runs/RUN_<stamp>_<topic>/
    MANIFEST.json
    REPORT.md
    serialterminal.log
    serialterminal.console.log
```

Executor сам создаёт содержимое artifacts. Publication helpers ничего не интерпретируют и не чинят:

```text
complete RUN (+ matching OBS when required)
    -> python3 -I scripts/commit-node-run

standalone observation-only case
    -> python3 -I scripts/commit-node-observation
```

Если observation относится к RUN, используй тот же `<stamp>_<topic>` и canonical строку:

```text
Run bundle: runs/RUN_<stamp>_<topic>/
```

Такой OBS является run-bound и не должен публиковаться через `commit-node-observation`.

Observation нужен прежде всего для reusable finding/anomaly/fault/recovery/FAIL/BLOCKED. Routine PASS run может быть RUN-only, но `MANIFEST.json` обязан явно указать `observation.state=not-required` и причину.

Перед bundle creation восстанови safe final state, закрой sessions и заверши SerialTerminal process, чтобы forensic и console logs были final. Скопируй exact `log_path` и `console_log_path` в bundle; не реконструируй их.

`REPORT.md` — полный curated executor report. `OBS_*.md` — короткое factual наблюдение. Final chat response после successful publication должен быть коротким pointer layer: result, observation path если есть, run path, commit SHA и independent remote verification.

После publication обязательно выполни independent remote verification:

```bash
git -C ../serialterminal-observations ls-remote origin refs/heads/node_observations
```

Если эта read-only verification не выполняется из-за sandbox/network/DNS restriction, например `Could not resolve hostname github.com`, не останавливайся сразу на `REMOTE VERIFY: BLOCKED`. Запроси минимально необходимое sandbox/network permission именно для повторного read-only `git ls-remote` и повтори verification. Не используй это разрешение для каких-либо дополнительных network/write операций.

Только если permission не предоставлен или повторный `ls-remote` с разрешением всё равно не может достичь origin, допустимо финально сообщить `REMOTE VERIFY: BLOCKED` с точной причиной. Если команда возвращает ожидаемый `refs/heads/node_observations` SHA, сообщи `REMOTE VERIFY: OK` и приведи подтверждённый remote SHA.

Если helper оставил/нашёл incomplete canonical backlog от старого interrupted run, не удаляй его. Complete unrelated run может публиковаться отдельно. При push failure не делай reset/rebase/force-push: следующий helper invocation умеет retry только safe validated local-ahead publication commits; divergence остаётся hard failure.

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

### Timing-sensitive Chatter scenario helper

Если correctness сценария зависит от реакции быстрее, чем обычный LLM round-trip между `observe` и следующим `send_line`, используй repository helper:

```bash
python3 -I scripts/run-chatter-scenario cancel-all-current-plus-queue \
  --sender-usb-key <device_key> \
  --sender-ble-key <device_key> \
  --peer-usb-key <device_key> \
  --peer-ble-key <device_key> \
  --log /tmp/serialterminal-chatter-scenario.log
```

Helper является только быстрой orchestration-обёрткой над `serialterminal.py agent` JSONL API. Он не должен открывать pyserial, Bleak, RFCOMM или другие transport backends напрямую; transport/session/reconnect/forensic ownership остаётся у SerialTerminal.

До запуска helper hardware executor обязан выполнить обычный host Bluetooth/audio preflight и получить exact `device_key` четырёх сопоставленных USB/BLE endpoints. Отдельный ad-hoc Python preflight для `/id`, `/echo` или timing orchestration не создавай. В частности, `/echo` является toggle и не должен использоваться как read-only проверка состояния.

Внутри собственного нового `serialterminal.py agent` process helper сам повторно выполняет transport-specific discovery, чтобы заполнить discovery cache: сначала `scope:"serial"`, затем `scope:"ble"`. Для Chatter timing helper не используй `scope:"auto"`: этому сценарию не нужен SPP path, а раздельный discovery сохраняет точную границу permission/backend failure. После discovery helper сначала открывает только USB endpoints, повторно подтверждает identities через `/id` и read-only проверяет `echo=OFF` через `/help`. BLE endpoints открываются только после этой проверки, поэтому help output не создаёт BLE backlog. Затем helper открывает переданные BLE keys, повторно проверяет USB↔BLE пары через `/id` и перед измерением штатно очищает reliable flow через `/cancel all`.

Не hard-code instance-specific device keys, MAC, tty paths или node IDs в skill/script. Отсутствующий после helper discovery expected key или `echo=ON` считаются pre-measurement `BLOCKED`, а не firmware FAIL.

Если helper до открытия measured sessions возвращает `serial_discovery_permission` или `ble_discovery_permission` с `Operation not permitted` / `Permission denied`, это sandbox/host permission boundary, а не выполненный hardware scenario. Запроси минимально необходимое sandbox/hardware permission именно для повторного запуска той же helper-команды и повтори её один раз. Такой privileged retry допустим до measured phase и не считается автоматическим повтором scenario после его результата. Не создавай отдельный canonical RUN/OBS только для первой permission-denied попытки; если permission не предоставлен или privileged retry снова блокируется, тогда зафиксируй один `BLOCKED` run с точной причиной. Не расширяй permission на произвольные Python, shell, source writes, flashing или reboot.

Не держи одновременно другой SerialTerminal process, владеющий теми же device keys: timing-sensitive helper запускает свой один long-lived `serialterminal.py agent`, открывает нужные sessions с `profile:"chatter"`, выполняет scenario и закрывает их.

Текущий subcommand `cancel-all-current-plus-queue` предназначен для deterministic hardware проверки `/cancel all`: он локально ждёт telemetry trigger `waiting>=2 ... in_flight=1` и без LLM round-trip немедленно отправляет BLE `/cancel all`. Финальный stdout — один JSON object с verdict/evidence pointers; exact forensic и companion logs остаются authoritative evidence.

Exit codes:

```text
0  PASS
1  INCONCLUSIVE/BLOCKED
2  FAIL
```

Helper не заменяет RUN/OBS policy и не является основанием автоматически объявлять hardware PASS без проверки его JSON result и exact SerialTerminal logs.

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
