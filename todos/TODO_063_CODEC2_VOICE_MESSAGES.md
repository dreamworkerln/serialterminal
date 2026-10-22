# Codec2 voice messages поверх существующего FT1

TODO-ID: TODO_063
Status: IMPLEMENTED / LOCAL SOFTWARE VALIDATION PASS / CLEAN-ENV CI REQUIRED / REAL INTEGRATION OPEN
Priority: P2
Corrective task: [TODO_064](TODO_064_CODEC2_VOICE_LIFECYCLE_FIXES.md) tracks REVIEW_006/F001–F005; F003 stop correction awaits operator retest; full real-audio/radio acceptance remains here.
Created: 2026-10-21
Planning checkpoint: `dev_tui_exp_recursive_missing@184fabfb8088b5b3568a26883c0a71159468864e`.
Plan revision: 2026-10-21 по [REVIEW_005](../reviews/REVIEW_005_CODEC2_VOICE_FILE_INTEGRATION.md), findings F001–F003.
Implementation checkpoint base: `dev_tui_exp_recursive_missing@989118042f2c4030bcde8bc328540ac67e14faed`; source implementation complete, clean-environment CI and real audio/radio validation remain separate gates.
Codec2 SDK dependency checkpoint: `codec2-sdk/dev@5ef71a1a0aee504752090015a114d9f24f52ef53`, pinned upstream Codec2 `310777b1c6f1af0bc7c72f5b32f80f6fd9136962` (Codec2 1.2.0).

## Purpose

Добавить в human TUI первый store-and-forward voice-message workflow без нового
радиопротокола: микрофон кодируется Codec2 прямо во время записи, результат остаётся
обычным стандартным `.c2` файлом, а доставка выполняется уже существующим FT1.
После verified RX completion SerialTerminal распознаёт voice message и проигрывает
его локально.

Первый этап должен проверить весь application path:

```text
TX: F12 -> mic -> PCM S16_LE mono 8 kHz -> Codec2 3200 -> *.stvoice.c2
    -> existing FileTransferManager / FT1 -> existing BINARY USER transport

RX: existing FT1 -> verified durable final_path -> voice recognizer
    -> Codec2 decode -> PCM S16_LE mono 8 kHz -> speaker
```

Голосовое сообщение здесь — обычный файл FT1. Encoding во время записи не означает
передачу во время записи: FT1 получает только завершённый `.c2`. В scope нет отдельного
режима радио, voice packets, voice ACK/retry/resume или realtime transport.

## Current architecture / facts at planning checkpoint

* Generic `TerminalTui` создаёт `FileTransferManager` только когда выбранный profile
  предоставляет `make_binary_user_transport(...)`; generic frontend не должен знать
  concrete profile name.
* F5 вызывает обычный `FileTransferManager.start_send(path)`. F7 и Esc/F6 принадлежат
  существующему lifecycle FT1; F10 зарезервирован terminal emulator-ом; F12 сейчас
  не назначен.
* FT1 остаётся владельцем metadata/chunks/compression/hash/repair/resume/result и
  durable publication. У RX terminal snapshot/event есть `final_path` только после
  завершённой проверки и публикации файла.
* Event sink получает `transfer_completed` с исходным wire filename и `progress`.
  Финальный filesystem basename может быть uniquified (`name (1).c2`), поэтому
  voice recognition не должна зависеть от буквального имени `final_path`.
* `_log_file_transfer_event()` сейчас одновременно пишет forensic FT1 event и human
  lifecycle line. Playback не должен запускаться из функции с logging ownership.
* Runtime dependencies SerialTerminal сейчас не включают audio/Codec2 Python package.
  `codec2-sdk` отдельно предоставляет portable shared `libcodec2` и manifest; runtime
  integration должна использовать shared library напрямую через `ctypes`, а не
  `c2enc`/`c2dec` subprocess как основной codec API.
* `start_send()` не является полностью неблокирующим API: поиск resume source и
  claim синхронны; TUI TX fence допускает ожидание до 10 секунд. Sender worker может
  выдать terminal event до возврата `start_send()` и получения вызывающим TX-ID.
