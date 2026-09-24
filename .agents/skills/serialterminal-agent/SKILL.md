---
name: serialterminal-agent
description: Работа с machine-facing SerialTerminal JSONL agent API для capability-based discovery, long-lived sessions, send и canonical observe.
---

# SerialTerminal agent

Это repo-local operational skill для `serialterminal agent`.

## Сначала прочитай API contract

Полный и канонический контракт находится в [AGENT_API.md](../../../AGENT_API.md).

Не переопределяй здесь schema, error codes или transport/session semantics. Если этот skill и `AGENT_API.md` расходятся, источником истины является `AGENT_API.md`.

## Базовый workflow

Запусти один долгоживущий процесс:

```bash
python3 serialterminal.py agent
```

Работай с ним по JSON Lines:

1. `discover` — получить supported `device_key`;
2. `open` — открыть одну или несколько sessions; `generic` используется по умолчанию, controller profile выбирай явно;
3. сохранить `latest_seq` каждой session;
4. передавать через `send_line` / `send_bytes`;
5. получать completed logical lines через `observe` + `cursors`;
6. после каждого `observe` продолжать именно с возвращёнными cursors;
7. для protocol reasoning использовать default `result.lines`; raw `result.events`/`data_b64` запрашивать только через `include_events:true` для конкретной forensic необходимости;
8. закрыть sessions через `close`; EOF agent process закроет оставшиеся.

Переиспользуй один agent process и уже открытые sessions. Для большой автономной проверки предпочитай один длинный сценарный проход с явными phases/checkpoints вместо десятков одинаковых `discover/open/close` циклов.

## Discovery

BLE discovery capability-based: устройство появляется, если advertising standard NUS или его адрес уже имеет cached confirmed NUS capability. Advertised name и controller profile не являются доказательством capability и не whitelist-ят устройство.

Transient UNKNOWN probe не означает NO и не должен заставлять scenario считать ранее подтверждённый target неподдерживаемым. Definitive probe result остаётся authoritative.

Если target отсутствует, используй Bluetooth capability scanner/prober и повтори `discover`. После discovery открывай возвращённый `device_key`; не используй BLE name aliases.

## Profiles

`open` без `profile` использует `generic`. Generic session не отправляет controller-specific connect preamble; generic BLE использует standard NUS и stream `main`.

Project-specific skill может явно выбрать bundled profile, например `"profile":"chatter"`. Profile задаётся на session, поэтому один process может одновременно держать разные profiles.

Connect preamble полностью принадлежит profile. Не используй legacy `auto_id` или собственные generic preamble toggles.

## Observe и cursors

`observe` — единственный receive/cursor workflow. По умолчанию ответ не содержит raw `events`:

```json
{"id":20,"op":"observe","cursors":{"s1":42},"timeout_ms":15000}
```

Для нескольких sessions:

```json
{"id":21,"op":"observe","cursors":{"s1":42,"s2":75},"timeout_ms":15000}
```

Raw transport evidence запрашивай только явно:

```json
{"id":22,"op":"observe","cursors":{"s1":42,"s2":75},"timeout_ms":15000,"include_events":true}
```

Без `include_events:true` поле `result.events` отсутствует. Cursor всё равно остаётся event cursor и двигается при raw activity; если chunk ещё не завершил LF-line, `result.lines` может быть пустым при уже продвинувшемся cursor.

`observe` требует непустой request `id`. Пока observation pending, этот ID нельзя использовать снова. Ответы могут приходить не в порядке запросов, поэтому всегда коррелируй по `id`.

`timeout_ms` — максимум конкретного long-poll, а не protocol constant. После timeout или event при необходимости сразу запускай следующий `observe` с возвращёнными cursors.

Если raw event пришёл, но LF ещё не завершил firmware line, `result.lines` может быть пустым. Не склеивай chunks вручную; продолжай observation, session layer хранит незавершённый line state.

## Два уровня receive evidence

```text
firmware/protocol reasoning   -> result.lines
transport/chunk forensics     -> result.events / data_b64
```

`result.events` при `include_events:true` сохраняет raw session event truth: `seq`, state/TX metadata, stream, chunk boundaries, decoded chunk text и exact bytes через `data_b64`. Без opt-in эти данные остаются в forensic `.log`, но не размножаются в model-facing JSON response.

