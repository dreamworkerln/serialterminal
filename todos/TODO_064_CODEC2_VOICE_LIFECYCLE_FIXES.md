# Codec2 voice: исправление lifecycle и audio ownership

TODO-ID: TODO_064
Status: IMPLEMENTED / SOFTWARE PASS / OPERATOR RETEST OPEN
Priority: P1
Created UTC: 2026-10-21
Source: REVIEW_006/F001–F005, поручение оператора оформить новый TODO и исправить.
Base: `dev_tui_exp_recursive_missing@8a9d91dc03630dec88c67ca0282a12dcff9ae89b`.
Review: [REVIEW_006](../reviews/REVIEW_006_CODEC2_VOICE_IMPLEMENTATION.md).
Parent feature: [TODO_063](TODO_063_CODEC2_VOICE_MESSAGES.md).

## Purpose

Исправить пять доказанных defects новой store-and-forward voice integration.
Голос остаётся обычным завершённым файлом существующего FT1. Исходные review
probes/results сохраняются как историческое evidence; source исправляется отдельно.

## Current behavior / findings

| Finding | Severity | Дефект | Требуемое поведение |
| --- | --- | --- | --- |
| REVIEW_006/F001 | HIGH | terminal старого TX сбрасывает state/job новой записи; F12 не останавливает микрофон | TX settlement адресован своей attempt; более новая запись сохраняет state, stop и TUI guards |
| REVIEW_006/F002 | HIGH | timeout ожидания playback игнорирует STARTING; capture и playback пересекаются | Один audio owner на весь startup/capture/finalization/playback, повторная проверка predicate после любого wakeup |
| REVIEW_006/F003 | MEDIUM | forced kill capture считается штатным stop и запускает send | Graceful requested stop отличим от forced/unexpected exit; сомнительная запись не auto-send |
| REVIEW_006/F004 | MEDIUM | late RX detached/replaced manager попадает в autoplay | RX admission проверяет конкретный manager/generation; obsolete event не создаёт новый playback |
| REVIEW_006/F005 | MEDIUM | decode/iterator error после Popen теряет child без terminate/wait | Каждый созданный audio child имеет bounded cleanup/reap на всех exit paths |

## Scope / invariants

- Только voice_service, voice_audio, их regression tests и согласованная документация.
- Capture job и TX attempt имеют независимую identity; поздний settlement не меняет
  новый capture и не теряет source ownership, даже если начался новый admission.
- Базовый ранний terminal до start_send return и retained READY_FILE сохраняются.
- STARTING резервирует audio owner до открытия микрофона; startup failure/close
  освобождает его. Playback отложен и не включается после false timeout predicate.
- Graceful stop/drain допускает штатный результат SIGINT, но не forced terminate/kill
  и не произвольный process failure. Partial не отправляется автоматически.
- Проверка RX manager/generation повторяется после filesystem validation перед
  enqueue; ранее корректно принятые published файлы не удаляются.
- Playback error/cancel закрывает stdin, boundedly останавливает и wait/reap-ит child;
  cleanup не скрывает исходную ошибку и не отменяет успешную файловую доставку.
- Обычный FT1/BINARY/JSONL/profile/transport/firmware не меняется. Нет нового radio
  режима, retry scheduler, record-duration cap или voice протокола.

## Implementation

- [x] F001: разделить capture state ownership и tracking незавершённых TX attempts;
  не терять старую attempt при новом admission, учитывать early terminal и shutdown.
- [x] F002: атомарный audio owner на STARTING, точный playback predicate на каждом wake.
- [x] F003: явный stop outcome backend, отказ от auto-send при forced/unexpected stop.
- [x] F004: RX manager/generation barrier при dispatch и enqueue, published file retained.
- [x] F005: exception-safe playback child cleanup с bounded terminate/kill/wait.
- [x] Regression tests каждого finding, включая составной реальный FT1 loopback F001.
- [x] Сверить ARCHITECTURE/README/TODO_063, AGENT_API и generic agent skill; сохранить
  неизменённые machine-facing semantics и исторический результат REVIEW_006.

