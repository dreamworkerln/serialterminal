# Codec2 voice implementation — ревью коммитов агента

REVIEW-ID: REVIEW_006
Разобрано в TODO: TODO_064
Status: COMPLETE
Verdict: RED — voice lifecycle; ordinary FT1 regression subset PASS
Date UTC: 2026-10-21
Reviewer: Codex, independent review of agent implementation

## Reviewed state

Repository: https://github.com/dreamworkerln/serialterminal
Branch: `dev_tui_exp_recursive_missing`
Reviewed commit: [8a9d91dc03630dec88c67ca0282a12dcff9ae89b](https://github.com/dreamworkerln/serialterminal/commit/8a9d91dc03630dec88c67ca0282a12dcff9ae89b)
Base commit: [989118042f2c4030bcde8bc328540ac67e14faed](https://github.com/dreamworkerln/serialterminal/commit/989118042f2c4030bcde8bc328540ac67e14faed)
Range: `989118042f2c4030bcde8bc328540ac67e14faed..8a9d91dc03630dec88c67ca0282a12dcff9ae89b`
Base selection: согласованная revision TODO_063 после REVIEW_005, до реализации агента.
Agent commits: `dc52187` (implementation), `8a9d91d` (TUI compatibility fixes).
Checkout: clean до начала; production source оставлен без изменений.
Previous review: [REVIEW_005](REVIEW_005_CODEC2_VOICE_FILE_INTEGRATION.md), design review.
Task/spec: [TODO_063](../todos/TODO_063_CODEC2_VOICE_MESSAGES.md).

Reviewed source hashes: [manifest](evidence/REVIEW_006/reviewed-files-sha256.json).
Workspace run: `/home/dream/coding/journal_of_experiments/20261021T214130Z_st_codec2_review006/`.
Сырые выводы, synthetic PCM и QA environment находятся там; здесь сохранены scripts,
сводки и checksums. Ни source fixes, ни новые TODO, ни Git/Drive публикации не выполнялись.

## Scope

Store-and-forward voice: standard .c2, ctypes SDK boundary, ALSA process ownership,
voice state/correlation, TUI/CLI wiring и regression относительно BASE. Прочитаны
source diff и полные новые модули, materially changed TUI bodies, применимые
architecture/TODO/FT1 contracts и tests. Существующие функции не удалены; FT1,
transports, profiles и agent JSONL implementation в этом diff не изменены.

Проверены software boundaries без физических устройств. Микрофон, динамик, BLE/USB,
RF, reconnect на нодах и firmware не запускались/не проверялись. Full pytest/полный CI
не запускался; ниже два явно выбранных subset и отдельные behavioral probes.

## Findings

### F001 — HIGH: terminal прежнего TX сбрасывает состояние уже следующей записи

Where: `voice_service.py:228–270` (`toggle_recording`), `544–572`
(`_apply_tx_terminal_locked`); public FT1 release ordering — `file_transfer/core.py:790–801`.

Verified behavior: после admission service возвращается в IDLE, оставляя `_tx_attempt`
до асинхронного terminal. После завершения FT1 `manager.busy` уже false, но voice
observer ещё может не обработать terminal. Следующий F12 начинает новую запись.
Обработчик старого TX без проверки current capture job безусловно очищает
`_capture_job_id` и меняет `_state` на IDLE/READY_FILE.

Failure scenario: запись A отправлена; completed event A ожидает observer; FT1 уже
освободился; оператор начинает B; B находится в RECORDING; observer применяет A.
B продолжает читать микрофон, однако service сообщает IDLE. Следующий F12 не ставит
stop: повторный start отказывается из-за `_audio_mode == capture`. TUI guards также
перестают считать локальную запись активной.

Impact: запись нельзя штатно остановить/отправить через F12; микрофон продолжает
работу при ложном состоянии, а device/profile/disruptive guards открыты. Требуется
выход/cleanup; это нарушение новой voice state machine, не поломка FT1 wire protocol.

Evidence: `stale_tx_clobbers_recording` в [probe](evidence/REVIEW_006/voice_regression_probe.py).
Использованы настоящие FT1 sender/receiver с loopback transport и gate только на
порядок callbacks. Обе FT1 стороны completed; `RECORDING -> IDLE`, capture открыт,
stop=false, F12=false. [Результаты](evidence/REVIEW_006/probe-results.json).

Test gap: существующий early-terminal test заканчивает одну local attempt; нет
нового capture между FT1 release и применением предыдущего terminal.
Confidence: HIGH, composed executable reproduction.
Required acceptance: settlement A может менять только принадлежащее A состояние;
capture B сохраняет job identity/state/guards и останавливается вторым F12.
Follow-up TODO: not assigned; scope existing TODO_063, задачи этим review не менялись.

### F002 — HIGH: playback запускается во время STARTING и затем пересекается с capture

Where: `voice_service.py:255–268`, `294–308`, `636–658` (`_playback_loop`).

Verified behavior: `wait_for` учитывает STARTING/RECORDING/FINALIZING, но после timeout
его false result игнорируется. Повторная проверка учитывает только queue и audio_mode.
Во время SDK/process startup state=STARTING, audio_mode=None. Через 0.2 s queued
playback запускается; capture worker затем без проверки playback назначает audio_mode
и открывает RECORDING. Начало audio owner не зарезервировано на весь startup.

Failure scenario: F12, медленный `start_capture`, verified RX ставится в autoplay.
Playback начинается в STARTING; start_capture завершается, микрофон и playback
работают одновременно.
Impact: нарушена согласованная взаимная исключительность; при использовании динамика
звук входящего сообщения может попасть в исходящую запись. Акустическое эхо на
реальной аппаратуре не проверялось; software overlap доказан.
Evidence: `playback_during_starting`, controlled AudioBackend startup gate, реальный
VoiceMessageService; [probe-results](evidence/REVIEW_006/probe-results.json).
Test gap: существующий тест RX during capture проверяет только уже установленный
RECORDING/audio_mode=capture, не STARTING и timeout predicate.
Confidence: HIGH для concurrency defect; акустическое следствие условно.
Required acceptance: audio admission атомарен для startup/capture/playback; ложный
predicate после timeout не разрешает playback; deferred RX ждёт освобождения owner.
Follow-up TODO: not assigned; related REVIEW_005/F003 and TODO_063.

### F003 — MEDIUM: запись после forced kill автоматически отправляется как штатная

Where: `voice_audio.py:140–162`; `voice_service.py:342–350`.

Verified behavior: `_wait_bounded` допускает terminate/kill fallback и возвращает
returncode. CaptureResult содержит returncode/stderr, но service проверяет только
requested_stop. Это означает «F12 просил stop», а не «capture корректно остановлен».
Код затем finalize-ит header/frames и вызывает start_send даже при returncode=-9.

Failure scenario: arecord не завершается штатно, fallback убивает процесс; неполная
запись всё равно становится автоматически отправленным voice file.
Impact: незавершённый audio stream выдаётся за успешно сформированную запись;
контейнер может оставаться валидным, что не доказывает корректность audio drain.
Evidence: `forced_kill_is_auto_sent`: CaptureResult(-9, true, ...) приводит к FT1
admission и IDLE. Проходят настоящие finalize/validation/admission branches service;
результат process boundary подан узким fake. [Результаты](evidence/REVIEW_006/probe-results.json).
Test gap: имеющийся fallback test проверяет факт terminate/kill, но не запрет
автоматической отправки после такого завершения.
Confidence: HIGH; правило классификации expected SIGINT exit требует сохранения
отличия от forced stop, blanket reject любого nonzero также был бы неверен.
Required acceptance: различать graceful requested stop, forced stop и unexpected exit;
при недоказанном корректном drain не выполнять auto-send, дать diagnostic/cleanup.
Follow-up TODO: not assigned; scope TODO_063 audio completion contract.

### F004 — MEDIUM: late RX прежнего manager проходит autoplay после замены session

Where: `voice_service.py:491–500`, `541–542`, `597–634`.

Verified behavior: event чужого/отсоединённого manager получает generation=-1.
TX branch проверяет manager/generation, RX branch такой проверки не делает и
использует -1 как допустимую часть autoplay identity. Старый receive_dir проверяется
через envelope.manager, поэтому file validation не отсекает obsolete session.

Failure scenario: manager A detached, manager B bound; late completed RX от A
принимается и проигрывается. Это отличается от уже принятой корректной queued playback:
новое audio admission происходит после утраты manager lifetime.
Impact: obsolete session может инициировать локальное воспроизведение; на RX отсутствует
тот же generation barrier, которым защищён TX. Старый файл при этом надо сохранить.
Evidence: `stale_rx_after_manager_replacement`: current manager B, event A,
получен один playback. [Результаты](evidence/REVIEW_006/probe-results.json).
Test gap: stale-manager test реализован только для TX и retained source deletion.
Confidence: HIGH для воспроизводимого поведения; expected lifetime barrier следует
из TODO_063 correlation/session contract. Политику already-admitted playback менять
для этого не требуется.
Required acceptance: проверять RX source manager/generation при обработке и admission;
late obsolete event не становится новым autoplay текущего lifetime; файл остаётся.
Follow-up TODO: not assigned; scope TODO_063, related REVIEW_005/F002.

### F005 — MEDIUM: playback exception оставляет дочерний процесс без cleanup owner

Where: `voice_audio.py:212–267` (`AlsaAudioBackend.play_pcm`).

Verified behavior: после Popen iterator/decoder может выбросить исключение. В finally
ссылка `_playback_process` очищается и pipes закрываются, но terminate/wait не
вызываются. После этого stop_playback уже не видит дочерний процесс. Ошибки playback
и декодирования не гарантируют bounded child reap.

Failure scenario: процесс создан, затем decoder generator бросает VoiceCodecError;
дочерний процесс ещё работает либо требует ожидания завершения. Backend теряет owner.
Impact: процесс может пережить ошибку/shutdown или остаться unreaped; зависание/занятость
реального audio device зависят от поведения aplay и не доказаны аппаратно.
Evidence: `playback_child_survives_decoder_failure`: реальный controlled Python child
вместо aplay; после decode exception child alive, stop_playback его не останавливает,
handle=None. Probe сам гарантированно terminate/wait-ит child в finally, утечки от
review не оставлены. [Результаты](evidence/REVIEW_006/probe-results.json).
Test gap: tests/test_voice_audio.py проверяет capture, но не playback exception cleanup.
Confidence: HIGH для process ownership failure; ALSA/device consequence NOT RUN.
Required acceptance: на каждом error/cancel path созданный child boundedly stopped
и waited/reaped до потери ownership; исходное исключение остаётся наблюдаемым.
Follow-up TODO: not assigned; scope TODO_063 AudioBackend lifecycle.

## Previous findings recheck

| Previous | Result | Evidence / limitation |
| --- | --- | --- |
| REVIEW_005/F001 | FIXED — базовый admission retention contract | Busy/exception сохраняют finalized path, READY_FILE и diagnostic; existing test PASS. Полный аппаратный incoming META / F5 retry не выполнялся |
| REVIEW_005/F002 | STILL_PRESENT — частично реализован | Admission вынесен из curses, pending/early terminal и isolated logger tests PASS; новые F001/F004 показывают оставшиеся lifetime gaps |
| REVIEW_005/F003 | STILL_PRESENT — startup gap | RECORDING/playback базовый test PASS; F002 воспроизводит overlap в STARTING |

Исторический RED REVIEW_005 не изменён. Это новый pass реальной реализации.

## Validation and evidence

| Проверка | Результат | Scope / evidence |
| --- | --- | --- |
| New codec/audio/service/TUI + neighboring CLI/TUI subset | 74 PASS / 2.00 s | Python 3.12.15; [точная команда](evidence/REVIEW_006/targeted-tests-summary.json) |
| Core FT1 + file window/lifecycle + keyboard/transfer PTY + generic profile subset | 220 PASS / 16.96 s | [точная команда](evidence/REVIEW_006/neighbor-regressions-summary.json); synthetic transport/PTY, не physical USB/BLE |
| Five failure probes | 5 defects reproduced | [script](evidence/REVIEW_006/voice_regression_probe.py), [results](evidence/REVIEW_006/probe-results.json); reproduction успех не является acceptance PASS |
| Actual ST wrapper -> SDK c2dec; SDK c2enc -> ST wrapper | PASS | 50 frames / 407 encoded bytes / 16000 PCM bytes в каждую сторону; encoded files побайтово совпали; [result](evidence/REVIEW_006/sdk-interop-result.json) |
| Pinned SDK provenance | Confirmed for existing build | upstream 310777b1c6f1af0bc7c72f5b32f80f6fd9136962, Codec2 1.2.0; manifest/library SHA в result; SDK не пересобирался |
| Changed-file Ruff; compile Python without emitted bytecode; function inventory | PASS | [static summary](evidence/REVIEW_006/static-summary.json), 12 Python files; прежних functions не удалено |
| GitHub CI exact 8a9d91d | No runs found | Read-only Actions API query head_sha; [summary](evidence/REVIEW_006/github-ci-summary.json). Это не CI failure и не server PASS |
| Full pytest / full local/server CI | NOT RUN | Выбранные subsets не подменяют полный CI |
| Real microphone/speaker / paired nodes / RF repair-resume voice | NOT RUN | Не было аппаратного разрешения/запуска, source review и synthetic audio only |

All checks above target exact 8a9d91d, BASE 9891180. QA dependencies из pyproject
установлены в отдельный run-local Python 3.12 environment: source workspace и системный
Python не изменялись. [Версии packages](evidence/REVIEW_006/qa-packages.txt).

Portable failure-probe invocation: задать `ST_REVIEW_REPO` к checkout reviewed target,
добавить его src в PYTHONPATH, запустить voice_regression_probe.py с dev dependencies.
SDK probe принимает CODEC2_SDK; synthetic PCM и outputs сохраняет рядом со script,
поэтому для запуска скопировать его в отдельный writable run directory.

## Assessment

Общий замысел реализован правильно: голос остаётся обычным finalized файлом FT1,
codec wrapper действительно совместим с pinned SDK; profile/transport/firmware/API
границы сохранены. В выбранном обычном FT1/TUI regression subset поломок не обнаружено.
Однако новая voice state machine и audio lifecycle содержат пять воспроизведённых
дефектов, включая зависающую запись и concurrent capture/playback. Принимать voice
feature как готовую и закрывать TODO_063 нельзя до исправления и повторной проверки.
Зелёные 294 tests и рабочий codec container этих путей не покрывают.

## Result

Status: COMPLETE
Verdict: RED
Verdict scope: Codec2 voice lifecycle implementation in 9891180..8a9d91d.
Remaining gates: fixes/review для F001–F005; clean-env CI; real audio smoke;
paired radio/repair/resume acceptance отдельно по TODO_063.
Follow-up: findings входят в тему TODO_063; разбор на TODO и source fixes не выполнялись.

## TODO triage — 2026-10-21

По отдельному поручению оператора все F001–F005 перенесены в
[TODO_064](../todos/TODO_064_CODEC2_VOICE_LIFECYCLE_FIXES.md), implementation поручена.
Исходный target, verdict RED, findings и evidence этого review сохранены.