* Event sink — process-local уведомление, не durable audio inbox. Completed tombstone
  после restart отвечает на повторные META/END без нового `transfer_completed`.

## Target behavior

### Codec and file format

Первый поддерживаемый режим: **Codec2 3200**.

```text
sample rate       8000 Hz
PCM               signed 16-bit little-endian mono
samples/frame     160
frame duration    20 ms
bits/frame        64
bytes/frame       8
encoded payload   400 bytes/s
```

Voice file использует стандартный Codec2 `.c2` header и payload. Не создавать
собственный SerialTerminal container и не добавлять voice metadata в FT1 wire
format. Каноническое имя исходящего файла — короткое уникальное имя вида
`voice-<timestamp>-<nonce>.stvoice.c2`, укладывающееся в существующий FT1 filename
budget.

TX encoder пишет header сразу и затем append'ит 8-byte Codec2 frames по мере
поступления PCM. Полный PCM файл на диске не создаётся. Последний неполный PCM frame
при остановке детерминированно дополняется тишиной до 160 samples; это может добавить
не более одного 20-ms frame. Read fragments сначала собираются в PCM samples/frames;
padding применяется только один раз после завершения capture и drain, не к каждому
короткому read. Header-only запись без encoded frames не отправляется.

RX parser сначала проверяет стандартный `.c2` header/magic, version/mode/flags и
целостность frame body. В первом этапе проигрывается только поддерживаемый 3200 mode;
другой валидный Codec2 mode остаётся обычным принятым файлом с понятным diagnostic,
а не декодируется неправильной геометрией.

### SDK loading and provenance

Не использовать неявный distro `libcodec2.so` как default: это разрушит смысл
отдельного pinned `codec2-sdk`.

Добавить явную TUI/runtime настройку уровня human frontend, например
`--codec2-sdk-dir PATH`, указывающую на portable SDK tree с `manifest.json` и `lib/`.
Loader должен:

1. лениво загрузить SDK только при использовании voice feature;
2. проверить manifest/schema/platform и shared-library build;
3. для первоначальной интеграции подтвердить pinned upstream commit
   `310777b1c6f1af0bc7c72f5b32f80f6fd9136962`;
4. найти library только внутри явно заданного SDK tree;
5. выдать user-visible unavailable/error без падения обычного terminal startup.

Exact `codec2-sdk` GDI commit выше является integration checkpoint этого плана.
Runtime не vendor'ит Codec2 source и не собирает upstream внутри SerialTerminal.

### Python codec boundary

Добавить небольшой application/backend слой, без raw `ctypes` pointer leakage в TUI:

```text
Codec2Library
  load/sdk provenance
  create(mode) -> Codec2Codec

Codec2Codec
  samples_per_frame
  bits_per_frame
  bytes_per_frame
  encode(pcm_s16le) -> bytes
  decode(encoded) -> pcm_s16le
  close()
```

ABI binding использует публичные `codec2_create`, `codec2_destroy`, `codec2_encode`,
`codec2_decode`, `codec2_samples_per_frame`, `codec2_bits_per_frame` и
`codec2_bytes_per_frame`. Ownership `CODEC2*` должен быть exception-safe и idempotent
при close/shutdown.

`c2enc`/`c2dec` разрешены только как reference/interoperability validation, не как
основной runtime codec path.

### Audio boundary

Ввести отдельный `AudioBackend`, чтобы Codec2/voice state machine не зависели от
конкретного Linux process API.

Первый backend — Linux ALSA tools:

```text
capture:  arecord -> raw S16_LE / 8 kHz / mono stdout
playback: decoded raw S16_LE / 8 kHz / mono -> aplay stdin
```

Запускать argv напрямую, без shell. `shutil.which()` проверяет наличие tools.
Процессы должны иметь bounded stop/terminate/kill cleanup, не оставлять zombies и
не блокировать curses event loop. Штатный stop capture сначала останавливает источник
и дочитывает stdout до EOF в ограниченный срок; затем кодируется остаток и закрывается
`.c2`. Terminate/kill используются как fallback, а expected exit от нашего stop
отличается от самопроизвольного отказа процесса. При недоказанном корректном завершении
файл автоматически не отправляется.

