---
name: serialterminal-agent
description: Работа с machine-facing SerialTerminal JSONL agent API для discovery, sessions, send/observe, high-level file transfers и long-running sweep jobs.
---

# SerialTerminal agent

Это repo-local operational skill для `serialterminal agent`.

## Сначала прочитай API contract

Полный и канонический общий JSONL contract находится в [AGENT_API.md](../../../AGENT_API.md).

Для controller recovery и FT1 persistent resume authoritative current contract находится в [FT1_RESUME.md](../../../FT1_RESUME.md). Он supersedes старые утверждения в длинных file-transfer разделах, где process restart ещё описан как non-resumable.

Не переопределяй здесь schema, error codes или transport/session semantics. Если речь не о FT1 recovery/resume, источником истины остаётся `AGENT_API.md`; для TODO_034–037 recovery/resume используй `FT1_RESUME.md`.

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
10. после terminal file transfer освободи retained runtime state через `file_transfer_close`, когда он больше не нужен; не удаляй durable resume state вручную как recovery action;
11. после terminal sweep освободи retained job через `sweep_close`;
12. закрыть sessions через `close`; EOF agent process закроет оставшиеся.

Переиспользуй один agent process и уже открытые sessions. Для большой автономной проверки предпочитай один длинный сценарный проход с явными phases/checkpoints вместо десятков одинаковых `discover/open/close` циклов.

## BLE shutdown

При `close` BLE session проверь optional `transport_release.result`: только
`disconnected` подтверждает освобождение backend на момент проверки; локальный
`state:closed` сам по себе этого не доказывает. Для BlueZ проверяется Device1,
для других backend явно указан `backend:bleak` и состояние клиента. При EOF итог
остаётся в forensic/timing/application logs; `failed`/`unknown` не считать PASS
освобождения даже при exit 0. Discovery ничего не отключает. Явный `open` BLE
кандидата с `busy:true` сначала адресно отключает выбранный BlueZ Device1 и
проверяет освобождение, затем выполняет обычный connect. Это затронет и другое
приложение, использующее ту же ноду; остальные адреса не отключаются.

## Discovery

Прототип BLE discovery показывает все scan results плюс подключённые BlueZ
устройства, даже без advertising. Последние имеют `busy:true` и ` (busy)` в label;
JSON не содержит ANSI. Видимость не доказывает NUS capability. PID registry и
автоматического определения осиротевших соединений нет. Если release при `open`
не подтверждён, session остаётся reconnecting с `connect-failed`; обычный connect
не начинается. После подтверждённого release дальнейший reconnect не повторяет
takeover по старому discovery snapshot.

Transient UNKNOWN probe не означает NO и не должен заставлять scenario считать ранее подтверждённый target неподдерживаемым. Definitive probe result остаётся authoritative.

Human `--profile chatter` фильтрует BLE chooser по advertised/confirmed NUS,
включая F2 после смены профиля. JSONL `discover` сохраняет all-device список;
`profile` в `open` выбирает поведение session, а не фильтр discovery.

Human Chatter TUI отдельно делает до 3 повторных USB `/id` при отсутствии
canonical NODE, с интервалом 1 s. Это не поведение JSONL `open`; не считать
успешный preamble write доказательством полученной canonical identity.

Если target отсутствует, используй Bluetooth capability scanner/prober и повтори `discover`. После discovery открывай возвращённый `device_key`; не используй BLE name aliases.

Для Serial явный `baud` в `discover` сохраняется как override. Если его нет,
`open` разрешает baud по выбранному профилю: generic 115200, chatter 921600.
BLE/native SPP UART baud не используют. Не подставляй универсальный Chatter baud
в discovery для sessions с разными профилями.

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

`chatter.reliable_user` DEPRECATED: `sweep_start` возвращает `deprecated_sweep_adapter` до firmware commands и ownership. Старый echo/echo-loop preflight несовместим с текущей firmware; не обходи guard ручным созданием legacy class. Замены пока нет; generic sweep API остаётся для зарегистрированных поддерживаемых adapters.

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

Старый bundled `chatter.reliable_user` использовать нельзя. Для новых USER-прогонов нужен отдельный согласованный сценарий через актуальный ST JSONL; deprecated adapter не является его заменой.

