# FT1: исправления lifecycle по ревью recursive missing

TODO-ID: TODO_043
Status: OPEN
Priority: CRITICAL
Created: 2026-10-13
Implementation: NOT STARTED
Validation: REVIEW FINDINGS RECORDED / FIX VALIDATION OPEN
Self-review: 2026-10-13 / original six reproduced / eight additional findings
Branch: `dev_tui_exp_recursive_missing`
Review checkpoint: `8cf689e0edd286ac9e48df9ab3c6990fc1bf0f79`
Initial review checkpoint: `cb891540451df7c864a40d06618213f10235477a`
Review base: `fd94bdeb1fd878e072b0f852b3e8f461d928e3cd`
Review verdict: **RED / не merge-ready; в таком виде в dev_tui не merge'ить.**

## Purpose

Собрать все шесть замечаний независимого ревью, переданного оператором, в одну
исходниковую задачу SerialTerminal. Исправить lifecycle и ограничения памяти,
сохраняя recursive missing-list и DATA LINK_FAIL → END → фактические missing holes.
Задача связана с [TODO_042](TODO_042_FT1_BATCHED_FINAL_REPAIR.md); замечания 1–2
затрагивают также recovery/resume workstream
[TODO_041](TODO_041_FT1_FAILURE_RECOVERY_AND_RX_OBSERVABILITY.md).

По отдельному поручению оператора выполнено собственное software/source ревью ST.
Дополнительные findings 7–14 и подозрения S1–S2 записаны ниже в этой же задаче;
это расширение review record, а не реализация исправлений.

Оформление этого TODO не запускает исправления, аппаратные прогоны или Git-операции.

## Связи с REVIEW_001 — разбор 2026-10-14

[REVIEW_001](../reviews/REVIEW_001_DEV_TUI_EXP_RECURSIVE_MISSING.md) проверяет
`db740af94c700c7c4e6d96abef7e809dadfcaf1c`. Исходные checkpoints и результаты
собственного/внешнего ревью ниже сохраняются; новый разбор не является re-review.

| Numbered finding | Раздел этой задачи |
| --- | --- |
| REVIEW_001/F001 | 1 — RX restore atomicity |
| REVIEW_001/F002 | 2 — quarantined same-ID retry |
| REVIEW_001/F003 | 3 — ROOT END / child RESULT ordering |
| REVIEW_001/F004 | 4 — child identity collision |
| REVIEW_001/F005 | 5 — terminal ROOT frame retention |
| REVIEW_001/F006 | 6 — bounded processed history |
| REVIEW_001/F007 | 7 — rejected ROOT META mutation |
| REVIEW_001/F008 | 8 — child-aware idle budget / META activity |
| REVIEW_001/F009 | 9 — foreground negotiation state |
| REVIEW_001/F010 | 10 — concurrent publication ownership |
| REVIEW_001/F011 | 11 — losing concurrent open workers |
| REVIEW_001/F012 | 12 — cleanup vs live pre-manifest partial |
| REVIEW_001/F013 | 13 — normalized cancel ID error |
| REVIEW_001/F014 | 14 — malformed journal timestamp |

Implementation/validation по всем этим findings остаются OPEN.
Из S1 выделен подтверждённый `REVIEW_001/F015` в
[TODO_044](TODO_044_FT1_LIVE_DURABLE_RETENTION.md); согласовать его cleanup
с finding 12. Из S2 выделен подтверждённый uint32 admission defect
`REVIEW_001/F016` в [TODO_045](TODO_045_FT1_CHUNK_SPACE_ADMISSION.md).
Остальные memory/queue/LIST invariants S2 остаются в этой задаче; их подозрения
не превращаются в доказанный runtime defect одним разбором.
Новый peer-ownership blocker `REVIEW_001/F017` ведётся отдельно в
[TODO_046](TODO_046_FT1_PEER_SCOPED_SENDER_JOURNALS.md), timing regression
`REVIEW_001/F018` — в [TODO_047](TODO_047_TIMING_APPEND_EVENT_IDENTITY.md).

## Checkpoint и границы доказательств

Ревьюер указал checkout `/mnt/serialterminal-exp`, branch
`dev_tui_exp_recursive_missing`, HEAD
`cb891540451df7c864a40d06618213f10235477a`, base
`fd94bdeb1fd878e072b0f852b3e8f461d928e3cd`.
Номера строк ниже относятся именно к этому checkpoint; пути исходников считаются
от `src/serialterminal/file_transfer/`.

При оформлении TODO локальный checkout `/home/dream/coding/python/serialterminal`
находится на той же branch и HEAD. Уже имеются незакоммиченные изменения в
`.agents/skills/serialterminal-agent/SKILL.md`, `AGENT_API.md`,
`src/serialterminal/profiles/chatter/machine_client.py` и untracked
`tests/test_chatter_machine_recovery.py`. Эти изменения не являются частью
проверенного ревьюером HEAD и не изменяются в рамках оформления TODO.