Ошибки процесса идут в application log и краткий human diagnostic; raw PCM не пишется
в application/primary logs. Playback читает/decode-ит frames потоком, без полного PCM
файла или неограниченного PCM buffer в памяти. Audio device selection принадлежит
backend/frontend и не меняет radio profile; первый backend может использовать системный
default, а документация должна объяснять выбор input/output, в том числе Bluetooth.

Backend API должен позволять позднее заменить `arecord`/`aplay` на PortAudio,
miniaudio или platform-specific implementation без изменения Codec2/FT1 логики.
Новые обязательные Python audio dependencies в первом этапе не нужны.

### VoiceMessageService ownership

`TerminalTui` владеет отдельным application-level `VoiceMessageService` рядом с
`FileTransferManager`:

```text
TerminalTui
  +-- FileTransferManager
  +-- VoiceMessageService
        +-- AudioBackend
        +-- Codec2Library / Codec2Codec
        +-- existing FileTransferManager
```

Dependency direction остаётся:

```text
TUI/application -> voice service -> Codec2/audio + public FileTransferManager API
profile          -> existing BinaryUserTransport capability
FT1              -> profile-owned BinaryUserTransport
transport        X voice/Codec2 semantics
firmware         X voice/Codec2 semantics
```

Нельзя добавлять `if profile.name == "chatter"` в generic TUI. Voice capability
доступна, когда текущий frontend имеет FT1 manager/BINARY capability и настроенные
Codec2/audio backends. Generic profile без такой capability сохраняет прежнее
поведение.

### TUI trigger and state

Первый вариант — **F12 toggle**, не hold-to-talk. Curses не предоставляет надёжный
cross-terminal key-release contract, поэтому настоящий press/release PTT в этот TODO
не входит.

```text
IDLE
  F12 -> предварительная проверка FT1/audio -> RECORDING

RECORDING
  F12 -> FINALIZING -> готовый .c2 -> ADMITTING (worker: start_send(path))
                                       |
                                       +-> принято: обычный FT1 lifecycle/progress
                                       +-> отказ: READY_FILE (сохранён path; ручной retry)

shutdown / codec/audio failure
  -> bounded cleanup; partial удаляется, finalized/resumable file сохраняется
  -> незавершённый файл никогда не отправляется автоматически
```

READY_FILE — локальное состояние сохранённого файла, не отдельный режим передачи
или вторая очередь доставки. Повторная отправка выполняется обычным F5 с тем же path,
чтобы существующий FT1 мог использовать свой resume journal. F12 не запускает скрытый
retry: новая запись может начаться только после освобождения текущей local operation;
ранее сохранённые finalized files при этом не удаляются.

Ранняя проверка FT1 busy не резервирует manager: пока идёт запись, входящий FT1
остаётся разрешён. Если он занял manager до stop/send, READY_FILE сохраняет запись
и показывает причину отказа и path. Capture/SDK initialization failure и отказ admission
после готовой записи — разные исходы.

Во время RECORDING/FINALIZING/ADMITTING:

* F2 device changes, F3 profile changes и F5 arbitrary file send блокируются;
* controller actions, которые profile классифицирует disruptive, также блокируются;
* viewing/scroll/clear/help/mouse и profile-classified non-disruptive actions остаются;
* после передачи ownership полностью переходит обычному FT1, и действуют его уже
  существующие F6/Esc/F7 правила;
* Ctrl+C/Ctrl+Q остаются надёжным выходом: capture/playback workers завершаются
  bounded cleanup, никакой implicit send на shutdown нет.

Footer/help показывает F12 Voice только когда feature применима; обычный generic
terminal не получает ложную доступность. Во время записи достаточно компактного
`VOICE REC <duration> · F12 send` status; отдельный второй progress overlay для
voice transfer не создавать — после stop используется существующее FT1 окно.

F10 остаётся без ST binding. Числовой предел длительности записи/локального playback
оператором пока не выбран. До реализации согласовать этот параметр и поведение при
его достижении; не вводить произвольный лимит или неявный auto-send. Этот открытый
пункт не требует нового TODO. Время radio delivery не обещается равным длительности
записи: 3200 mode даёт 400 payload bytes/s плюс header и FT1 overhead.

