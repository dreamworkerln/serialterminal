---
name: serialterminal-agent
description: Работа с machine-facing SerialTerminal JSONL agent API для discovery, sessions, send/observe, high-level file transfers и long-running sweep jobs.
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
8. для длинной детерминированной матрицы измерений используй generic `sweep_start` / `sweep_observe` вместо LLM/tool turn на каждый sample;
9. для передачи файла на profile с binary capability используй `file_send_start` + `file_transfer_observe`, а не ручные `/bin`/base64/chunks;
10. после terminal file transfer освободи retained state через `file_transfer_close`, когда он больше не нужен;
11. после terminal sweep освободи retained job через `sweep_close`;
12. закрыть sessions через `close`; EOF agent process закроет оставшиеся.

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

## Generic sweep jobs

Для длинного повторяемого измерительного прохода не делай вручную:

```text
send_line
-> observe
-> следующий model/tool turn
-> send_line
-> observe
...
```

Если controller profile предоставляет подходящий adapter, запускай один generic sweep job поверх уже открытых sessions.

Каноническая schema находится только в `AGENT_API.md`; здесь важны operational rules:

- сначала обычными `discover/open` получи already-open sessions;
- `sweep_start` должен описывать deterministic ordered axes и **точное** `repetitions=N`;
- successful start уже держит mutation ownership; до adapter prepare job автоматически проходит pre-sweep TX fence для всех ранее принятых external TX;
- `session_tx_unknown` на этом fence означает ambiguous pre-sweep side effect: не пытайся "додренировать" queue, закрой/переоткрой session или следуй project recovery semantics;
- sweeper не решает сам увеличить N и не выполняет RF/protocol analytics;
- после быстрого `sweep_start` сохрани `sweep_id`, initial cursor, advertised `max_window` и retention;
- держи pending `sweep_observe` long-poll для реактивного progress/terminal state;
- sweep cursor отдельный от session `observe.cursors`;
- запрашиваемый window может быть больше server maximum — сервер вернёт не больше advertised `max_window`;
- если `response.cursor < head_cursor`, сразу вычитай retained backlog следующими окнами;
- `sweep_cursor_expired` означает явную потерю части RAM event history; не скрывай этот gap;
- `state=failed` внутри успешного `sweep_observe` — failure самого job, а не JSONL request failure; если есть и primary, и cleanup failure, они приходят отдельно как `failure` и `cleanup_failure`;
- `sweep_cancel` только запрашивает отмену; terminal `cancelled/failed` подтверждай через `sweep_observe`;
- после terminal state вызови `sweep_close`, когда больше не нужна retained RAM history.

Во время active sweep participating sessions mutation-owned. Не пытайся параллельно делать на них обычные `send_line`, `send_bytes` или `close`: это должно вернуть `session_busy`. Read-only `status`/обычный `observe` остаются допустимы.

Generic ownership не изолирует физический эфир. Неучаствующие sessions/processes/devices generic API не блокирует; project-specific executor обязан держать другие влияющие на эксперимент передатчики quiet.

Для `chatter.reliable_user` sweep mode живёт в SerialTerminal: после host TX fence adapter через существующие команды делает `/cancel all`, выключает diag/heartbeat/echo-loop/manual echo и включает `BOTH`, а generic ownership блокирует конкурирующие external mutations на participating sessions. Никакого firmware `/sweep on|off` prerequisite нет. Третья нода на той же частоте всё ещё может загрязнить эксперимент — frequency/environment isolation остаётся задачей executor/coordinator. Cancel path использует `/cancel all` и отдельный bounded cancel budget.

### Execution vs analysis

Sweep events — только mechanical execution progress:

```text
coordinate/sample lifecycle
repetition
terminal job state
```

Не превращай их в:

```text
ACK quality
CRC/HDR anomaly
retry quality
CLEAN/DEGRADED
```

Controller adapter может читать protocol lines, чтобы определить operational settlement и не менять PHY посреди активной операции. Это synchronization, не measurement analysis.

После sweep consuming project skill/reviewer может читать обычный forensic log и анализировать protocol/RF evidence по своим правилам. `[SWEEP] event_seq` в forensic `.log` коррелирует с `sweep_observe.events[].seq` и остаётся после `sweep_close`.

Для bundled `chatter.reliable_user` adapter не делай вручную конкурирующие radio/config commands. Adapter сам приводит participating sessions в quiet diagnostic baseline существующими Chatter-командами, применяет/проверяет coordinate и сериализует reliable USER samples. Его конкретные plan fields/limits смотри в `AGENT_API.md`; interpretation ACK/retry/CRC/RSSI/SNR остаётся в LoRa-Chatter consuming skill.

## File transfer

Для bundled `chatter` file transfer является profile capability поверх BINARY USER.
Не реализуй file transfer вручную через `send_line("/bin ...")`.