## File transfer

Chatter profile сам согласует защищённый `/m1` interface: CRC, epoch/request, window=2,
LINK_OK по existing RF ACK. ACCEPTED/TX_DONE не означают delivery. Это profile-owned
деталь, агент продолжает использовать только high-level file API. Machine path не
зависит от human output mode; legacy `/bin` выбирается только после явного отказа
старой прошивки. Silence/UNKNOWN не разрешают fallback или blind replay. Для forensic
capture машинных bytes запускай ST с `--log-base64`; default logs их редактируют.


Для bundled `chatter` file transfer является profile capability поверх BINARY USER. Не реализуй file transfer вручную через `send_line("/bin ...")`, base64 или собственный chunk loop.

Используй только:

```text
file_send_start
file_transfer_observe
file_transfer_cancel
file_transfer_close
```

`file_send_start` принимает уже открытую session и локальный path, быстро возвращает `transfer_id`, затем работа идёт в background. Это же operation является явным trigger для same-process и persistent resume после failed attempt (прежний worker должен закончить settling): если существует ровно один валидный journal того же неизменившегося source, manager переиспользует тот же `transfer_id`, а initial result может содержать `resumed:true`. SerialTerminal **не** запускает старые transfer автоматически при старте процесса.

До admission/preparation `file_send_start` проверяет basename целиком в UTF-8:
при превышении META budget возвращает `filename_too_long` с `filename_bytes` и
`max_filename_bytes` (Chatter сейчас 162 bytes с extension), без новой передачи
или silent rename. `progress.elapsed` доступен и во время работы, после terminal
фиксируется; это время текущей runtime attempt, не всей истории durable resume.

Если matching sender journals несколько, операция должна вернуть `ambiguous_resume_state`. Не выбирай journal сам и не удаляй `.serialterminal-state`/`.part`, чтобы "починить" ситуацию. Если source изменился, old transfer_id не должен использоваться для новых bytes; manager начинает новую identity по текущему contract.

`file_transfer_observe` — pending long-poll с собственным cursor и structured progress; он не блокирует обычный `status`/session `observe`. `status` Chatter session также может содержать structured `controller` lifecycle snapshot.

Не считай `percentage=100` или последний DATA доказательством completion. Sender completed только после remote verified `RESULT OK`. Receiver completed только после проверки wire/original SHA и atomic final publication.

Во время active transfer session mutation-owned: не делай на ней параллельный `send_line`, `send_bytes`, `close` или sweep start. Read-only status/observe допустимы.

Protected Chatter machine path восстанавливает потерянный локальный outcome через cached QUERY той же epoch/request. Full-credit STATUS или результат позднего pending ticket — только повод QUERY; они не подтверждают успех раннего ticket. Потеря ACCEPTED/TX_DONE не отключает recovery; UNKNOWN блокирует новую submission, RF SUBMIT автоматически не повторяется. Полный contract — AGENT_API.md.

FT1 не использует TELEMETRY как control plane и не меняет human-console output mode. Не жди диагностический `DELIVERY ACK` на каждый DATA: protected machine path использует correlated epoch/request outcomes независимо от human presentation; remote truth принадлежит FT1 RESUME/RESULT и repair. В explicit legacy fallback local `send_binary()` использует exact `> [BINARY]` как controller-local backpressure. Только этот fallback в TELEMETRY-only режиме без BINARY presentation завершается capability error и не переключает `/both`; если mode неизвестен, legacy adapter делает read-only `/help` preflight.

Terminal `machine_link_failed` одного DATA не обрывает файл: M1 ticket освобождён,
ST пишет `binary_send_link_failed` и продолжает до END. Это относится к ROOT,
DATA списков дыр и досылке. Немедленного RF replay из ST нет: реальные пропуски
запрашивает peer через final recursive repair. Потерянный ACK возможен и при
доставленном DATA; completion доказывается только RESULT OK и SHA.
META/END/control LINK_FAIL, REJECTED/UNAVAILABLE и UNKNOWN этим исключением
не покрываются. Progress отражает обработанный поток DATA, включая link failure,
а не доказанное сохранение всех chunks.

