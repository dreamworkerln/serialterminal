# Codec2 voice messages поверх существующего FT1

TODO-ID: TODO_063
Status: OPEN
Priority: P2
Created: 2026-10-21
Planning checkpoint: `dev_tui_exp_recursive_missing@184fabfb8088b5b3568a26883c0a71159468864e`.
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

Это фундамент для последующего realtime half-duplex voice, но realtime transport
в scope этого TODO не входит.

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
не более одного 20-ms frame.

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
не блокировать curses event loop. Ошибки процесса идут в application log и краткий
human diagnostic; raw PCM не пишется в application/primary logs.

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
  F12 -> RECORDING

RECORDING
  F12 -> FINALIZING -> FileTransferManager.start_send(c2_path)
                       -> обычный FT1 lifecycle/progress

shutdown / codec/audio failure
  -> local capture cleanup; никогда не отправлять незавершённый файл автоматически
```

Во время RECORDING/FINALIZING:

* F2 profile/device target changes и F5 arbitrary file send блокируются;
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

F10 остаётся без ST binding.

### TX temporary-file lifecycle

Использовать отдельный temp root, по умолчанию через system `tempfile` namespace
вроде `serialterminal-voice/`; при необходимости добавить `--voice-temp-dir`.
Не использовать receive directory как TX scratch.

* capture failure/truncated initialization удаляет незавершённый temp;
* после `start_send()` temp нельзя удалять до terminal TX outcome;
* успешный TX удаляет generated temp;
* failed/cancelled TX сохраняет finalized `.c2` и сообщает путь для диагностики/
  возможного ручного retry, вместо молчаливой потери записи;
* service shutdown закрывает handles/processes и не оставляет partial file,
  выглядящий как успешно сформированный voice message.

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

## Implementation plan

### Phase 1 — codec/file primitives

- [ ] Добавить isolated Codec2 ctypes wrapper и standard `.c2` reader/writer.
- [ ] Добавить explicit SDK-tree configuration/provenance validation без system-lib fallback.
- [ ] Зафиксировать Codec2 3200 frame geometry через runtime ABI, не размножать размеры по TUI.
- [ ] Добавить deterministic final PCM-frame padding и strict encoded-frame validation.

### Phase 2 — local audio backend

- [ ] Определить `AudioBackend` protocol и Linux `arecord`/`aplay` implementation.
- [ ] Сделать capture/playback streaming и bounded process/thread shutdown.
- [ ] Отделить backend errors от FT1 correctness; не писать raw audio в logs.

### Phase 3 — VoiceMessageService

- [ ] Реализовать `IDLE -> RECORDING -> FINALIZING -> FT1` TX state machine.
- [ ] Генерировать collision-resistant short `*.stvoice.c2` filename и temp lifecycle.
- [ ] Bind generated TX temp к returned FT1 transfer ID для success cleanup и failure retention.
- [ ] Реализовать RX terminal-event recognition и bounded playback queue.
- [ ] Сделать close/shutdown idempotent и безопасным при recording/playback/finalizing.

### Phase 4 — TUI integration

- [ ] Добавить F12 toggle через canonical TUI action, без concrete-profile branch.
- [ ] Добавить recording/finalizing admission guard для F2/F3/F5 и disruptive human actions.
- [ ] Сохранить existing F4/F6/F7/F8/F9/F10/Ctrl+C/Ctrl+Q semantics.
- [ ] Добавить capability-aware footer/help/status; не создавать второй transfer progress UI.
- [ ] Разделить FT1 event dispatch и logging так, чтобы playback не жил в log function.

### Phase 5 — configuration/docs

- [ ] Протянуть explicit codec2 SDK directory через human CLI -> TUI; classic/agent APIs не менять без отдельного решения.
- [ ] При необходимости добавить configurable voice temp directory через centralized settings/CLI ownership, без mutable globals.
- [ ] Обновить README/INSTALL/ARCHITECTURE и коротко FILE_TRANSFER: voice является application consumer verified FT1 completion, не новым FT1 protocol.
- [ ] По AGENTS.md отдельно проверить AGENT_API и `.agents/skills/serialterminal-agent/SKILL.md`; ожидаемое решение — JSONL schema не меняется в первом этапе.

## Validation / acceptance

### Automated

- [ ] Codec2 wrapper tests: load/provenance failures, ABI signatures, geometry,
  create/destroy ownership, encode/decode exact buffer sizes and invalid input.
- [ ] `.c2` tests: header roundtrip, truncated/invalid magic, unsupported mode,
  body not divisible by frame size, final-frame padding.
- [ ] Reference interoperability against exact `codec2-sdk` checkpoint:
  ST-produced `.c2` decodes with SDK `c2dec`; SDK `c2enc` file is accepted/decoded
  by ST. Record SDK manifest and exact commit in evidence.
- [ ] AudioBackend tests with fake processes/streams: fragmented reads, process exit,
  stop during blocked read, stderr/error, bounded terminate/kill and no zombies.
- [ ] Voice service TX tests: start/stop/send, FT1 busy, codec/audio unavailable,
  start_send failure, success temp cleanup, failure/cancel retention, shutdown while recording.
- [ ] Voice service RX tests: root verified RX exactly once; wire filename vs uniquified
  final_path; invalid header; unsupported mode; failed/cancelled transfer; recursive child;
  playback failure cannot change FT1 completion.
- [ ] TUI unit + curses/PTY: F12 mapping/status, F2/F3/F5/disruptive guard during record,
  existing F6/F7/F8/F9 behavior, F10 remains unbound, Ctrl+C/Ctrl+Q shutdown,
  generic profile unchanged.
- [ ] Existing FT1/core/TUI regressions plus full `pytest -q`; compileall and changed-file
  Ruff according to AGENTS.md. Source tests run outside restrictive sandbox as required.

### Real integration

- [ ] Linux host with exact SDK tree + real `arecord`/`aplay`: record -> standard `.c2`
  -> local decode/play smoke; no full PCM temp file.
- [ ] Two SerialTerminal/Chatter endpoints: F12 record/stop, existing FT1 transfer,
  receiver waits for verified durable completion and auto-plays once.
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
* cross-platform audio backend beyond the abstraction needed for a later implementation.

Realtime half-duplex should become a separate TODO after this store-and-forward path
proves Codec2/audio/UI ownership. It should reuse `Codec2Library`/`Codec2Codec` and
`AudioBackend`, but use a latency-oriented transport where late speech frames may be
dropped rather than retransmitted until reliable delivery.

## Planning result

Plan only. No SerialTerminal source, tests, runtime behavior, firmware, hardware,
Codec2 SDK or FT1 wire changes are implemented by this TODO creation checkpoint.