`result.lines` содержит только завершённые LF-terminated lines. Line assembly выполняется один раз на session layer независимо для каждого stream.

## TX semantics

`send_line`/`send_bytes` с `state=queued` означает только принятие reconnect-safe TX queue.

`tx_state=written` означает успешное завершение transport `write()`. Это не доказательство peer delivery, firmware acceptance или выполнения higher-level operation.

`tx_state=unknown` означает, что transport side effect неоднозначен. Текущий пример — BLE GATT write timeout: backend write мог завершиться поздно даже после cancellation request. SerialTerminal **не** выполняет automatic retry такого TX, чтобы не создавать потенциальный duplicate side effect.

При `unknown` не делай blind resend. Используй последующие RX/application-level данные, чтобы определить результат; если доказательства недостаточны, outcome сценария должен быть `INCONCLUSIVE`/ambiguous согласно consuming skill, а не выдуманный PASS/FAIL доставки.

Ordinary definite transport failures могут быть retry после reconnect самим session layer; порядок очереди сохраняется.

## Run logs и forensic gaps

Agent создаёт пару:

```text
serialterminal-...log
serialterminal-...console.log
```

Основной `.log` — forensic/API/transport evidence. Companion `.console.log` — human-oriented presentation: `send_line` как `[sN] [I]`, completed console RX lines как `[sN] [O]`. Background streams остаются только в forensic log/observe events.

Если persisted event logger потерял часть bounded session event history, `.log` содержит explicit `[ERROR]` payload с `event="forensic_gap"` и lost sequence range. Такой лог нельзя трактовать как непрерывную forensic history через этот диапазон.

Если broad scenario требует строгой evidence completeness, `forensic_gap` должен делать соответствующий участок проверки `INCONCLUSIVE` или FAIL по правилам consuming skill; никогда не игнорируй gap silently.

## Ошибки

Не делай blind retry при structured error. Сначала читай `error.code`, `error.message`, details и при необходимости forensic log/`AGENT_API.md`.

`cursor_expired` относится к raw SessionEvent retention window; отдельного line cursor нет.

Permission errors Bluetooth/D-Bus/sandbox не означают отсутствие устройства и не являются основанием сразу завершать workflow как BLOCKED. Если операция необходима для текущей задачи и уже разрешена её scope, сначала запроси минимально необходимое elevated permission для конкретной операции или command prefix, затем повтори её.

Ошибки вида `Operation not permitted`, `Permission denied`, `EACCES`, `EPERM`, read-only sandbox path или заблокированный доступ к device/D-Bus/network трактуй как access boundary. BLOCKED допустим только если elevation недоступно, явно отклонено или повтор после одобренного elevation всё равно не может выполнить необходимую операцию.

Разные классы операций могут требовать отдельных approvals. Не предполагай, что разрешение на BLE discovery автоматически покрывает open/write/device access, а разрешение на одну Git operation покрывает другую. Для разрешённых Git/evidence операций при sandbox failure также запрашивай узкое elevated permission для точной команды/helper или необходимого Git metadata/network access и повторяй операцию. Elevation не расширяет task scope и не разрешает действия, которые исходно запрещены.

## Большие автономные сценарии

Для build-level проверки, где project-specific skill умеет управлять устройствами через JSONL API:

- держи один agent process и минимально необходимое число long-lived sessions;
- разделяй сценарий на phases с уникальными payload/markers, чтобы старый RX нельзя было спутать с новым;
- перед каждым phase сохраняй cursors и проверяй только новые события/lines;
- выполняй independent assertions по каждой session/направлению;
- не считай `queued`/`written` доставкой;
- обрабатывай `unknown`, `cursor_expired`, `forensic_gap`, disconnect/reconnect как first-class outcomes;
- собирай один run bundle после полного сценария вместо множества ручных повторов, если project policy это допускает;
- UI-only hotkeys/visual presentation не пытайся доказывать machine API, если для них нет отдельного PTY/UI harness.
- не перечитывай накопленный stdout background agent process после того, как его JSON responses уже были обработаны; после clean close/EOF проверяй только нужный final state или finalized logs;
- finalized `.log`/`.console.log` проверяй targeted search/count/summary; не загружай целиком большой forensic log обратно в model context без конкретной forensic необходимости.

Firmware-specific команды, RSSI/SNR/Q, radio collision rules, reboot/cancel semantics и acceptance criteria остаются в project-specific skill, а не здесь.