После временного отказа local HELLO (например, прежний owner ещё завершает
RF после отмены) client повторяет только согласование, в bounded deadline.
Idle receiver восстанавливается без file_send_start; новая file operation тоже
может запустить HELLO. Pending/UNKNOWN и несовместимый WELCOME не обходятся,
RF SUBMIT автоматически не повторяется. События machine_negotiation_failed и
machine_negotiation_retry позволяют отделить это ожидание от radio DATA loss.

### Controller reboot / same-process recovery

Controller lifetime отделён от transport generation. USB tty может остаться открытым во время reboot. Chatter adapter распознаёт controller reset/READY и не превращает обычный transport reconnect без reset evidence в фиктивный reboot.

Для active FT1 recoverable local outcomes (`local_tx_unknown`, `local_disconnect`, `local_controller_reset`) приводят transfer в `recovering_local_node`. File layer сохраняет exact current idempotent META/DATA/END, не выпускает следующие chunks и после восстановления controller может повторить только текущий message при учтённом исходе прежней submission. Lost echo или unresolved pipeline tickets дают `local_tx_unsettled`: reconnect/host drain недостаточны, нужен наблюдаемый controller reset. Recovery bounded общим deadline; endless replay/hang недопустим.

Generic `tx_state=unknown` по-прежнему нельзя blind-retry через обычный `send_line`; recovery authority здесь существует только потому, что FT1 message identity/idempotence определены приложением.

Явный `RESULT(ok=false, code="cancelled")` симметрично отменяет ROOT и descendants
на peer без ответного cancel loop; неизвестный/terminal ID игнорируется.
`transfer_cancelled` может содержать `cancelled_by_peer` для происхождения отмены.
Остальной отрицательный RESULT прерывает cancellation-aware binary send/readiness и
pipeline waits. Это `remote_failed`, не operator cancel: sender journal остаётся.
При cleanup/drain error исходный remote code сохраняется, а неопределённый drain
удерживает lease до session close. Backend, игнорирующий stop signal, сохраняет
свои ограничения на blocking call.

Terminal remote integrity/quarantine/invalid_metadata errors переводят sender
journal в terminal: следующая explicit отправка получает новый ID. Timeout/restart
сохраняют same-ID resume. RX restore rollback предшествует release; неудачный
rollback удерживает ownership. Concurrent итоговые файлы с одним basename
сохраняются под разными именами, publishing intent резервирует имя до tombstone.

### Persistent receiver state

Receiver durable state хранится под configured receive directory:

```text
<receive_dir>/.serialterminal-state/
```

EOF agent закрывает FT manager через suspension и сохраняет partial/journal для same-transfer resume; это не `file_transfer_cancel`. Явный cancel удаляет receiver partial state. При проверке сохранения нужны и manifest, и существующий `.part`.

Chatter получает radio-dependent deadlines из проверенного `/config` + `/radio read config` и LoRa ToA/ACK/retry, а не из фиксированных SF7 таймаутов. `radio_timing_unavailable` требует разобраться с отсутствующим или расходящимся readback; не обходи его ручным `/bin`. `timeout_ms` у observe — только long-poll, не предел длительности файла. У ROOT нет общего часового deadline; idle/control/drain используют бюджеты profile. При local boot control/idle могут оцениваться по последнему проверенному PHY; RF admission всё равно ждёт READY и fresh readback. После failed ROOT перед явным resume дождись settlement обеих сторон: поздний RESULT ещё активного remote child может совпасть с новой попыткой того же ROOT ID.

Receiver timeout может оставить durable suspended partial и освободить runtime ownership. Не интерпретируй `remote_sender_timeout` как обязательное удаление partial state. Durable received ranges, а не размер `.part`, являются доказательством того, какие chunks можно пропустить после restart.

При matching META и корректном receiving/suspended manifest без `.part` receiver
сам сбрасывает durable/runtime proof до нуля и отвечает `RESUME 0` с тем же ID.
Событие `resume_state_reset` содержит reason=missing_partial, previous_chunks и
next_chunk=0. Ручная чистка journals не нужна. Это не разрешает сбрасывать
существующие partial, publishing/quarantined state, чужой owner или unsafe paths.