Все repro, измерения и результаты тестов в разделе Findings и Review validation
получены **по сообщению ревьюера**. При создании TODO они не воспроизводились;
сырые артефакты и команды запуска ревьюер в сообщении не приложил. Наличие записанных
результатов не означает, что исправления уже реализованы или проверены.

### Повторное подтверждение на опубликованном HEAD — 2026-10-13

Оператор передал дополнительное независимое ревью
`dev_tui_exp_recursive_missing@8cf689e0edd286ac9e48df9ab3c6990fc1bf0f79`.
Ревьюер сообщил, что не полагался на текст TODO и отдельно воспроизвёл все шесть
findings на этом HEAD. Вердикт остаётся **RED / в dev_tui не merge'ить**;
исправления recursive lifecycle ещё не начинались.

По сообщению ревьюера, `8cf689e` не меняет `recursive.py`, `resumable.py`,
`manager.py` или `coordinator.py` относительно `cb891540`; изменения главным
образом относятся к machine-negotiation recovery, тестам и оформлению TODO_043.
При внесении этого дополнения локально проверены HEAD `8cf689e`, чистое исходное
worktree и отсутствие diff между двумя checkpoints для этих четырёх FT1-модулей.
Это проверка идентичности исходников, не локальное воспроизведение дефектов.
Dirty edits, перечисленные выше, описывают момент первоначального оформления TODO.