### Асинхронный переход к FT1 и lifetime (REVIEW_005/F002)

Blocking capture, stop/drain/finalize и вызов `start_send()` выполняются вне curses
thread. Voice state меняет один serialized owner; frontend handler только принимает
действие и показывает snapshot/status. Нельзя вызывать `start_send()` из FT1 callback.

До вызова `start_send()` service регистрирует pending operation с finalized path,
local job identity и конкретным manager/session lifetime. События коррелируются
с этим lifetime и TX-ID; ручной retry того же FT1 ID также различает local attempt
и старые event seq/cursors, чтобы запоздалый terminal не удалил файл новой попытки.

FT1 callback передаёт короткое событие в bounded dispatch без audio/decode/storage
работы и без ожидания voice worker. Ранний terminal event до return не теряется; после
возврата service связывает TX-ID и учитывает returned snapshot, который уже может быть
terminal. Event и snapshot применяются идемпотентно: cleanup/retention ровно один раз.
Нельзя молча терять terminal TX outcome при overflow: нужен явный diagnostic и
reconciliation через public manager snapshot/status до решения о судьбе temp.

Logging и voice delivery получают событие независимо, с изолированными exception
boundaries. Исключение logger не отключает voice observer и наоборот. Playback error
не меняет FT1 result. Нельзя использовать private recursive state как новый voice API.

Shutdown запрещает новые admission, останавливает capture/playback и учитывает уже
начатый `start_send()`: pending source нельзя удалить, пока callback/return/settlement
ещё способны подтвердить принятый TX. Late result прежнего manager не привязывается к
новой session. Уже принятый файл завершает/приостанавливает существующий FT1 по своему
контракту; finalized resumable source сохраняется. Незавершённый admission не превращает
Ctrl+C/Ctrl+Q в неограниченное ожидание и не оставляет неучтённый worker/file owner.

### TX temporary-file lifecycle

Использовать отдельный temp root, по умолчанию через system `tempfile` namespace
вроде `serialterminal-voice/`; при необходимости добавить `--voice-temp-dir`.
Не использовать receive directory как TX scratch.

* capture failure/truncated initialization удаляет незавершённый temp;
* с момента начала admission temp нельзя удалять до разрешения pending operation и,
  если TX принят, его terminal outcome; ранний terminal учитывается после привязки ID;
* отказ `start_send()` до появления TX-ID (busy, claim/fence/initialization error)
  сохраняет finalized `.c2`, показывает path и причину, возвращает READY_FILE;
  автоматического voice retry нет;
* успешный TX удаляет generated temp;
* failed/cancelled TX сохраняет finalized `.c2` и сообщает путь для диагностики/
  возможного ручного retry, вместо молчаливой потери записи;
* service shutdown закрывает handles/processes, удаляет незавершённый partial,
  сохраняет finalized/READY_FILE/resumable source и сообщает retained paths;
  partial никогда не выглядит как успешно сформированный voice message.

Ручной retry использует тот же finalized path/bytes, без переименования или повторного
encode. Успех старого TX не разрешает удалить файл, уже принадлежащий новой local
attempt; lifetime/identity проверяются перед cleanup.

### RX recognition and playback

Не встраивать autoplay в `_log_file_transfer_event()`.

TUI event sink должен иметь application-level dispatcher (или эквивалентный
отдельный completion observer): logging остаётся logging side effect, а voice service
получает terminal event отдельно. Ошибка playback не может изменить FT1 result.

Autoplay admission требует одновременно:

1. root `direction == "RX"`;
2. terminal `kind == "transfer_completed"`;
3. **исходный wire filename из event** соответствует `*.stvoice.c2`;
4. `progress.final_path` присутствует и остаётся внутри normal FT1 publication path;
5. файл открывается после durable FT1 completion;
6. standard Codec2 header/magic валиден и mode поддерживается.

Использование wire filename намеренно: FT1 collision-safe publication может назвать
файл на диске `voice-...stvoice (1).c2`, но семантика исходного сообщения при этом
не меняется. `final_path` используется только для открытия проверенного content.

