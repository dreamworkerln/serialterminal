# FT1: исправления lifecycle по ревью recursive missing

TODO-ID: TODO_043
Status: OPEN
Priority: CRITICAL
Created: 2026-10-13
Implementation: NOT STARTED
Validation: REVIEW FINDINGS RECORDED / FIX VALIDATION OPEN
Branch: `dev_tui_exp_recursive_missing`
Review checkpoint: `cb891540451df7c864a40d06618213f10235477a`
Review base: `fd94bdeb1fd878e072b0f852b3e8f461d928e3cd`
Review verdict: **RED / не merge-ready; в таком виде в dev_tui не merge'ить.**

## Purpose

Собрать все шесть замечаний независимого ревью, переданного оператором, в одну
исходниковую задачу SerialTerminal. Исправить lifecycle и ограничения памяти,
сохраняя recursive missing-list и DATA LINK_FAIL → END → фактические missing holes.
Задача связана с [TODO_042](TODO_042_FT1_BATCHED_FINAL_REPAIR.md); замечания 1–2
затрагивают также recovery/resume workstream
[TODO_041](TODO_041_FT1_FAILURE_RECOVERY_AND_RX_OBSERVABILITY.md).

Оформление этого TODO не запускает исправления, аппаратные прогоны или Git-операции.

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

Требование: bounded replay-history mechanism с явным пределом памяти/entries
и проверенными duplicate/stale semantics. Не хранить каждый child META с начала
передачи бессрочно. Устранение ROOT leak само по себе не решает рост live ROOT.

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

В scope: все шесть findings, regression tests для пяти конкретных repro,
bounded design и stress test processed history, согласование актуальной
recovery/recursive документации и подготовка повторного ревью.

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

## Known limitations

Repro ещё не воспроизведены локально в этой задаче. Предел processed history и
точная классификация permanent failure требуют явного design при реализации.
Прежние успешные subsets и hardware smoke не отменяют найденных lifecycle дефектов
и не доказывают пригодность cb891540... к merge.

## Result

Status: OPEN / CRITICAL
Implemented: none; создан task record, runtime не изменён этой задачей.
Validated: только проверка оформления TODO/ссылок; fixes/software/hardware OPEN.
Review: cb891540451df7c864a40d06618213f10235477a — RED / не merge-ready.
Next action: отдельный старт исправлений 3+4+5, затем 1+2 и bounded history 6,
регрессии/stress, полный software gate и повторное независимое ревью.