Не удаляй `.part`/manifest вручную во время recovery. Completed tombstone позволяет повторно подтвердить уже опубликованный transfer после потерянного RESULT без создания duplicate final file.

### Persistent sender / RESUME

При restart sender journal revalidated по content identity; deterministic gzip rebuild дополнительно проверяется по wire identity. Sender после META получает FT1 `RESUME_FROM` (wire message type 6) с earliest receiver-proven missing chunk. Только этот receiver-proven cursor разрешает пропустить prefix.

Нормальный persistent flow:

```text
file_send_start(path)
-> same transfer_id if valid journal matches
-> META
<- RESUME_FROM N
-> DATA N...
-> END
<- полный missing-list служебным файлом, если остались holes
-> selective DATA repair + END
<- RESULT OK
```

`RESUME_FROM` — coarse earliest-missing cursor, а существующий `MISSING` остаётся exact final selective repair. Это не firmware ACK и не LoRa SACK. Per-DATA FT1 ACK нет.

LIST META несёт previous_repair_id и отвечает на последний END родителя. Replay
cache хранит одну последнюю child META; старый LIST после eviction не запускает
repair. У родителя один queued verified request; число полезных циклов не ограничено.

Текущий recursive coordinator использует FT1 v3: оба ST endpoint должны обновляться вместе. Совместимость wire с v1/v2 не требуется. RESUME ожидание остаётся bounded. Invalid resume cursor за `chunk_count` считается protocol failure.

Следи за состояниями/событиями вроде:

```text
recovering_local_node
resuming
sender_resume_journal_restored
remote_resume
resume_started
resume_handshake_fallback
resume_state_restored
transfer_suspended
local_recovery_started
local_recovery_resumed
```

DATA неверной длины даёт `chunk_rejected` (`chunk_index`, `reason=length_mismatch`,
`actual_length`, `expected_length`), сохраняя partial file и корректные чанки.
Не отменяй transfer из-за этого события: после END существующий MISSING/repair
запросит отсутствующий блок. Повреждённый дубликат не удаляет сохранённую копию.
Финальная проверка SHA-256 обязательна; `chunk_rejected` не означает delivery PASS.

### Monitoring

Для быстрого file transfer **не пытайся сопровождать каждый DATA chunk отдельным model/tool turn** и не вычитывай `file_transfer_observe.events` окно за окном в темпе передачи. Такой orchestration не успевает за потоком, может получить `file_cursor_expired` и резко снижает полезную скорость сценария.

Обычный progress контролируй coarse-grained snapshot-ами `status` примерно раз в 2–5 секунд: `state`, `chunks_completed`, `bytes_completed`, `percentage`, `failure`, а при Chatter recovery — также controller state. `file_transfer_observe` используй для bounded lifecycle/fault observation, не как обязательный per-chunk control loop. Детальную последовательность после прогона бери targeted search из finalized forensic log.

В recursive coordinator полный список передаётся внутренним FT1 файлом; старый compact MISSING отвергается. ROOT default30%, служебные файлы exempt; depths1..8, три завершённых no-progress cycles на файл. Parent waits приостановлены на время child. Не запускай ручную досылку и не считай служебный RESULT OK завершением ROOT. Snapshots могут содержать repair={missing_total,depth,no_progress}. Нет overall часового deadline; idle control/transport recovery bounded. После process restart стек не восстанавливается автоматически, используется явный ROOT resume. Persistent resume после process restart теперь поддерживается по `FT1_RESUME.md`, поэтому не начинай безусловно новый transfer с нуля и не меняй transfer_id вручную.

Полный current recovery/resume contract, durability guarantees и physical-validation boundary — в `FT1_RESUME.md`. LoRa SACK в этот contract не входит.

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

Для serial partial/invalid write, backend write exception и flush error после
записи также дают `unknown`. Только явно возвращённые ноль bytes доказывают отсутствие
записи и допускают generic retry. При остановке session ещё не начатый TX получает
`cancelled`; оставшийся in-flight TX — `unknown`. `worker-failed` прекращает admission
и завершает pending TX; `notifier-failed` сообщает отказ callback без повторной записи.