Recursive service files, failed/cancelled transfers, 100% DATA до RESULT, invalid
magic/header, unsupported mode и обычные `.c2`/не-voice файлы не должны случайно
запускать playback. Они остаются обычными FT1 artifacts и дают bounded diagnostic.

Playback выполняется вне FT1 worker/event callback и вне curses redraw. Один
background playback worker сериализует сообщения; очередь должна быть bounded с
явным overflow policy, чтобы серия входящих файлов не создала неограниченный backlog.
Первый вариант при заполнении очереди отклоняет новую заявку на autoplay, сохраняет
полученный файл и выдаёт bounded diagnostic с path; предыдущие заявки не вытесняются,
FT1 completion остаётся успешным. Размер очереди — centralized backend setting,
а не новая FT1 wire настройка.

### Capture/playback admission (REVIEW_005/F003)

Локальные microphone capture и playback не работают одновременно. Во время
RECORDING/FINALIZING входящие verified voice files только ставятся в очередь;
playback начинается после освобождения audio owner. Начало записи блокирует запуск
очередного playback атомарно, не через несогласованные check-then-act проверки.

Если playback уже идёт, F12 не прерывает его и не начинает capture: TUI сообщает
«воспроизведение продолжается; повторите F12 после окончания». Эта консервативная
политика не требует нового управления radio/FT1. Во время ADMITTING микрофон уже
закрыт: локальный playback допустим, если audio owner свободен.

### Autoplay identity, повторное прослушивание и restart

Autoplay допускается не более одного раза для одного root receive completion в
текущем service/manager lifetime; duplicate/late events и reconciliation не создают
повторное воспроизведение. Корреляция учитывает manager/session, direction и transfer
identity, а не только basename. Ручной replay — отдельное явное действие пользователя.

Полученный `.c2` не удаляется после playback error, overflow или успешного прослушивания.
Показывать сохранённый path и документировать повторное локальное воспроизведение через
SDK `c2dec`/`aplay`; отдельный inbox/player UI в первом этапе не обязателен.

Гарантия durable FT1 delivery не означает exactly-once playback через process crash.
После restart не выполнять автосканирование старых файлов для autoplay и не считать
META/END tombstone replay новым audio event. При crash между публикацией и callback
файл может остаться непрослушанным; он доступен вручную. Durable played/unplayed inbox
в этот этап не входит. Reconnect в том же процессе до первого verified completion
сохраняет обычное правило однократного autoplay.

## Implementation plan

### Phase 1 — codec/file primitives

- [x] Добавить isolated Codec2 ctypes wrapper и standard `.c2` reader/writer.
- [x] Добавить explicit SDK-tree configuration/provenance validation без system-lib fallback.
- [x] Зафиксировать Codec2 3200 frame geometry через runtime ABI, не размножать размеры по TUI.
- [x] Добавить deterministic final PCM-frame padding и strict encoded-frame validation.

### Phase 2 — local audio backend

- [x] Определить `AudioBackend` protocol и Linux `arecord`/`aplay` implementation.
- [x] Сделать capture/playback streaming и bounded process/thread shutdown.
- [x] Отделить backend errors от FT1 correctness; не писать raw audio в logs.

### Phase 3 — VoiceMessageService

- [x] Реализовать capture/finalize/admission с явным READY_FILE при отказе старта FT1;
  сохранить finalized path и обычный F5 retry без отдельной delivery state machine.
- [x] Генерировать collision-resistant short `*.stvoice.c2` filename и temp lifecycle.
- [x] Зарегистрировать pending source до admission; связать local job/manager lifetime
  с TX-ID, учесть ранний terminal и returned terminal snapshot ровно один раз.
- [x] Выполнять blocking admission вне TUI; оградить shutdown и late manager results.
- [x] Сохранить failed/cancelled/READY_FILE/resumable source; success cleanup только
  для соответствующей local attempt, без удаления файла другого owner.
- [x] Реализовать RX terminal-event recognition, session-scoped deduplication,
  bounded playback queue и reject-new autoplay overflow с сохранением файла.
- [x] Сериализовать audio owner: playback ждёт capture/finalize; F12 во время playback
  сообщает busy; входящий FT1 продолжает обычную файловую доставку.
- [x] Сделать close/shutdown idempotent и безопасным при recording/playback/finalizing.

