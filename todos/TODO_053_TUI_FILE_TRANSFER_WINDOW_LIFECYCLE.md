# TUI file-transfer window lifecycle TODO

TODO-ID: TODO_053
Status: IMPLEMENTED / operator hardware validation OPEN
Recorded: 2026-10-16

## Purpose

Привязать окно передачи к настоящей runtime-попытке FT1 и убрать возможность
показывать сохранённый прогресс как текущую передачу. Заменить двухстрочный
фоновый progress bar одной краткой строкой. Это продолжение TODO_052;
история и выполненные gates предыдущего TODO сохраняются.

Оператор сначала запросил исследование и новый TODO, затем явно поручил
исправление и тесты. Последние уточнения оператора имеют приоритет:

* В чат писать происходящие lifecycle-события, причины ошибок и итог.
* Автоматически закрывать большое окно только после успешной передачи.
  Ошибка и отмена остаются в уже открытом окне до явного Esc.
  Это заменяет прежнее автозакрытие после принятого cancel из TODO_052.
* Реальное возобновление после reboot/reconnect возвращает большое окно
  в центр, даже если оператор ранее свернул его в фон.
* Boot/READY сами по себе, при отсутствии передачи, не создают окно по F7.

## Finding checkpoint

Исследованный snapshot: ветка `dev_tui_exp_recursive_missing`, чистый исходный
commit [`f70f1a8efff02f4b29e77782f50c18941596f890`](https://github.com/dreamworkerln/serialterminal/commit/f70f1a8efff02f4b29e77782f50c18941596f890).
Исходные findings: [REVIEW_003](../reviews/REVIEW_003_TUI_TRANSFER_WINDOW_LIFECYCLE.md),
F001–F004. Точная причина описанного оператором reboot/F7 эпизода по имеющимся
логам не установлена: клавиши и frontend mode в них не записаны. Не выдавать
найденные дефекты за доказанную причину именно этого физического эпизода.

## Current behavior at finding checkpoint

`FileTransferWindow` различал операции только по transfer_id и считал активным
любой snapshot, кроме трёх terminal states. При этом `display_snapshot()` может
возвращать history, а одна и та же ROOT identity допускает повторную runtime
попытку. При асинхронной отмене окно скрывалось раньше завершения worker,
после чего прежний DATA header/F7 оставались доступны. Same-ID resume наследовал
состояние закрытого окна и старого confirmation. Одно redraw независимо читало
несколько snapshots для header и overlay. В фоне показывались две подробные
строки с отдельным progress bar.

## Target behavior: transitions

Frontend modes: `closed`, `foreground`, `background`; confirmation — отдельное
адресное состояние ввода, а не владелец FT1. Наличие файла, журнала, старого
snapshot, соединения или READY не является admission новой передачи.

| Условие / событие | Большое окно | Фоновая строка / F7 |
| --- | --- | --- |
| Запуск ST; нода загружается; активной ROOT нет | Закрыто | Индикатора файла нет; F7 ничего не открывает |
| Новый принятый ROOT TX/RX, в том числе preparation | Открывается по центру | Верхнего file indicator нет |
| F7 при активной передаче | `foreground` ↔ `background` | Только в фоне одна строка; та же попытка и прогресс |
| Обычный progress, resize, scroll, clear, Enter | Сохраняет выбранный mode | Не создаёт новую операцию и не всплывает на каждый chunk |
| Reboot/reconnect во время настоящей FT1 | Сохраняет mode, показывает recovery | Boot/READY без FT1 activity не имитирует возобновление |
| Подтверждённое продолжение FT1 после восстановления | Автоматически `foreground` | Свёрнутая строка убирается; последующий F7 снова работает |
| Успех ROOT по действующему FT1 contract | Автоматически закрывается | Индикатор исчезает; F7 не возвращает результат |
| Ошибка/отмена при открытом окне | Остаётся до Esc | Состояние и причина доступны; Esc закрывает окончательно |
| Ошибка/отмена в фоне | Не всплывает | File indicator исчезает; результат остаётся в чате |
| Подтверждённый local cancel принят, settlement ещё идёт | Остаётся с явным ожиданием отмены | Нельзя повторно подтвердить cancel или открыть старый DATA progress |
| Snapshot перестал принадлежать runtime owner / suspended history | Закрыто | F7 не превращает history в активную передачу |
| Источник snapshot исчез при открытом confirmation | Видимое уведомление об изменившейся операции | Старый Enter потребляется, не уходит в command input |
| После terminal принят тот же transfer_id заново | Новая попытка открывается | Старые confirmation, mode и скорость не наследуются |

Пользовательское закрытие terminal окна не удаляет файлы, journals или retained
FT1 history. Закрытие UI не снимает mutation ownership до реального settlement.

## Presentation and ownership contract

* FT1 остаётся единственным владельцем истины об admission/settlement.
  Его `presentation_snapshot()` атомарно содержит runtime presentation metadata:
  `attempt`, `active`, `cancel_requested`, `resume`, `activity`.
* `attempt` — process-local opaque identity конкретной принятой попытки;
  она меняется при same-ID readmission и не является новым wire/protocol ID.
  Confirmation защищается этим ключом и при нажатии Enter, и в момент принятия
  отмены менеджером. Очередь RX отмены также не должна поражать следующую попытку.
* Recovery/resume markers переживают пропущенные redraw. Нельзя требовать,
  чтобы TUI обязательно успел увидеть промежуточный `recovering_local_node`.
* Public controller status используется как дополнительное lifecycle evidence.
  Profile разбирает boot syntax; generic TUI не изучает Chatter strings/UUIDs.
  Для RX после смены controller epoch/generation нужны READY и настоящий FT1
  activity, а не один факт готовности ноды.
* Один redraw использует один ROOT snapshot для окна, header и body geometry.
  Новый принятый TX виден и до первого scheduling его worker, без старого ROOT.
* В фоне: направление, сокращённое имя, процент и скорость для DATA либо
  текущая фаза для recovery/repair/verification, подсказка F7. Одна строка,
  без второй графической полосы, chunks и wire-byte counters. Большое окно
  сохраняет подробные показатели. Скорость сбрасывается на новую попытку.
* Lifecycle-сообщения (начало, стадии, recovery/resume, запрос отмены, suspension,
  terminal outcome) идут в чат и LOCAL log независимо от видимости окна.
  Chunk-level machine traffic не превращается в тысячи human chat сообщений.
  Service child не создаёт ложного ROOT успеха; 100% DATA не заменяет RESULT.

## Scope / non-goals

TUI, FT1 runtime presentation и адресная отмена, regression/PTY tests, документация.
Не менять firmware, wire format, resume admission, физический transport или
порядок передачи. Не исправлять discovery в этом TODO: это TODO_054.
Не превращать UI в отдельную протокольную FSM и не сбрасывать FT1 по boot markers.

## Implementation

- [x] Явные frontend modes и positive active-state eligibility с проверкой owner.
- [x] Runtime attempt key, snapshot metadata и atomic expected-attempt cancellation.
- [x] Защита deferred RX cancel от новой same-ID попытки.
- [x] Recovery/resume возвращает окно; READY без передачи его не создаёт.
- [x] Success autoclose; cancel/error до явного закрытия; видимый stale-modal guard.
- [x] Один snapshot на кадр, корректный новый ROOT до старта worker.
- [x] Одна фоновая строка, reset скорости, lifecycle chat summaries.
- [x] Согласовать README/ARCHITECTURE/FILE_TRANSFER и проверить AGENT_API/runtime skill.

## Validation

- [x] Исходные offline repro на настоящих manager lifecycle paths и узких fakes.
- [x] Новые contract tests против исходного SHA: 12 FAIL / 7 PASS
  ([evidence](../reviews/evidence/REVIEW_003/base-regressions.txt)); это доказательство
  дефектов/изменённого контракта, не acceptance новой реализации.
- [x] Первый полный software checkpoint: 1073 PASS / 104.19 s, 7 fork warnings.
- [x] Финальные lifecycle + real curses/PTY TX/RX: 197 PASS / 5.16 s.
- [x] Полный pytest финального source/test snapshot: 1081 PASS / 103.18 s,
  без skips; 7 существующих multiprocessing/fork warnings.
- [x] Compileall (src/tests/entrypoints/tools/scripts), diff/comment review PASS.
  Full Ruff: те же 3 F401, побайтово одинаковый вывод на исходном SHA и final tree;
  новых static findings нет. Общий CI parity gate TODO_051 не закрывается этим fix.
- [ ] Отдельный разрешённый физический reboot/reconnect smoke с точным runtime
  checkpoint; согласовать с остающимся аппаратным gate TODO_052.

Автотесты должны проверять реальные admission → failure → drain/release → same-ID
restore → late confirmation/cancel; начальный boot без передачи; активный RX boot
с READY и DATA; recovery целиком между redraw; foreground/background terminal
матрицу; pending cancellation; старую RX очередь; новый TX до scheduling worker;
resize/Unicode; отсутствие второго file indicator; отсутствие повторного popup
после следующего F7. Зелёный source-string test не заменяет исполнение этих путей.

## Result

Implementation / validated source identity:
`f70f1a8efff02f4b29e77782f50c18941596f890` +
[source/test patch](../reviews/evidence/REVIEW_003/implementation-source-tests.patch.gz),
SHA256 распакованного patch `c0a549cf7a044f8326b37f2dc841cbdc4535b2cabc2f4ff447f3c6ef20e33a53`.
Полный PASS относится к этому точному patch; последующие изменения — docs/evidence.
Новый lifecycle suite содержит 27 cases, включая composed FT1 и controller parser
checks; реальный curses/PTY дополнительно проверяет TX/RX и один snapshot на кадр.
[Full pytest](../reviews/evidence/REVIEW_003/full-pytest.txt),
[TUI subset](../reviews/evidence/REVIEW_003/tui-targeted.txt).

AGENT_API и runtime skill явно просмотрены: JSONL schema/ownership и wire format
сохранены; добавлены только описания human lifecycle summaries. Dependency direction:
TUI → public manager presentation snapshot / public profile controller status.
Observation-workspace skill/references просмотрены read-only: они используют agent
API и не закрепляют старый F7/cancel UI; их изменение не требуется. Перед физическим
TUI smoke нужно использовать актуальную матрицу этого TODO вместо старого cancel
autoclose сценария TODO_052.

Software gates PASS; physical validation NOT RUN — оператор проверяет на железе сам.
Commit/push в текущую ветку GitHub и публикация в GDI явно разрешены оператором
после полного pytest PASS; точный commit сообщается в итоговом ответе.