Дополнительный reference, переданный оператором:
[артефакт ревью в Google Drive](https://drive.google.com/file/d/1bjeA4JbyRcXwnW8ZLNV0XotUYmX7WT6b/view).
Содержимое артефакта при этом обновлении не проверялось; evidence ниже записано
из переданного текста ревью. Ревьюер сообщил, что исходники не менял и оставил
worktree clean.

## Current behavior / Findings

### 1. RX restore не атомарный — blocker

Место: `resumable.py:267–359`.

Последовательность:

```text
load suspended manifest
→ claim
→ persistent_status = receiving
→ _checkpoint_incoming()     # manifest уже переписан
→ publish runtime state
```

Ревьюер fault injection остановил операцию после успешного checkpoint, но до
runtime publication. Результат:

```text
до:
durable = suspended
runtime = failed

после rollback:
durable = receiving
runtime = failed
_active_id = None
_incoming = None
```

Комментарий `# Только успешные claim и checkpoint публикуют новое runtime state.`
не обеспечивает заявленный инвариант: durable state уже заявляет receiving,
хотя runtime revival не состоялся.

Требование: durable transition после runtime admission либо полноценный rollback
manifest. Согласовать durable/runtime state и ownership при ошибке на этой границе.

### 2. Same-ID retry trap после integrity failure — blocker

Место: `resumable.py:692–740`.

Воспроизведение ревьюера:

```text
transfer 0x55
→ final wire_hash_mismatch
→ receiver state = quarantined
→ sender journal остаётся
→ пользователь повторяет send того же source
→ sender выбирает journal
→ снова transfer_id 0x55, resumed=True
→ peer отвечает retained transfer is quarantined
```

Terminal integrity failure → retained outgoing journal → automatic same-ID resume
→ тот же заведомо непригодный identity → failure loop.

Требование: разделить причины по пригодности same-ID resume:

- Resumable: timeout / restart / lost outcome / recoverable lifecycle.
- Non-resumable: wire_hash_mismatch / original_hash_mismatch / quarantine /
  identity conflict; окончательную классификацию причин закрепить при реализации.

Нельзя делать новый ID после вообще любой ошибки: это разрушит нормальный resume.
Судьбу непригодного outgoing journal и правила следующего send определить явно.

### 3. ROOT END выбрасывается при задержанном child RESULT

Место: `recursive.py:236–254`.

Сейчас логика при наличии child сохраняет END только после локально увиденного
успешного remote_result дочернего LIST:

```python
if frame.child_id is not None:
    child = ...
    if child ... and child.record.remote_result and child.record.remote_result.ok:
        frame.deferred_end = message
    return
```

Допустимая перестановка событий:

```text
B sends LIST child
A receives LIST
A verifies LIST
A sends RESULT child
A immediately sends requested ROOT DATA
A sends ROOT END
              ↓
B host sees ROOT END
before B host presentation of child RESULT
```

Когда `child_id != None`, а `remote_result is None`, B молча выбрасывает END.
Ревьюер воспроизвёл это с задержанной presentation дочернего RESULT. При легальном
`max_control_replays=0` результат:

```text
TX: failed / remote_result_timeout
RX: repair_requested / all requested DATA already arrived
```

На `8cf689e` ревьюер дополнительно проверил handler непосредственно: правильный
END с правильным repair_id до presentation child RESULT оставляет
`deferred_end=None`; после установки успешного child RESULT тот же END сохраняется.

Default replay чаще маскирует ошибку повторными META/END, но добавляет паузу
и делает correctness зависимым от повторной доставки control.

Требование: сохранять текущий END с правильным repair_id как deferred независимо
от того, увидел ли локальный host child RESULT. Применять его после корректного
settlement child; stale или неверный repair_id не должен завершать ROOT.

### 4. Child transfer ID collision уничтожает ROOT recursive context

Места: `recursive.py:142–198`, `protocol.py:247–252`.

До underlying admission wrapper выполняет:

```python
frame = _Frame(...)
self._recursive_frames[meta.transfer_id] = frame
```

Затем вызывается `manager._handle_meta()`. Protocol проверяет согласованность
parent/depth, но не запрещает child.transfer_id == parent_transfer_id.

Воспроизведение ревьюера:

```text
ROOT id = 100
child META:
    transfer_id = 100
    parent_transfer_id = 100
    depth = 1
```

Underlying manager конфликтующий META отвергает правильно. Но wrapper уже
перезаписал `_recursive_frames[100]`, затем rollback удалил этот key:

```text
до:
record 100 = waiting_result
root frame 100 = exists

после bad child META:
record 100 = waiting_result
root frame 100 = MISSING
```

ROOT и lease живы, recursive context уничтожен. Это дефект admission validation
принимаемого input, независимо от вероятности случайной uint64 collision.

Требование: минимум child_id != parent_id и отсутствие конфликтов с active
recursive identities. Сохранить корректный duplicate/replay path. Map менять
после успешного admission либо точно восстанавливать прежний объект при rollback.

### 5. Terminal ROOT frames удерживаются бессрочно

Место: `recursive.py:318–361`.

Для child есть `_recursive_frames.pop(record.transfer_id, None)`, а удаления
terminal ROOT нет. Core ограничивает terminal records:
`FILE_MAX_RETAINED_TERMINAL = 16` и удаляет старые `_records`.

Ревьюер выполнил подряд 40 обычных успешных передач:

```text
                         TX    RX
_records                 16    16
_terminal_order          16    16
_recursive_frames        40    40
orphan frames            24    24
```

Recursive layer удерживает старые `_TransferRecord`, META и всё содержимое _Frame
после core eviction. Это memory leak долгоживущего ST.

Требование: единая retention/cleanup policy для ROOT frame, согласованная
с terminal record/tombstone semantics. Проверить успех, failure, cancel и eviction;
не потерять обработку допустимых late control и completed publication semantics.

### 6. parent.processed растёт без ограничения

Места: `recursive.py:40`, `recursive.py:155`, `recursive.py:341`.

Каждый успешно завершённый child остаётся до смерти ROOT frame:

```python
parent.processed[record.transfer_id] = frame.meta
```

Дизайн разрешает прогресс по одному чанку без минимальной скорости; любое
уменьшение missing_total сбрасывает no_progress (`100 → 99 → 98 → 97 → ...`).
Общего лимита repair cycles нет, поэтому история растёт вместе с их количеством.
По оценке ревьюера, при создании таких же MetaMessage:

```text
100 000 processed entries ≈ 31.8 MiB
≈333 bytes / entry
```

Миллион repair cycles даёт порядок сотен MiB только в словаре. Дефект 5 оставляет
его жить и после завершения ROOT.

На `8cf689e` ревьюер отдельно выполнил 5000 успешных child settlements:
`processed=5000`, `terminal_order=16`, records=17. Это подтверждение роста
replay-history во время live ROOT, отдельно от приведённой оценки памяти.

Требование: bounded replay-history mechanism с явным пределом памяти/entries
и проверенными duplicate/stale semantics. Не хранить каждый child META с начала
передачи бессрочно. Устранение ROOT leak само по себе не решает рост live ROOT.

## Собственное ревью ST — 2026-10-13

Checkpoint: `8cf689e0edd286ac9e48df9ab3c6990fc1bf0f79`, branch
`dev_tui_exp_recursive_missing`, diff base `fd94bdeb1fd878e072b0f852b3e8f461d928e3cd`.
В начале этой работы уже присутствовали документальные изменения в TODO_043,
TODO_042 и TODO_INVENTORY.md от дополнения внешнего ревью. Source/tests соответствовали
HEAD и в ходе собственного ревью не изменялись. Firmware и физическое оборудование
не использовались.

Scope ревью: diff ветки, FT1 recursive/core/recovery/storage/pipeline, связанные
agent/session admission, machine negotiation, radio timing, TUI/shutdown и logging;
dependency direction сверена с ARCHITECTURE.md. Это software review этих путей,
не свидетельство полного аудита всех модулей ST или аппаратной acceptance.

### Локальное подтверждение исходных findings 1–6

| Finding | Собственный repro на HEAD | Результат |
| --- | --- | --- |
| 1 | После настоящего checkpoint restore выставлен stopping до runtime publication | suspended → receiving на диске; runtime failed, active_id=None, incoming=None |
| 2 | Два связанных CaptureTransport, ROOT 0x55, подмена hash END; повтор того же source после settlement | RX quarantined; journal сохранён; второй send снова 0x55/resumed=True и failure |
| 3 | Handler получает правильный END/repair_id при живом child TX до remote_result, затем после RESULT OK | deferred_end отсутствует до RESULT и сохраняется после; полная end-to-end перестановка с max_control_replays=0 в собственном repro не прогонялась |
| 4 | ROOT TX 100/waiting_result и child META id=parent_id=100 | ROOT record и active_id живы, ROOT frame удалён |
| 5 | 40 RX через META/DATA/END с реальной проверкой/публикацией; отдельно 40 TX terminal settlements без реальной отправки | Обе стороны: records=16, frames=40, orphan=24; TX здесь проверяет retention boundary, не 40 end-to-end передач |
| 6 | 5000 синтетических успешных child RX settlements при живом ROOT; request потребляется после каждого settlement | processed=5000, terminal_order=16, records=17, frames=1; это structural stress, не физический slow-progress run |

Все шесть дефектов воспроизведены локально в указанных границах. Исходные внешние
repro/evidence выше сохранены отдельно и не подменяются этими проверками.
В repro 2 дополнительно видно, что `_finish_early_result()` (`resumable.py:918–925`)
теряет `details.remote_code`: первый failure содержит wire_hash_mismatch, второй
early rejection содержит только remote_failed и текст quarantine. Это следует
учесть при классификации journal в исправлении 2.

### 7. HIGH — отвергнутый ROOT META перезаписывает живой recursive frame

Место: `src/serialterminal/file_transfer/recursive.py:200–204`.

После `manager._handle_meta()` wrapper проверяет только наличие non-terminal record,
не факт admission. Поэтому конфликтующий META того же ROOT ID, отвергнутый core
с protocol_error, всё равно создаёт новый `_Frame` поверх существующего.

Локальные repro:

- RX record сохраняет исходный rx_meta, но frame.meta становится отвергнутым META;
  request_id 900 → 0, processed и no_progress обнуляются.
- TX ROOT 100 с admitted RX child 101: после конфликтующего ROOT META frame
  заменён, child_id и last_end потеряны; `_incoming_for(100)` возвращает incoming
  дочернего файла 101. ROOT active_id=100 и child record=receiving остаются живыми.

Это отдельный путь от self-parent collision finding 4: он действует и при
`parent_transfer_id=0`. Rejected input не должен менять existing frame,
repair identity, history, child relation или incoming binding. Регрессии нужны
для TX/RX ROOT, active child и последующего корректного repair.

### 8. HIGH — RX idle budget не исключает время child и игнорирует META activity

Места: `recursive.py:145–152`, `336–344`, `455–461`;
`manager.py:367–394` (все пути от `src/serialterminal/file_transfer/`).

При child `_expire_stale_incoming()` только пропускает проверку. После settlement
возвращается тот же parent incoming с прежним last_activity_monotonic. Уже
проведённое в child время немедленно попадает в проверку ROOT inactivity,
хотя FT1_RESUME.md обещает pause parent idle waits во время children.

Локальный clock-boundary repro: budget=10 s, parent activity=20 s назад;
при child ROOT остаётся repair_requested, после успешного child settlement timestamp
не меняется и первый idle sweep даёт failed/remote_sender_timeout. Для длинного
служебного файла это означает преждевременный timeout до прихода следующего ROOT DATA.
Child duration здесь моделировалась timestamp, реальное RF ожидание не запускалось.

Отдельно правильный duplicate META в fast path отправляет RESUME, но не вызывает
`_touch_incoming()`. После такого META timestamp остаётся старым, receiver всё равно
истекает. Underlying resumable handler activity обновляет, wrapper обходит этот путь.

Требование: определить и проверить pause/resume elapsed accounting для parent;
валидная META activity учитывается, stale/conflicting input не продлевает ownership.
Нужны длинный child, nested unwind и valid duplicate META regressions.

### 9. HIGH — неудачный foreground HELLO retry оставляет M1 в negotiating навсегда

Место: `src/serialterminal/profiles/chatter/machine_client.py:79–94`,
`116–145`, `160–165`, `180–189`.

`_negotiate()` выставляет negotiating и очищает error, но failed state при исключении
восстанавливает только bootstrap caller. Foreground `_ready()` retry такого rollback
не делает. Background lifecycle не повторяет согласование из negotiating; следующие
foreground calls при существующем start_thread ждут, вместо нового HELLO.

Repro с fake M1 node: bootstrap получает BUSY и завершается failed; foreground send
повторяет HELLO, пока owner ещё BUSY, и получает machine_owner_busy. После освобождения
owner lifecycle thread жив, pending пуст, но mode=negotiating. Следующий send получает
machine_negotiation_timeout; новых HELLO=0. Negotiation deadline сокращён до 30 ms
для воспроизводимой software проверки, SUBMIT/RF не отправлялись.

Требование: exception/cancel-safe negotiation state и отсутствие phantom active
negotiation после выхода её owner; повторить failed foreground retry → owner free
для idle RX и нового send, сохранив Pending/UNKNOWN guards.

### 10. BLOCKER — параллельная publication перезаписывает файл при двух RESULT OK

Место: `src/serialterminal/file_transfer/resumable.py:642–662`;
`core.py:174–189`. FILE_TRANSFER.md обещает не перезаписывать existing final names.

Два manager/session могут иметь общий receive_dir. `_unique_destination()` и
проверка exists перед `os.replace()` не резервируют destination атомарно.

Детерминированный concurrency repro: две RX с ID 201/202, разными проверенными
данными и filename=retained.bin; barrier поставлен непосредственно перед финальным
os.replace после обеих exists checks. Обе RX completed, обе отправили RESULT OK,
final_path одинаковый. Файл один и соответствует лишь одной transfer; два completed
tombstones не обеспечивают сохранность двух payloads.

Требование: publication ownership/name reservation между writers одного namespace,
без overwrite и с сохранением одного durable intent destination при restart.
Проверить две concurrent sessions, разные payloads/IDs, одинаковый basename,
existing file и crash/reconcile на выбранных границах. Конкретный способ
межпроцессной coordination пока не выбран; software repro — один процесс/два manager.

### 11. MEDIUM — проигравший concurrent agent open оставляет application workers

Место: `src/serialterminal/agent_core.py:687–728`.

FileTransferManager и M1 bootstrap запускаются до второй проверки device ownership.
При проигрыше этой проверки закрывается только transport, созданный file manager
не закрывается и session не регистрируется.

Repro двух concurrent open одного fake device с barrier после создания managers:
один open успешен, второй device_busy; отвергнутый manager сохраняет живые RX,
outbox и machine lifecycle threads, stopping=False. Публичный close_all видит только
зарегистрированную session; orphan отдельно закрыт самим repro после измерения.

Generic JSONL runner сериализует обычные synchronous open requests, поэтому repro
проверяет конкурентный SessionManager API/заявленный кодом race guard, не утверждает
что две последовательные JSONL строки автоматически создают эту гонку.
Требование: полностью закрывать не admitted runtime; regression с двумя callers
и подтверждением отсутствия orphan workers/queued application operations.

### 12. HIGH — создание второго manager удаляет live partial первого

Места: `src/serialterminal/file_transfer/resume_store.py:26–43`, `325–338`;
`resumable.py:522–558`.

Startup cleanup считает .part без manifest orphan и удаляет его. Между созданием
нового .part и первым checkpoint manifest есть легальное окно live admission;
другой manager в том же receive_dir не знает ownership первого.

Repro: остановить первый RX на claim callback после создания part, создать второй
manager в общем receive_dir, затем продолжить admission. Part существовал до второго
manager и исчез после него; первый checkpoint заканчивается storage_failed.
При прямом handler вызове runtime остаётся receiving/active_id=601 до cleanup;
software RX worker error boundary также требуется проверить отдельной регрессией.

Это ownership/storage race, не TTL eviction старого suspended файла. Нужна
coordination cleanup/admission общего namespace; opening another session не должно
удалять bytes live transfer. Проверить также count/byte-budget cleanup против
активных owners, не отменяя retention policy для abandoned state.

### 13. MEDIUM — invalid cancel transfer_id превращается в internal_error

Место: `src/serialterminal/file_transfer/recursive.py:464–468`;
`src/serialterminal/agent_core.py:1074–1083`.

Wrapper вызывает parse_transfer_id до core cancel, который переводит parse error
в FileTransferError/invalid_transfer_id. Поэтому FileProtocolError уходит мимо
SessionManager._file_error и JSONL выдаёт internal_error.

Локально через настоящий AgentProtocol с injected file manager:
file_transfer_cancel(session=s1, transfer_id=not-hex) → internal_error,
message="transfer_id is not valid hex". Session/device здесь не открывались.
Требование: сохранить предусмотренную core cancel нормализацию invalid ID и
регрессию JSONL; invalid input не должен отменять descendants.

### 14. MEDIUM — повреждённый journal timestamp ломает выбор resume до validation

Место: `src/serialterminal/file_transfer/resume_store.py:283–295`;
`manager.py:69–105`.

Outgoing candidates сортируются через float(updated) до `_validated_sender_candidate`.
Один manifest с правильными schema/source_path, но updated="bad-timestamp", даёт
необработанный ValueError и блокирует start_send этого source. Это disk-metadata
robustness case, не валидный journal, создаваемый штатным writer.

Repro записывает JSON такого journal через atomic_json и вызывает
`_sender_resume_candidate()`: ValueError/could not convert string to float.
Требование: повреждённая metadata не должна обходить candidate validation и
повреждать пригодные journals; выбранный ignore/reject outcome закрепить явно.

### Подозрения / design boundaries, не подтверждённые отдельными failure repro

- **S1: live durable-store retention.** `ResumeStateStore.cleanup()` вызывается
  constructor, но не save_incoming/save_outgoing/save_completed. Documented count,
  TTL и total-part bounds не выглядят enforced во время одного долгого процесса.
  Нужны live-store stress и явный contract, когда срабатывают эти bounds; не считать
  это уже доказанным исчерпанием диска. Проверять вместе с безопасной cleanup из 12.
- **S2: representable/admitted file size и temporary memory.** META содержит
  uint64 sizes, END/DATA — uint32 chunk space; admission не проверяет этот совместный
  предел. `_missing_indexes()` материализует весь missing set до ROOT percent gate,
  `read_missing_list()` материализует все ranges, `parent.requests` не имеет maxlen.
  Большие peer declarations или накопление запросов могут обойти цель bounded memory.
  Опасные многогигабайтные allocations в ревью не запускались. Нужны явные supported
  limits/flow invariants и stress; не вводить произвольный лимит successful repair
  cycles вместо решения finding 6. Проверить допустимость нового LIST относительно
  текущего END, не только наличие parent.last_end.

### Собственная validation и воспроизводимость

Локальные software артефакты находятся в `/tmp/st-review-043-20261013/`.
Это временные host-side review scripts/logs, не canonical hardware evidence;
содержимое scripts использует fixtures текущего HEAD и assertions наличия дефекта.
Exit 0 этих scripts означает **REPRODUCED / RED**, а не PASS исправления.

Команды, выполненные из repository root:

```text
PYTHONPATH=src:tests /usr/bin/python3 /tmp/st-review-043-20261013/probes.py
PYTHONPATH=src:tests /usr/bin/python3 /tmp/st-review-043-20261013/recursive_boundaries.py
PYTHONPATH=src:tests /usr/bin/python3 /tmp/st-review-043-20261013/integrity_retry.py
PYTHONPATH=src:tests /usr/bin/python3 /tmp/st-review-043-20261013/storage_and_agent.py
PYTHONPATH=src:tests /usr/bin/python3 /tmp/st-review-043-20261013/api_and_cleanup.py
```

Все пять final repro scripts: exit 0 / defects reproduced. Первые draft запуски
probes требовали исправления interpreter (default python без pytest) и входного
conflicting META в TX case; final log относится к исправленному review script,
runtime не менялся.

SHA256 scripts и final logs (порядок: script / одноимённый .log):

```text
probes:
c61afe48cbdef865ce03fc1f3cd5144f11fa88cda90859440ab08f1f815b7220
9b783324c4da49301126ba4a148e24bbf5ee6a8fc9ba993046b8605e5ecd47ec
recursive_boundaries:
24e343bf2ea3dde486f6d4dc7ae5b818cf7a00d26f3c52df2294956d34ecf8c8
5668bfdc9d2ef03558a3b7aed3c675c1725219745afb7367600d69ef5d550538
integrity_retry:
de78a493ad2a9ce817a73ad7f1c6d1c8c62bd835013ea284941f6165e4ff038a
23afa5e805c8eeaf14910da37e2d35bd5791c5bdac351174e374f8c4c54b6fef
storage_and_agent:
8c5f6f8a115f0b2872c459d7a11f2dd07c14a20ea7c19f05aa8b4f0ba995d599
67decd2bab15d933ab4dbea8bdf62d579704bdd34eadbee839cabe9b292d7928
api_and_cleanup:
7e7bdb6015e258eb0bf11f01d18226440d75ff8c608754daff7270a4422ab6b3
f26541aa6a2b27cc525498316cc80b9db5c6b4e2784b0c537fa2dfeadf506a6c
```

Дополнительные проверки текущего software HEAD:

```text
SERIALTERMINAL_CACHE_FILE=/tmp/st-review-043-20261013/device-cache.json pytest -q
  sandbox: 573 passed, 28 failed / 292.20 s
SERIALTERMINAL_CACHE_FILE=/tmp/st-review-043-20261013/device-cache-unsandboxed.json pytest -q
  outside sandbox: 601 passed / 66.02 s
/usr/bin/python3 -m compileall -q src serialterminal.py tools
  PASS
```

26 sandbox failures относятся к mocked BLE: самостоятельный socketpair.send
подтвердил EPERM, asyncio loop не получает межпоточный wakeup. Два остальных
failures — observe_two_sessions_wakes_for_either_session и
lost_meta_hits_percent_gate_then_explicit_retry_keeps_identity — отдельно прошли
(2 passed / 1.71 s); они также прошли в полном outside-sandbox run. Причина их
первого падения не установлена; сохранить это как test instability follow-up,
не объявлять доказанным production defect или исправлением.

Связанный subset с isolated cache: `pytest -q tests/test_file_transfer*
tests/test_ft1* tests/test_chatter_machine* tests/test_chatter_radio_timing.py
tests/test_chatter_binary_user.py tests/test_timing.py tests/test_application_log.py
tests/test_tui.py` — 284 passed / 46.93 s. `pytest -q -x tests/test_agent.py` —
19 passed / 2.22 s. Полный sandbox `pytest -q -x` отдельно остановился на mocked
BLE burst (47 passed, 1 failed); он не является full-suite gate.

Full outside-sandbox log SHA256:
`041a29d058470c299227d71bd26b1764d349a19f5d45f9f2ddf42a204567224a`.
601 PASS относится к существующим tests на неисправленном HEAD. Fix regression
coverage для новых findings отсутствует, verdict остаётся **RED**.

### Follow-up checklist собственного ревью

- [ ] 7: rejected ROOT META сохраняет frame/repair/child/incoming для TX и RX.
- [ ] 8: parent idle elapsed не включает child; valid META обновляет activity.
- [ ] 9: failed/cancelled foreground negotiation не оставляет negotiating без owner.
- [ ] 10: atomic destination ownership, concurrent publication без overwrite/false OK.
- [ ] 11: cleanup всех workers проигравшего concurrent SessionManager.open.
- [ ] 12: shared-store cleanup не удаляет live admission/partial другого manager.
- [ ] 13: invalid file_transfer_cancel ID → invalid_transfer_id, без side effects.
- [ ] 14: безопасный malformed updated/candidate validation и явный error policy.
- [ ] S1/S2: закрепить live retention, representability и memory/queue invariants;
  отдельные stress/negative cases, не выдавая static suspicion за выполненный repro.
- [ ] Сохранить постоянные regression tests и review evidence при реализации;
  временные /tmp artifacts не являются долгосрочным regression suite.

Ранее предложенный порядок исправлений 3+4+5 → 1+2 → 6 сохранён как рекомендация
первого ревью. Перед implementation нужно учесть новые publication/storage blockers
и согласовать design; собственное ревью не выбрало новую архитектуру или API.

## Target behavior и Invariants

Сохранить архитектурную идею recursive repair. Положительные результаты ревью:

- DATA LINK_FAIL → не считать DATA гарантированно потерянным → закончить initial
  stream → END → receiver определяет реальные holes → verified LIST → repair.
- repair_id связывает END с конкретным verified LIST.
- Depth 0..8; ROOT 30% gate с exemption service-files; no_progress=3.
- Один внешний ownership lease на ROOT; internal service files не публикуются
  пользователю.
- Explicit cancel active-child в repro ревьюера корректно отменил descendants
  и освободил единственный ROOT lease.

Исправления должны сохранить перечисленные свойства, SHA256/publication contract,
нормальный same-ID recovery и защиту от повторной обработки служебного списка.
Тесты этой branch проверяют текущий recursive multi missing. Возврат к одиночному
legacy MISSING или сохранение совместимости ради отсутствующих пользователей
не являются критерием исправления.

## Scope и Non-goals

В scope: исходные шесть findings, regression tests для пяти конкретных repro,
bounded design и stress test processed history, согласование актуальной
recovery/recursive документации и подготовка повторного ревью.
По поручению собственного ревью сюда также внесены findings 7–14 и S1–S2;
их implementation/validation остаются OPEN по follow-up checklist выше.

Firmware, radio protocol и flashing не входят в эту исходниковую задачу.
Не запускать FLOW/CAPS/FT1 QUERY, watchdog TODO_038 или unrelated cleanup.
Аппаратная матрица и merge acceptance остаются gates TODO_042; создание этого
TODO не является разрешением запускать их, переключать ветки, commit или push.

## Design и порядок следующих действий

Точные варианты atomic restore, journal classification и replay retention пока
не выбраны: требования и альтернативы ревьюера не выдаются за готовый design.
До реализации закрепить выбранные правила и их проверяемые пределы в этом TODO.

Порядок, предложенный ревьюером:

1. Исправить 3 + 4 + 5 как непосредственно внесённые recursive branch.
2. Закрыть 1 + 2, чтобы recursive stack не оставался поверх lifecycle holes.
3. Добавить regression test на каждый из пяти конкретных repro.
4. Для processed ввести bounded design и stress test, сохраняя допустимый
   медленный прогресс ROOT без нового лимита всех успешных repair cycles.
5. После исправлений и validation передать ревьюеру diff от
   `cb891540451df7c864a40d06618213f10235477a` до нового точного checkpoint.
   Только после повторного ревью решать готовность к hardware matrix/merge.

Этот порядок описывает будущую работу; исправления требуют отдельного старта
оператором. При незакоммиченном checkpoint фиксировать также dirty diff digest.

## Implementation checklist

- [ ] 3: корректно deferred END при delayed child RESULT и верном repair_id.
- [ ] 4: безопасный identity validation/admission и точный rollback map.
- [ ] 5: согласованный ROOT frame retention/cleanup с core и tombstones.
- [ ] 1: атомарный RX restore относительно durable/runtime/lease state.
- [ ] 2: классификация resumable/non-resumable failure и outgoing journal policy.
- [ ] 6: bounded processed history с документированным пределом и replay semantics.
- [ ] Сверить FT1_RESUME.md, FILE_TRANSFER.md, AGENT_API.md и repo-local
  serialterminal-agent skill с реально изменёнными semantics; синхронизировать
  TODO_041/TODO_042 и inventory без выдачи старого evidence за новую проверку.

## Validation checklist / acceptance criteria

- [ ] 3: delayed presentation child RESULT, ROOT DATA/END уже пришли,
  max_control_replays=0 — verified ROOT success без timeout и повторного END;
  отдельно stale/wrong repair_id и child failure.
- [ ] 4: child_id == parent_id и collision с другим active recursive identity
  отвергаются без изменения существующего frame/record/lease; последующий
  корректный repair работает. Duplicate META не создаёт второй admission.
- [ ] 5: не менее 40 sequential ROOT transfers на TX/RX; terminal records и
  recursive state obey documented retention bound, orphan frames отсутствуют.
  Покрыть success/failure/cancel/eviction и требуемую late-control обработку.
- [ ] 1: fault injection после checkpoint до runtime publication — rollback
  восстанавливает согласованный durable/runtime state и освобождает claim;
  нормальный suspended restore и повтор после rollback работают.
- [ ] 2: wire_hash_mismatch → quarantine → повтор того же source не входит
  в automatic same-ID failure loop. Проверить original_hash_mismatch и identity
  conflict; timeout/restart/lost outcome сохраняют пригодный same-ID resume.
- [ ] 6: stress многих successful repair cycles с прогрессом по одному чанку;
  history stays within chosen explicit bound. Duplicate/stale LIST, в том числе
  после eviction history, не запускает repair повторно и не портит active parent.
  Проверить память/entries во время live ROOT и release после terminal state.
- [ ] Записать RED/GREEN для repro, exact implementation/validation checkpoints,
  команды и результаты relevant FT1/recovery/publication/recursive/timing tests.
- [ ] Полный pytest -q в среде с необходимыми зависимостями, compileall и
  diff --check для final checkpoint; collection failure не считать PASS.
- [ ] Повторное независимое ревью diff от cb891540... и решение по всем шести
  findings. TODO_043 CLOSED только после implementation и обязательных software/
  review gates; это само по себе не закрывает hardware/merge gates TODO_042.

## Review validation — внешние результаты, не новая validation

### Первое ревью — cb891540...

Независимые результаты, сообщённые ревьюером для cb891540...:

```text
FT1/recovery/publication/recursive subset: 114 passed
machine client / radio timing / recursive/timing subset: 98 passed
python -m compileall: PASS
git diff --check fd94bde..HEAD: PASS
```

Полный suite ревьюер подтвердить не смог: в его runtime нет pyserial,
полный collection падает на serial/TUI-модулях. Широкие subsets без этих файлов
шли без падений до лимита команды; это не полный PASS.
Ревьюер отметил соответствие статуса TODO_042 реальному состоянию:
`OPEN / CRITICAL / PROTOTYPE IMPLEMENTED / REVIEW AND BROAD VALIDATION OPEN`.

### Дополнительное ревью — 8cf689e...

Результаты, сообщённые ревьюером для
`8cf689e0edd286ac9e48df9ab3c6990fc1bf0f79`:

```text
FT1/machine/timing subset: 215 passed
python -m compileall -q src serialterminal.py tools: PASS
git diff --check fd94bde..HEAD: PASS
All six lifecycle findings: independently reproduced / RED
```

Полный `pytest -q` не PASS: collection упал на 14 test modules из-за отсутствующего
pyserial. По сообщению ревьюера, установка зависимости была невозможна без сети.
Это limitation его окружения; все шесть findings воспроизводятся без pyserial.

Deletion review: ревьюер не нашёл очевидно случайного удаления production-функции;
изменения `main`, `close`, `TimingTrace.__init__` оценены как осознанные refactor/API
changes, legacy FT1 tests заменены v2/recursive tests. Backwards compatibility
для этой ветки не является требованием. В HEAD-only изменениях `machine_client.py`
новый blocker не доказан, новые recovery tests проходят по сообщению ревьюера;
это не исправляет recursive stack.

Эти результаты не запускались локально при обновлении TODO и не заменяют
fix/regression/stress/full-suite/re-review gates.

## Known limitations

Исходные repro воспроизведены локально в границах раздела собственного ревью;
end-to-end delayed RESULT/max_control_replays=0 и физический slow-progress stress
в этом собственном ревью не выполнялись. Предел processed history и
точная классификация permanent failure требуют явного design при реализации.
Прежние успешные subsets и hardware smoke не отменяют найденных lifecycle дефектов
и не доказывают пригодность cb891540... к merge.

## Result

Status: OPEN / CRITICAL
Implemented: none; создан task record, runtime не изменён этой задачей.
Validated: software HEAD 8cf689e — full suite 601 PASS вне sandbox, compileall PASS;
исходные шесть и дополнительные восемь defects локально воспроизведены в описанных
границах. Fixes/regressions/re-review/hardware OPEN; существующий suite не покрывает
найденные дефекты. Source/tests не менялись, commit/push/merge не выполнялись.
Review: 8cf689e0edd286ac9e48df9ab3c6990fc1bf0f79 — RED / не merge-ready;
все шесть findings повторно подтверждены ревьюером после первого cb891540... review;
собственное ревью добавило 7–14 и static follow-ups S1–S2. Вердикт RED сохранён.
Next action: перед отдельным стартом implementation учесть findings 7–14/S1–S2
и закрепить publication/shared-storage design; исходный предложенный порядок
3+4+5 → 1+2 → 6 требует включить новые findings, регрессии/stress, полный software
gate и повторное независимое ревью.