### Phase 4 — TUI integration

- [x] Добавить F12 toggle через canonical TUI action, без concrete-profile branch.
- [x] Добавить recording/finalizing/admitting guard для F2/F3/F5 и disruptive human actions.
- [x] Показать READY_FILE path/reason и возможность обычного ручного F5 retry.
- [x] Сохранить existing F4/F6/F7/F8/F9/F10/Ctrl+C/Ctrl+Q semantics.
- [x] Добавить capability-aware footer/help/status; не создавать второй transfer progress UI.
- [x] Разделить FT1 event dispatch и logging с независимыми exception boundaries;
  callback только enqueue, playback не живёт в log function; terminal outcome
  не теряется молча при bounded dispatch overflow.

### Phase 5 — configuration/docs

- [x] Протянуть explicit codec2 SDK directory через human CLI -> TUI; classic/agent APIs не менять без отдельного решения.
- [x] При необходимости добавить configurable voice temp directory через centralized settings/CLI ownership, без mutable globals.
- [x] Duration/bytes policy первого этапа: SerialTerminal не вводит произвольный
  числовой recording/playback cap и не делает timer/size auto-send. Запись заканчивается
  вторым F12 (либо error/shutdown); PCM и playback остаются streaming, а внутренние
  очереди/process cleanup имеют отдельные bounded resource/time limits.
- [x] Документировать retained paths, default/Bluetooth audio route и ручной local
  replay без повторной отправки файла; не обещать durable autoplay через restart.
- [x] Обновить README/INSTALL/ARCHITECTURE и коротко FILE_TRANSFER: voice является application consumer verified FT1 completion, не новым FT1 protocol.
- [x] По AGENTS.md отдельно проверить AGENT_API и `.agents/skills/serialterminal-agent/SKILL.md`; ожидаемое решение — JSONL schema не меняется в первом этапе.

## Validation / acceptance

### Automated

- [ ] Codec2 wrapper tests: load/provenance failures, ABI signatures, geometry,
  create/destroy ownership, encode/decode exact buffer sizes and invalid input.
- [ ] `.c2` tests: header roundtrip, truncated/invalid magic, unsupported mode,
  body not divisible by frame size, final-frame padding один раз после EOF,
  empty/header-only capture не отправляется.
- [ ] Reference interoperability against exact `codec2-sdk` checkpoint:
  ST-produced `.c2` decodes with SDK `c2dec`; SDK `c2enc` file is accepted/decoded
  by ST. Record SDK manifest and exact commit in evidence.
- [ ] AudioBackend tests with fake processes/streams: fragmented reads, process exit,
  stop during blocked read, graceful stdout/EOF drain, expected stop vs unexpected
  exit, stderr/error, bounded terminate/kill и отсутствие zombies.
- [ ] Voice service TX tests: start/stop/send, FT1 busy, codec/audio unavailable,
  start_send failure, success temp cleanup, failure/cancel retention, shutdown while recording.
- [ ] REVIEW_005/F001: входящий META во время capture -> stop -> FT1 busy -> сохранённый
  valid .c2/path; обычный F5 retry тем же source после освобождения manager.
- [ ] REVIEW_005/F002: claim delay не блокирует curses; terminal success/failure до
  start_send return; terminal returned snapshot + event не дублируют cleanup.
- [ ] REVIEW_005/F002: logger exception, dispatch overflow с reconciliation, shutdown
  во время admission, late event старого manager и stale terminal предыдущей local
  attempt того же resumed TX-ID не теряют/не удаляют чужой файл.
- [ ] Voice service RX tests: root verified RX exactly once; wire filename vs uniquified
  final_path; invalid header; unsupported mode; failed/cancelled transfer; recursive child;
  playback failure/overflow cannot change FT1 completion; published file остаётся.
- [ ] REVIEW_005/F003: RX completion during recording/finalizing ждёт audio owner; F12
  during playback не начинает capture; конкурентный старт не открывает оба backend.
- [ ] Duplicate completion/reconnect дают один autoplay в текущем lifetime; completed
  tombstone replay после restart не запускает autoplay; retained path пригоден для
  ручного replay после audio failure/overflow без повторного FT1 send.