## Validation / closure

Software acceptance этой corrective задачи:

- [x] Новые regression tests воспроизводят defects на BASE и проходят на fix checkpoint.
- [x] Поздний A terminal во время STARTING/RECORDING/ADMITTING B не меняет B;
  после B F12 запись завершается штатно, source A очищается только своим результатом.
- [x] Queued RX ждёт delayed microphone startup дольше playback wait timeout;
  capture/playback одновременно не открыты; startup failure/close не блокирует queue.
- [x] Graceful stop accepted; forced fallback и unexpected returncode не вызывают FT1.
- [x] Late RX после detach/rebind, а также replacement во время validation отклонены;
  нормальный текущий verified RX по-прежнему играет один раз.
- [x] Реальный controlled child остановлен/reaped после decode/stream error и cancel.
- [x] Relevant voice/TUI/FT1 subset, затем общий pytest по AGENTS.md для shared TUI
  regression, compile и Ruff по workflow; фиксировать точные команды/skips/revision.
- [x] Diff review, source/API/skill consistency, BASE+patch SHA evidence и итоговый
  статус implementation отдельно от validation.

Аппаратное acceptance полной voice feature остаётся в TODO_063: real microphone/
speaker smoke и paired radio/repair/resume. Оно не является заменой software proof
этих пяти дефектов. Этот TODO не закрывает TODO_063 и не утверждает hardware PASS.
Full GitHub CI/commit/push/physical actions не выполняются без поручения.

## Historical evidence / initial result (superseded for F003 closure)

Baseline evidence: [review probes](../reviews/evidence/REVIEW_006/probe-results.json).
Implementation: DONE. Validation: PASS, software corrective scope only.
Validated checkpoint: BASE 8a9d91dc03630dec88c67ca0282a12dcff9ae89b +
`todos/evidence/TODO_064/source-fix.patch`, new regression file and SHA manifest.
Source patch и evidence checksums фиксируются после завершения документации.

### Executed checks

| Check | Result | Evidence |
| --- | --- | --- |
| Initial 17 regression cases before source fixes | 15 FAIL / 2 PASS | baseline-summary.json |
| Final identical 20 regression cases on archived BASE | 17 FAIL / 3 PASS / 8.98 s | baseline-final-summary.json; full old code saved as baseline-8a9d91d.tar and baseline-source/ |
| Same 20 cases on fixed source, identical wrapper/Python/args | 20 PASS / 4.08 s | fixed-final-summary.json; test SHA fd261ac6e8a0b6b8070fe51c4fed208a7f9bd2cd61db62140dfe6a185acc9671 |
| Existing voice/codec/audio/TUI + initial regression subset | 37 PASS / 5.47 s | fix-targeted-summary.json, before 3 extra boundary cases |
| Exact local software commands from .github/workflows/ci.yml | compile PASS; Ruff PASS; pytest 1415 PASS / 123.52 s | workflow-validation-summary.json; Python 3.12.15 |
| Lizard advisory, same workflow thresholds | WARNING, non-blocking as configured | changed-complexity.json: new threshold crossings in RX/overflow helpers; broader cleanup outside this fix scope |
| Full suite warnings | 7 DeprecationWarning, multiprocessing fork with threads | warnings-summary.json; existing test files, no unhandled-thread warning |
| Documentation/API/skill consistency and source diff | Reviewed | ARCHITECTURE/README/TODO_063 updated; AGENT_API and generic skill unchanged because JSONL semantics unchanged |
| Physical audio/radio, GitHub CI, commit/push | NOT RUN | Full feature gates remain in TODO_063 |

Run evidence: `/home/dream/coding/journal_of_experiments/20261021T220835Z_st_todo064_voice_fixes/`.
Portable summaries/patch/checksums: [todos/evidence/TODO_064](evidence/TODO_064/).
The baseline package import path was explicitly checked to belong to saved old src;
no branch checkout/reset/rebase was used. Baseline failures are assertions/timeouts
for the intended defects, not import/syntax/type errors. Old-code archive checksum:
28a22b7d5c28e9cd649d1f63c17fe6f710667d33289711791bc5962a21ba9ebe.

