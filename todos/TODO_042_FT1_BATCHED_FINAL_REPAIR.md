# FT1: итоговый repair порциями пропусков

TODO-ID: TODO_042
Status: DEFERRED
Created: 2026-10-11
Design checkpoint: `dev_tui@f9c8a8f0798db362f6c04b7df12de7f53256975a` + экспериментальное рабочее дерево реархитектуры; документационный запрос оператора 2026-10-11.
Implementation: OPEN / NOT STARTED
Validation: OPEN / NOT RUN

## Purpose

Снять ограничение, при котором больше 28 разрозненных диапазонов пропусков после
END нельзя исправить, хотя все накопленные чанки пригодны для докачки. Запрашивать
пропуски последовательными порциями в существующем END/MISSING/RESULT обмене,
сохраняя формат FT1 v1 и итоговую проверку файла.

Работа отложена до отдельного выбора этой задачи оператором после текущих
аппаратных gates реархитектуры и при планировании дальнейших работ LoRa-SACK.
Создание этого TODO не включает реализацию в текущий пункт 8.

## Related documents

- [TODO policy](../TODO_MANAGEMENT_POLICY.md) — правила ведения задачи.
- [Inventory](../TODO_INVENTORY.md) — текущий статус и порядок работ.
- [FILE_TRANSFER.md](../FILE_TRANSFER.md) — FT1 и итоговый repair.
- [FT1_RESUME.md](../FT1_RESUME.md) — identity, durable state и resume.
- [TODO_029](TODO_029_FILE_TRANSFER_RECONNECT_REPAIR.md) — исходный final repair.
- [TODO_035](TODO_035_FT1_SAME_PROCESS_PAUSE_RESUME.md),
  [TODO_036](TODO_036_FT1_PERSISTENT_RECEIVER_RESUME_STATE.md),
  [TODO_037](TODO_037_FT1_PERSISTENT_SENDER_AND_RESUME_HANDSHAKE.md) — recovery/resume.
- [TODO_041](TODO_041_FT1_FAILURE_RECOVERY_AND_RX_OBSERVABILITY.md) — сохранение
  partial при ошибках; его FLOW/CAPS и midstream repair остаются отдельным design.
- [TODO_038](TODO_038_FT1_REMOTE_PROGRESS_WATCHDOG.md) — отдельный будущий watchdog.

## Current behavior

Проверено чтением исходников на указанном checkpoint с рабочими изменениями:

- `protocol.py`: общий header 12 bytes (`>2sBBQ`), количество диапазонов uint8,
  каждый диапазон — `start_chunk:uint32` + `count:uint32`, big-endian (`>II`).
- При BINARY payload capacity 243 один MISSING вмещает
  `floor((243 - 12 - 1) / 8) = 28` диапазонов. Это предел диапазонов, а не общего
  числа чанков: один непрерывный пропуск может содержать много чанков.
- `encode_missing()` требует, чтобы весь переданный набор диапазонов помещался
  в один пакет. Receiver `_handle_end()` строит полный набор; при превышении
  capacity завершает попытку с `repair_too_large`. Пригодный partial сохраняется
  действующим failure/recovery контрактом.
- Sender `_await_remote_completion()` уже обрабатывает цикл MISSING → запрошенные
  DATA → END, но каждый MISSING расходует общий `max_repair_rounds`, по умолчанию 8.
  Есть общий deadline ожидания результата. Пагинация пропусков не реализована.

28 одиночных несмежных пропусков помещаются. 29 таких пропусков уже превышают
текущий предел. Восемь раундов не дают сейчас возможность запросить 224 разных
диапазона: receiver сначала должен закодировать полный список в одном MISSING.

## Target behavior

Выбранное решение: сохранить uint32 и запрашивать пропуски частями. Это снимает
предел полного списка пропусков в одном пакете и не уменьшает допустимый размер
файла переходом на uint16; существующие ограничения FT1 uint32 остаются.
Формат пакетов сохраняется. Это будущая доработка, сейчас её в runtime нет.

Состояние принятых чанков у получателя уже есть. Новые поля в пакете не нужны:
изменить нужно выбор диапазонов и учёт бюджета repair.

После END receiver сообщает одну ограниченную порцию актуальных пропусков.
Sender исправляет её и снова отправляет END. Receiver пересчитывает missing set
и сообщает следующую порцию либо проверяет файл и отвечает RESULT OK.

Пример: 80 одиночных разрозненных пропусков, все repair DATA доставлены:

```text
END → MISSING(28 ranges) → repair DATA → END
    → MISSING(28 ranges) → repair DATA → END
    → MISSING(24 ranges) → repair DATA → END
    → проверка хешей / публикация → RESULT OK
```

Если часть repair DATA опять потеряна, она остаётся в актуальном missing set и
попадает в следующие порции. Сам факт отправки порции не доказывает её приём.

## Scope and non-goals

Scope: host-side FT1 receiver/sender, final repair после END, связанные тесты,
диагностика, документация и политика конечных лимитов.

Не входят: midstream repair, остановка original DATA ради раннего repair,
FLOW/CAPS/FT1 QUERY, remote-progress watchdog, новые wire message types,
одновременная рассылка нескольких MISSING с reassembly, изменение radio ACK,
firmware, payload capacity или замена uint32 на uint16.

## Invariants

- Сохраняются FT1 v1 bytes, uint32 start/count, stable transfer_id, chunk indices,
  META identity и prepared wire SHA-256; firmware остаётся opaque transport.
- Каждый MISSING самостоятельно декодируется, содержит отсортированные,
  несмежные и непересекающиеся корректные диапазоны в пределах chunks_total.