- [ ] TUI unit + curses/PTY: F12 mapping/status, F2/F3/F5/disruptive guard during record,
  existing F6/F7/F8/F9 behavior, F10 remains unbound, Ctrl+C/Ctrl+Q shutdown,
  generic profile unchanged; READY_FILE diagnostic/F5 retry и playback busy status.
- [ ] Existing FT1/core/TUI regressions plus full `pytest -q`; compileall and changed-file
  Ruff according to AGENTS.md. Source tests run outside restrictive sandbox as required.

### Real integration

- [ ] Linux host with exact SDK tree + real `arecord`/`aplay`: record -> standard `.c2`
  -> local decode/play smoke; no full PCM temp file.
- [ ] Two SerialTerminal/Chatter endpoints: F12 record/stop, existing FT1 transfer,
  receiver waits for verified durable completion and auto-plays once.
- [ ] Проверить входящий voice файл во время записи: без звука в microphone capture,
  файл доставлен FT1, затем проигран локально. Проверить busy admission и ручной retry
  сохранённой записи без повторного encode.
- [ ] Repeat with FT1 repair/resume/reconnect: voice layer does not invent additional
  retry semantics and only plays after final verified ROOT completion.
- [ ] Measure recorded duration, encoded bytes and transfer time; 3200 mode should be
  approximately 400 encoded payload bytes/s plus 7-byte header and FT1 overhead.

TODO cannot become CLOSED from mock/unit tests alone: exact Codec2 SDK interoperability
and one real audio smoke are required. Paired radio/hardware validation is recorded
separately from software/host validation.

## Non-goals / deferred follow-up

Not part of TODO_063:

* realtime voice packets while the microphone is still active;
* hold-F12 key-release detection in curses;
* evdev/global-key PTT;
* jitter buffer, packet sequence/reordering, PLC/FEC or voice-specific radio scheduling;
* per-frame retransmission/SACK semantics for live speech;
* firmware changes or a new BINARY USER wire type;
* replacing FT1 reliable file delivery for store-and-forward messages;
* automatic system/distro Codec2 discovery;
* cross-platform audio backend beyond the abstraction needed for a later implementation;
* durable played/unplayed inbox, automatic replay после process crash и отдельная
  voice delivery/retry queue; это не требуется для передачи обычных `.c2` через FT1.

Realtime half-duplex should become a separate TODO after this store-and-forward path
proves Codec2/audio/UI ownership. It should reuse `Codec2Library`/`Codec2Codec` and
`AudioBackend`, but use a latency-oriented transport where late speech frames may be
dropped rather than retransmitted until reliable delivery.

## REVIEW_005 disposition — 2026-10-21

Все actionable findings остаются внутри TODO_063:

| Finding | Исправление плана | Обязательный validation |
| --- | --- | --- |
| F001 | READY_FILE, retention до admission, обычный F5 retry того же source | incoming FT1 during capture, admission failure, retained file + retry |
| F002 | worker admission, pending operation до вызова, early terminal/snapshot idempotence, lifetime/shutdown и isolated logging | ранний success/failure, delayed claim, overflow, stale manager/attempt, shutdown |
| F003 | audio owner исключает capture/playback overlap; deferred playback, F12 busy | RX during record, F12 during playback, concurrent audio admission |

Дополнительные замечания приняты как EOF/final-padding, streaming playback, overflow
retention, manual replay, restart boundary и явная открытая duration policy.
Отдельный TODO не создаётся: для текущего store-and-forward feature это одна задача.
Durable inbox/realtime не заведены в работу и не получили новые номера.

[REVIEW_005 contract probe](../reviews/evidence/REVIEW_005/probe-results.json)
подтверждает свойства существующего FT1 API, не реализацию voice feature. Исторический
RED verdict ревью сохраняется; изменение плана само по себе не является re-review или
доказательством исправленной runtime реализации.

## Implementation result — 2026-10-21