Initial capture graceful-stop handling was checked against ALSA master, which did not establish the installed version behavior:
[signal handler and process exit](https://github.com/alsa-project/alsa-utils/blob/master/aplay/aplay.c).
Backend records actual requested SIGINT and forced fallback separately; an already
exited process is not reclassified as a requested stop.

### Initial result (closure reopened below)

Initially CLOSED for the five software defects and associated regression coverage. This is
implementation-author validation, not a new independent REVIEW_007. Historical
REVIEW_006 remains RED for its exact old target. TODO_063 retains real audio/radio
and release gates; no new radio behavior or firmware changes were introduced.

## Reopened: requested arecord stop returns status 1

Оператор обнаружил отказ при втором F12 на установленном arecord 1.2.6.
Диагностика сохранена в
`/home/dream/coding/journal_of_experiments/20261021T223654Z_st_arecord_status1/`.
Виртуальный ALSA `-D null` воспроизводит requested SIGINT → returncode 1,
без forced fallback и без stderr при `-q`. Первоначальная F003-классификация
ошибочно отклоняет штатную запись. Предыдущие software результаты выше относятся
к прежнему checkpoint и не покрывали этот исход. F003 и software closure открыты
повторно; аппаратный голосовой retest оператора также остаётся OPEN.

### Correction implementation

Ограниченная классификация принимает status 1 только при фактически запрошенном
SIGINT, без forced fallback и с пустым stderr. Backend всегда запускает `arecord -q`;
при диагностике ошибки status 1, незапрошенном exit, status 2 и forced terminate/kill
запись по-прежнему не отправляется. Обычные результаты 0 и -SIGINT сохранены.
Никаких блокировок между двумя ST и выбора другого микрофона не добавлено.

Причина подтверждена точным upstream для установленного alsa-utils 1.2.6:
[capture() and signal_handler()](https://github.com/alsa-project/alsa-utils/blob/v1.2.6/aplay/aplay.c).
После SIGINT `in_aborting` приводит к `prg_exit(EXIT_FAILURE)`; `-q` убирает
информационное сообщение об остановке. Поэтому returncode 1 сам по себе не доказывает
ошибку записи. Probe использует только ALSA `-D null`: микрофон, динамики и радио
не открывались. Без `-q` informational stderr намеренно не допускается; production
backend всегда quiet.

Расширенный service test использует настоящий CaptureResult вместо собственной
копии graceful-stop predicate. До исправления: 1 FAIL / 9 PASS (падает именно
requested quiet status 1). После: voice subset 39 PASS / 5.81 s. Виртуальный real
arecord до/после: code 1, requested=true, forced=false, stderr пуст; graceful_stop
false → true. Исторические patch/results выше сохранены без перезаписи.

Запущенные оператором ST необходимо перезапустить, чтобы они загрузили исправленный
Python-код. Фактический микрофонный F12 → send retest оператора остаётся OPEN.

### Correction validation / current status

- Full local workflow commands: compile PASS; Ruff PASS; pytest **1419 PASS**,
  7 existing DeprecationWarning, 124.20 s. Lizard remains advisory WARNING.
- Exact tested source hashes remained unchanged throughout validation.
- Current checkpoint: BASE 8a9d91d +
  [current-source-fix.patch](evidence/TODO_064/arecord-status1/current-source-fix.patch),
  SHA-256 `42c19419136e0f36acb469e4a68803a6df1d61b12baa48beb3e7a94d08500679`.
- [Correction evidence](evidence/TODO_064/arecord-status1/report.md),
  [validation](evidence/TODO_064/arecord-status1/validation.json) and hashes saved
  separately; initial differential evidence has not been overwritten.
- Source comments/diff and AGENT_API/generic skill consistency reviewed: no machine
  API/schema change, firmware change, GitHub CI or commit/push.
- Implementation and software validation DONE; **operator real-microphone F12 retest
  OPEN**, TODO_063 real audio/radio gates OPEN. Restart both ST processes before retest.