Используй:

```text
file_send_start
file_transfer_observe
file_transfer_cancel
file_transfer_close
```

`file_send_start` принимает уже открытую session и локальный path, быстро возвращает
`transfer_id`, затем работа идёт в background. `file_transfer_observe` — pending
long-poll с собственным cursor и structured progress; он не блокирует обычный
`status`/session `observe`.

Не считай `percentage=100` или `completed` по последнему отправленному DATA.
Sender completed только после remote verified `RESULT OK`. Receiver completed только
после проверки stream/original SHA и atomic final save.

Во время active transfer session mutation-owned: не делай на ней параллельный
`send_line`, `send_bytes`, `close` или sweep start. Read-only status/observe
допустимы.

Для `chatter` file transfer не использует TELEMETRY как control plane и вообще не
меняет human-console mode. Не жди `DELIVERY ACK` на каждый DATA: локальный
`send_binary()` использует exact `> [BINARY]` как controller backpressure, а remote
truth принадлежит FT1 MISSING/RESULT. В TELEMETRY-only режиме без BINARY presentation
transfer должен явно завершиться capability error, а не переключать `/both`.
Если mode ещё неизвестен, Chatter profile сам делает read-only `/help` preflight.
Controller reboot без physical disconnect считается отдельной epoch: replay допустим
только после нового `CHATTER READY`.

FT1 v1 умеет in-process repair после временного local USB/BLE/SPP reconnect. Receiver
сохраняет transfer state в памяти, после END может выдать один structured MISSING с
диапазонами, sender досылает только указанные DATA и повторяет END. Следи за состояниями `waiting_result`, `repair_requested`, `repairing` и при
необходимости за событиями `missing_detected`, `repair_requested`,
`repair_round_sent`, `control_replay`.

Для быстрого file transfer **не пытайся сопровождать каждый DATA chunk отдельным
model/tool turn** и не вычитывай `file_transfer_observe.events` окно за окном в темпе
передачи. Такой orchestration не успевает за потоком, может получить
`file_cursor_expired` и на практике резко снижает полезную скорость сценария.
Обычный progress контролируй coarse-grained snapshot-ами `status` примерно раз в
2–5 секунд: `state`, `chunks_completed`, `bytes_completed`, `percentage` и
`failure`. `file_transfer_observe` используй для bounded long-poll/редких lifecycle
или fault events, когда они действительно нужны, а не как обязательный per-chunk
control loop. Детальную последовательность chunk/send-stage событий после прогона
бери targeted search из finalized forensic log; не загружай весь chunk backlog в
контекст модели во время активной передачи.

Generic `tx_state=unknown` по-прежнему нельзя blind-retry через обычный
`send_line`. File layer сам может повторить тот же idempotent FT1 message. Если
получен `repair_too_large`, текущий transfer terminal-failed: для полной повторной
передачи явно запускай новый `file_send_start`, не делай MISSING pagination и не
создавай бесконечный restart loop.

Если incoming transfer больше 120 секунд не получает META/DATA/END, он завершается
`remote_sender_timeout` и освобождает session. После restart самого SerialTerminal
persistent resume нет: начинай новый transfer.
LoRa SACK в этот contract не входит.

## Два уровня receive evidence

```text
firmware/protocol reasoning   -> result.lines
transport/chunk forensics     -> result.events / data_b64
```

`result.events` при `include_events:true` сохраняет raw session event truth: `seq`, state/TX metadata, stream, chunk boundaries, decoded chunk text и exact bytes через `data_b64`. Persisted forensic `.log` по умолчанию заменяет `data_b64` на `<base64>`; raw base64 на диск разрешается только явным process flag `--log-base64`. API response при этом остаётся exact и не зависит от logging flag.

`result.lines` содержит только завершённые LF-terminated lines. Line assembly выполняется один раз на session layer независимо для каждого stream.

## TX semantics

`send_line`/`send_bytes` с `state=queued` означает только принятие reconnect-safe TX queue.

`tx_state=written` означает успешное завершение transport `write()`. Это не доказательство peer delivery, firmware acceptance или выполнения higher-level operation.

`tx_state=unknown` означает, что transport side effect неоднозначен. Для BLE это включает GATT write timeout и failure fragmented write после того, как хотя бы один write-without-response ATT chunk уже завершился: backend/peripheral side effect нельзя безопасно считать отсутствующим. SerialTerminal **не** выполняет automatic retry такого TX, чтобы не создавать потенциальный duplicate side effect.

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


## Exclusive serial ownership

Не открывай один и тот же tty одновременно из двух процессов SerialTerminal. На POSIX
transport запрашивает exclusive ownership; второй процесс остаётся reconnecting и
получает `connect-failed` с `serial device busy: <path>` до освобождения порта.