Store-and-forward voice implemented from base
`989118042f2c4030bcde8bc328540ac67e14faed` without firmware, FT1 wire or agent JSONL
schema changes. Runtime pieces are `voice_codec.py`, `voice_audio.py` and
`voice_service.py`; human CLI/TUI owns the explicit SDK/temp configuration and F12 UI.
REVIEW_005/F001–F003 are represented in runtime state/retention/admission/audio-owner
logic and regression tests. `AGENT_API.md` and the SerialTerminal agent skill were
reviewed: no machine API operation or schema change is required for this TUI-only layer.

Local isolated voice validation passes 15 tests covering codec/container, ALSA process
cleanup, admission retention/early terminal, capture/playback exclusion, stale-manager
protection, shutdown during blocked admission, invalid/recursive RX and autoplay dedup.
`python3 -m compileall -q src serialterminal.py tools` passes. The broader TUI/CLI suite
cannot be collected in this stripped local checkout because `pyserial` is not installed;
clean-environment GDI CI remains required and is not replaced by that local limitation.
Exact built-SDK interoperability and real `arecord`/`aplay` smoke remain OPEN, therefore
this TODO is IMPLEMENTED but not CLOSED. Paired radio validation remains OPEN separately.

## Corrective lifecycle validation — 2026-10-22

[REVIEW_006](../reviews/REVIEW_006_CODEC2_VOICE_IMPLEMENTATION.md) found five defects
at 8a9d91d. Operator requested a separate corrective TODO and fixes:
[TODO_064](TODO_064_CODEC2_VOICE_LIFECYCLE_FIXES.md). Its initial software validation
(before the host arecord status-1 regression) used BASE 8a9d91d + saved patch:
independent capture/TX ownership, startup audio
exclusion, stop classification, RX generation barrier and child cleanup.
The same 20 regression cases: old snapshot 17 FAIL / 3 PASS, fixed source 20 PASS;
full local pytest 1415 PASS, compile/Ruff PASS. Review verdict stays historical RED.
Actual SDK interoperability was confirmed by REVIEW_006 on unchanged voice_codec;
real microphone/speaker and paired-radio acceptance, server CI and release remain
separate OPEN gates. TODO_063 is not CLOSED by these software results.

### Host F12 stop correction

TODO_064 was reopened after the operator reported normal F12 stop returning arecord
status 1. This was reproduced with installed alsa-utils 1.2.6 on virtual ALSA null.
Classification now accepts requested quiet status 1 without fallback/diagnostic;
forced stop and diagnosed errors remain rejected. Expanded regression tests use
the production CaptureResult classifier. Current correction evidence and validation
are in TODO_064; operator microphone retest and full audio/radio gates remain OPEN.

After the stop correction: full local pytest 1419 PASS, compile/Ruff PASS;
operator real-microphone F12 retest remains OPEN.

### Recording panel — 2026-10-22

Operator requested a large persistent red recording panel in the existing FT1 window
area. Implemented in the human TUI: RECORDING has a solid red background, bold white
text, elapsed timer and F12 stop/send hint; STARTING/FINALIZING/ADMITTING use a neutral
preparation panel. The existing FT1 window resumes after admission. Scrolling and F7
do not hide the recording indicator; compact mode survives terminal resize. A hidden
old FT1 confirmation cannot intercept F12 while local voice work is active.

This is presentation only: capture, Codec2, FT1 lifecycle/wire, profiles, agent JSONL
and firmware remain unchanged. No streaming or concurrent voice mode was added.
Software validation/evidence for this panel is recorded separately below. Real audio
and paired-radio acceptance for the complete feature remain OPEN.

Panel software validation: selected TUI/voice/file-window/PTY subset **173 PASS**;
full workflow software commands: compile/Ruff PASS, pytest **1432 PASS**, 7 existing
DeprecationWarning, 121.33 s. Lizard advisory WARNING remains non-blocking per workflow.
A real ncurses/PTY probe confirmed white-on-red recording at 80×24, 60×12 and 35×8,
neutral finalization/admission and handoff to ordinary FT1. No physical devices opened.
Checkpoint: `a1fe052` + saved change.patch/source SHA manifest in
`/home/dream/coding/journal_of_experiments/20261021T225707Z_st_voice_panel/`.
API/skill consistency and comment-preserving diff reviewed; no machine API change.
Operator visual/microphone retest after ST restart remains OPEN; no new commit/push.