FT1 освобождает ownership после учёта собственных host writes. При
`local_tx_drain_timeout` ownership сохраняется: закрой session перед новой работой.
Этот drain не доказывает завершение firmware queue или RF delivery.

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
- finalized ST-логи анализируй Python-скриптом `scripts/analyze_file_transfer.py`; в контекст получай сводки, не сырые записи;
- при уже явно обнаруженном отказе/баге/ошибке используй ограниченный `--excerpt-at <ISO-время-с-timezone>` с `--before`/`--after`, при необходимости `--excerpt-log application` и явным `--show-excerpt`; не собирай полный лог последовательными фрагментами. Подробности лимитов и provenance — `LOGGING.md`.

Firmware-specific команды, RSSI/SNR/Q, radio collision rules, reboot/cancel semantics и acceptance criteria остаются в project-specific skill, а не здесь.

## Exclusive serial ownership

Не открывай один и тот же tty одновременно из двух процессов SerialTerminal. На POSIX transport запрашивает exclusive ownership; второй процесс остаётся reconnecting и получает `connect-failed` с `serial device busy: <path>` до освобождения порта.

## Application errors and incremental timing

При `--log /path/test.log` CLI создаёт рядом все четыре файла: `test.log`,
`test.console.log`, `test.fttiming.jsonl` и `test.application.log`. Без `--log`
application log использует `logs/serialterminal-application-<timestamp>-p<pid>.log`
относительно рабочего каталога. Traceback ошибки записывается сразу, с flush/fsync. Не путай его с транспортным
`.log`. Ошибка не должна нарушать JSONL stdout. TUI показывает красную ERROR плашку;
Ctrl+C завершает работу без traceback в терминал. Timing `.fttiming.jsonl` пишется
пачками256 отдельным writer (очередь максимум8), close дописывает остаток. После
SIGKILL ранее flushed данные остаются, незаписанный хвост может отсутствовать;
не считай такой trace полным. Writer failure виден в app log. Подробности в AGENT_API.md.

FT1 host metadata по умолчанию ограничены65 536 received ranges и manifest4 МиБ;
LIST — максимум65 537 ranges. Последовательный файл не хранит запись на каждый
chunk. Превышение range budget сохраняет полезный partial и даёт storage_failed;
не считать такой отказ успешным completion и не удалять partial вручную.

Служебные partial очищаются циклически во время работы: старые неактивные `.part`
и manifests уступают место новым при byte/free-space pressure. ENOSPC/EDQUOT
повторяется только после фактической eviction; активные owners других процессов
и итоговые файлы защищены. Если освободить нечего — storage_failed с последним
пригодным partial/proof. Defaults:7 суток, incoming32/outgoing32/completed64,1 GiB
partial на receive_dir. Это не `/clean` и не удаление готовых пользовательских файлов.

META с derived chunk_count выше0xffffffff отвергается до RX admission через
invalid_metadata; sender проверяет подготовленный wire до journal/META. Последний
DATA index при максимальном числе chunks —0xfffffffe. Это wire bound, отдельно
от host RAM/storage budgets; не создавать большие тестовые файлы для этой границы.

Outgoing journals/leases изолированы по выбранному device_key: agent передаёт key
из open, TUI — key выбранного transport. Для двух фиксированных радионод это
привязка к локальной ноде, не discovery удалённого RF peer. Same-key restart
сохраняет ID; разные USB/BLE keys и старые unbound journals не объединяются.
Anonymous library manager без peer_key имеет только volatile instance binding.
Не менять identity вручную ради resume и не удалять чужой journal при cancel.

Timing correlation key — `(segment_id, seq)`: новый UUID segment_id на экземпляр
trace/session replacement, seq локален segment. Append сохраняет прежние rows;
legacy без segment_id не имеет этой гарантии. Оборванный fragment сохраняется
отдельной строкой и считается evidence gap, последующие JSON rows читаются
независимо. Batches сериализуются до flush между POSIX writers; подробности
reopen/concurrency/clock semantics и incremental writer находятся в LOGGING.md.

Без flock/pread остаётся single-writer path; межпроцессная сериализация batch
гарантируется на POSIX. Это не требует POSIX-модуля для импорта generic terminal.