- Размер порции вычисляется из фактической payload capacity, а не hardcoded 28.
- RESULT OK разрешён только после полного приёма, wire/original SHA-256,
  необходимой распаковки и атомарной публикации; tombstone предотвращает повторную
  публикацию после lost RESULT.
- При timeout, лимите, disconnect или cancel пригодные partial/journal сохраняются
  согласно действующему recovery контракту. Cancel/close остаются отзывчивыми.
- Все очереди, число повторов, время работы и размер диагностик ограничены.
  Старая/дублированная MISSING не даёт бесконечно продлевать deadline.

## Design

Receiver после каждого корректного END строит canonical missing ranges и выбирает
первую порцию, помещающуюся в один MISSING. Остальные пропуски остаются в bitmap;
хранить многопакетный список или собирать страницы по сети не требуется. Новая
порция определяется заново после следующего END, с учётом реально принятых DATA.
Полный приём запускает существующую finalization.

Sender сохраняет существующий один repair loop и DATA pipeline. Получив порцию,
валидирует transfer_id/ranges, отправляет только запрошенные чанки и повторяет END.
Не запускать новый sender worker и не возобновлять original stream с нулевого чанка.

Пересмотреть `max_repair_rounds=8`: число успешно обслуженных порций большого
missing set не должно само по себе исчерпывать лимит восстановления. Разделить
бюджет нормальных порций и бюджет повторов без подтверждённого прогресса; оставить
конечный общий deadline/объём работы. Точные пределы и способ доказательства
прогресса определить и закрепить тестами перед реализацией. Local LINK_OK и
уменьшение произвольной порции не являются доказательством уменьшения всего
missing set. В legacy wire нет sequence/page token: delayed/duplicate MISSING
могут приводить к безопасной повторной передаче, но не к ложному прогрессу или
неограниченному циклу. Повторно теряемая первая порция должна завершаться bounded
failure, а не навсегда блокировать остальные пропуски.

Wire compatibility не означает одинаковые возможности peers: старый sender всё
ещё ограничен восемью раундами, старый receiver требует full-set MISSING. New/new
должен поддерживать много порций; new/old и old/new должны сохранять ограниченное,
наблюдаемое поведение и partial. Не обещать снятие лимита 28 для старого receiver
или гарантированное завершение >8 порций со старым sender. Если потребуется
negotiation для более сильных гарантий, это отдельное согласование scope.

uint16 не выбран: замена обоих полей дала бы 57 диапазонов при capacity 243,
но меняет wire encoding и ограничивает представимые индексы/длины. Порции решают
ограничение количества диапазонов с сохранением нынешнего пространства uint32.

## Implementation

- [ ] Зафиксировать лимиты порций, повторов без прогресса, общий deadline и
  правила обработки stale/duplicate MISSING без новых wire fields.
- [ ] Выбирать bounded canonical portion на receiver после END без отказа только
  из-за большого полного missing set; сохранять остальные bitmap gaps.
- [ ] Адаптировать sender repair budget и diagnostics, сохранив один loop,
  deadline, pipeline, cancel и отрицательный RESULT.
- [ ] Сверить normal repair, same-transfer resume, process/controller recovery,
  late DATA, duplicate END и completed tombstones с FT1_RESUME.
- [ ] Обновить FILE_TRANSFER, FT1_RESUME, AGENT_API и agent skill по реально
  реализованной семантике; синхронизировать TODO_029/041 и inventory.

## Validation

- [ ] Автоматически проверить 0/1/28/29/80 isolated ranges, >224 ranges и
  contiguous bursts; capacity-dependent границы и uint32 boundary values.
- [ ] Проверить потери DATA во время repair, lost MISSING/END/RESULT,
  duplicate/reordered/delayed control и повторный запрос той же порции.
- [ ] Проверить bounded no-progress failure, общий deadline, отрицательный RESULT
  и responsive cancel без удаления пригодных partial/journal.
- [ ] Проверить restart sender/receiver/both между порциями, controller recovery,
  same transfer identity, точный итоговый hash и единственную публикацию.
- [ ] Проверить new/new, new/old и old/new, включая старый лимит восьми раундов;
  existing codec vectors остаются byte-for-byte совместимыми.
- [ ] Выполнить relevant regression и полный pytest на точном implementation
  checkpoint; отдельно записать commit/CI результаты, если выполнялись.
- [ ] На двух нодах проверить >28 isolated ranges управляемой host-side инъекцией
  (явно пометить её), repair-on-repair и итоговый SHA-256; четыре топологии и оба
  направления. Не выдавать обычный удачный RF прогон за проверку >28 ranges.
- [ ] Измерить elapsed time, useful throughput, число порций/повторов и overhead
  относительно того же PHY/transport/размера файла без пропусков.

## Findings and known limitations

Это последовательная обработка порций, а не несколько пакетов одного составного
MISSING и не midstream repair. Потеря большого количества DATA до END всё ещё
обнаруживается в final repair; задача не доказывает живость remote ST во время
original stream. Конечные бюджеты означают, что постоянные потери могут завершить
попытку с ошибкой и сохранённым resumable state.

TODO_041 уже описывает будущий более широкий early repair. Этот TODO выделяет
самостоятельную доработку legacy final repair; при будущей реализации early repair
нужно переиспользовать согласованную политику порций/лимитов и не создавать
конкурирующие repair loops. Наличие обоих документов не включает early repair.

## Result

Status: DEFERRED
Implemented: отсутствует.
Validated: runtime tests и hardware validation этой функции не выполнялись.
Docs-only checkpoint: 2026-10-11, новый TODO и запись в inventory поверх указанного
HEAD с существующим dirty tree; отдельный commit/push/CI не выполнялись.
Next action: после завершения текущих gates отдельно выбрать TODO_042 для
реализации и сначала утвердить конечные budgets/compatibility contract.
