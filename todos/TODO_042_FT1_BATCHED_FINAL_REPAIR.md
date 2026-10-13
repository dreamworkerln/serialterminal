# FT1: рекурсивная передача списков пропусков служебными файлами

TODO-ID: TODO_042
Status: OPEN
Priority: CRITICAL
Created: 2026-10-11
Design updated: 2026-10-12, обсуждение и согласование с оператором.
Implementation: PROTOTYPE IMPLEMENTED / REVIEW AND BROAD VALIDATION OPEN
Validation: 10 TARGETED CASES PASS / FULL SUITE AND HARDWARE OPEN
Branch: `dev_tui_exp_recursive_missing`
Base checkpoint: `dev_tui@fd94bdeb1fd878e072b0f852b3e8f461d928e3cd` (`point 8 done`).
Docs checkpoint: `991ff0e` (`docs: define recursive FT1 missing-list repair prototype`).
Initial source checkpoint reviewed: `cb891540451df7c864a40d06618213f10235477a`; локальные dirty edits на момент первого ревью не входят в этот checkpoint.
Follow-up source checkpoint reviewed: `8cf689e0edd286ac9e48df9ab3c6990fc1bf0f79`.

## Independent review received — 2026-10-13

Для указанного HEAD ревьюер вынес **RED / не merge-ready; в таком виде в dev_tui не merge'ить**. Все шесть замечаний собраны в отдельном [TODO_043](TODO_043_FT1_RECURSIVE_LIFECYCLE_REVIEW_FIXES.md): atomic RX restore, same-ID quarantine retry, deferred ROOT END, child-ID admission collision, terminal ROOT frame retention и bounded processed history. Recursive repair и DATA LINK_FAIL → END сохраняются. Исправления, регрессии/stress, software gates и повторное ревью предшествуют решению о hardware matrix/merge. TODO_042 остаётся OPEN / CRITICAL; прежние PASS не закрывают эти findings. Внешние subsets 114/98 PASS не являются полным suite PASS или новой локальной validation.

Дополнительное ревью `8cf689e` независимо подтвердило все шесть дефектов;
`recursive.py`, `resumable.py`, `manager.py`, `coordinator.py` не менялись
относительно `cb891540`. Исправления lifecycle не начаты, вердикт остаётся RED.
Ревьюер сообщил 215 PASS для FT1/machine/timing subset, compileall и diff-check
PASS; полный pytest collection падает на 14 modules без pyserial и не считается
PASS. Рост live ROOT history подтверждён 5000 успешными child settlements
с `processed=5000`. Подробности и границы внешнего evidence — в TODO_043;
локально при обновлении документации repro/tests не запускались.

По следующему поручению оператора собственное software ревью ST на `8cf689e`
воспроизвело исходные шесть findings в явно описанных границах и добавило findings
7–14 плюс static follow-ups S1–S2 в TODO_043. Среди новых blockers — повреждение
ROOT frame rejected META, неправильная idle pause и concurrent publication с
overwrite при двух RESULT OK. Полный pytest вне sandbox: 601 PASS; compileall PASS.
Это validation существующего неисправленного HEAD, не PASS исправлений. Вердикт
остаётся RED; implementation, новые регрессии и повторное ревью OPEN.

Descriptive suffix BATCHED_FINAL_REPAIR сохранён как историческое имя файла;
актуальный design — recursive missing, TODO-ID не меняется.

## Purpose

Убрать ограничение полного списка пропусков одним FT1 MISSING. При capacity243
текущий пакет содержит максимум28 диапазонов. Для файла примерно1 МиБ /227 bytes
=4620 чанков даже30 разрозненных дырок, около0.65%, дают repair_too_large.

Для прототипа оператор выбрал переиспользование файлового механизма ST:
полный список дырок передаётся обратно служебным файлом FT1. Если дырки есть
в самом служебном файле, список его дырок тоже передаётся файлом в обратную
сторону. Вложенность ограничена; после доставки нижнего списка чинится его
родитель, затем последовательно возвращаемся к исходному файлу.

Это описание исходного design до implementation. Recursive FT1 v2 prototype
реализован в source checkpoint выше; Result и checkpoints ниже сохраняют историю
validation. Текущие review findings и критерии исправлений находятся в TODO_043.

## Related documents

- [TODO policy](../TODO_MANAGEMENT_POLICY.md).
- [Inventory](../TODO_INVENTORY.md).
- [FILE_TRANSFER.md](../FILE_TRANSFER.md) — текущий FT1 contract.
- [FT1_RESUME.md](../FT1_RESUME.md) — identity, durable state и resume.
- [TODO_029](TODO_029_FILE_TRANSFER_RECONNECT_REPAIR.md) — final repair.
- [TODO_035](TODO_035_FT1_SAME_PROCESS_PAUSE_RESUME.md),
  [TODO_036](TODO_036_FT1_PERSISTENT_RECEIVER_RESUME_STATE.md),
  [TODO_037](TODO_037_FT1_PERSISTENT_SENDER_AND_RESUME_HANDSHAKE.md) — recovery.
- [TODO_041](TODO_041_FT1_FAILURE_RECOVERY_AND_RX_OBSERVABILITY.md) — failure,
  partial и отдельный future FLOW/midstream scope.
- [TODO_038](TODO_038_FT1_REMOTE_PROGRESS_WATCHDOG.md) — отдельный watchdog.
- [TODO_040](TODO_040_CENTRALIZED_SETTINGS_SINGLE_SOURCE.md) — future config layer.

## Исходное поведение до реализации прототипа и границы слоёв

Ниже описан исходный FT1 v1. Текущий recursive v2 и последующие исправления
описаны в Result и implementation checkpoints; старые defaults здесь — история.

- FT1 v1 header:12 bytes, >2sBBQ, transfer_id:uint64. MISSING:type5, затем
  range_count:uint8 и пары start_chunk:uint32/count:uint32, big-endian.
- Индексы с нуля; count обозначает непрерывную длину. Capacity243 даёт28
  диапазонов, не28 чанков. encode_missing требует поместить весь набор;
  receiver после END иначе получает repair_too_large.
- Receiver ST знает число чанков из META и учитывает записанные чанки в
  incoming.received. После корректного END вычисляет отсутствующие индексы.
  MISSING формирует ST, а не прошивка. Полный набор чанков с неверным хэшем
  означает hash failure, а не список отсутствующих чанков.
- Прошивка не знает файлов, FT1, chunk indexes, END или MISSING. Она перевозит
  непрозрачные BINARY USER; CRC/ACK/retry/dedup относятся к радиотранспорту.
- CRC-error USER не передаётся принимающему ST и не подтверждается ACK.
  Передающая прошивка при включённом retry повторяет USER; исчерпание попыток
  сообщает LINK_FAIL и вызывает ошибку ST. Это не обычное успешное завершение
  файла с молча оставленной радио-дыркой.
- LINK_OK подтверждает приём кадра peer firmware. Последующая доставка через
  USB/BLE в ST, обработка и хранение остаются отдельными границами. В прежних
  экспериментах были пропуски после LINK_OK; их точный источник не установлен.
- Sender сейчас выполняет MISSING → DATA → END с max_repair_rounds=8.
  FT defaults: result_timeout3600s, control replay interval30s/max3,
  receiver idle120s; resume handshake3s и local BINARY timeout30s.
  Эти ST defaults не адаптируются к PHY. Радиотайминги прошивки учитывают ToA.
- RESULT(ok=false) уже может остановить sender до END при обнаруженной ошибке
  receiver, например storage failure/cancel. Успех только после полной проверки
  и публикации файла. Потерянный RESULT не гарантирует немедленную остановку.

## Agreed target

### Полный список — служебный файл FT1

Первоначальная передача ROOT идёт A → B. После END, если остаются допустимые
пропуски, B создаёт полный список дырок ROOT и передаёт его как внутренний файл
LIST1 в направлении B → A. ROOT ожидает, его partial и контекст сохраняются.

Если LIST1 дошёл полностью и прошёл проверку, A разбирает список, досылает
запрошенные ROOT DATA и END. B снова проверяет ROOT. При новых/оставшихся дырках
создаётся новый служебный файл списка; при полном приёме ROOT проверяется и
публикуется существующим файловым механизмом.

Если LIST1 неполон, A создаёт LIST2 — список дырок LIST1 — и отправляет A → B.
После полного LIST2 B досылает LIST1. После полного LIST1 A досылает ROOT.

```text
ROOT:  A → B, неполон
LIST1: B → A, дырки ROOT, неполон
LIST2: A → B, дырки LIST1, получен полностью
       B → A, досылка LIST1 + END, LIST1 проверен
       A → B, досылка ROOT + END, ROOT проверен
       B → A, RESULT OK для ROOT
```

Использовать существующие FT1 codec/file DATA, подготовку immutable wire,
проверку хэшей, partial/resume и pipeline. Новый слой оркестрирует связи файлов
и возврат к родителю. Передавать дырки каждого неполного родителя этим способом;
порционные MISSING и отдельная сборка страниц MISSING больше не являются target.

Список должен содержать всю актуальную missing set родителя, а не порцию28.
Сохраняются uint32 start_chunk/count и полный missing_total:uint32 для диагностики
sender. missing_total равен сумме count полного canonical списка; это число
чанков, не диапазонов. Размер списка не ограничивается одним BINARY USER.

Разбирать диапазоны только после полного приёма и проверки служебного файла.
Проверять связь с родителем, границы chunks_total, sorted/non-overlapping/
non-adjacent ranges, длину/count и соответствие missing_total сумме диапазонов.
При нуле дырок проверяется сам родитель; успех не следует только из нулевого
счётчика. Ошибка хэша не позволяет угадывать отсутствующие индексы.

Точные служебные metadata/layout, marker типа файла и version handling закрепить
перед codec implementation. Прежний предложенный layout одного MISSING v2 с
missing_total не является новой спецификацией рекурсивной схемы.

### Identity, повторы и родительские сессии

- У каждого нового служебного файла отдельный transfer_id:uint64 и явная связь
  с непосредственным родителем. Повтор передачи того же списка сохраняет его ID.
- Новый цикл починки создаёт новый служебный файл с новым ID, даже если список
  байт-в-байт совпал с предыдущим. Не спутать это с автоматическим same-file resume.
- ST учитывает обработанные ID списков в контексте операции. Повторно доставленный
  уже обработанный список не запускает досылку и не считается новым циклом.
- Списки и досылки выполняются последовательно. Проверять ожидаемого родителя и
  текущую дочернюю сессию; чужой/старый список не меняет текущий residual progress.
- Отдельную новую систему sequence tokens/PHY RTT/freshness для обычных пакетов
  MISSING не проектируем. Unique child IDs, parent linkage и обработанные ID —
  техническая часть оркестрации, не новый вопрос выбора схемы для оператора.
- Нынешний manager допускает одну активную файловую передачу. Простого вложенного
  start_send недостаточно: parent runtime нужно приостановить, сохранить и дать
  transport ownership дочерней сессии, затем восстановить parent.
- При смене ролей settled tickets/queues не теряются. Ожидания дочернего обмена
  не считаются обычным отсутствием активности родителя и не запускают его старый
  META/END replay параллельно дочерней передаче. Не создавать второй конкурентный
  owner радио/transport или независимый pipeline для каждого уровня.
- Служебные файлы остаются внутренними: не публикуются как обычные пользовательские
  downloads и не выдают успешное завершение ROOT. ROOT завершается единожды.

### Глубина рекурсии: максимум8

ROOT имеет depth0. LIST1 имеет depth1; разрешены служебные уровни1..8.
Если для неполного файла depth8 понадобился бы новый список depth9, вся ROOT
операция завершается file transfer fail с явной причиной recursion_depth_limit.
Пригодный partial ROOT сохраняется по действующему failure/resume contract.
Успешное разворачивание стека возвращает depth к родителю.

Глубина не ограничивает число циклов одного родителя. Последовательно доставленные
новые списки ROOT каждый раз имеют depth1, а не возрастающую глубину.

### Процентный gate: ROOT30%, служебные файлы без процентного gate

Согласован будущий configurable default max_missing_percent=30 для исходного
пользовательского файла. Default реализован в file_transfer/recursive.py и constructor argument max_missing_percent.
Метрика:100*missing_total/chunks_total по чанкам wire-потока; при compression
деноминатор относится к сжатому потоку. Сравнивать без округления процента.

После END ROOT: больше30% → отрицательный RESULT, failed attempt и пригодный
partial; ровно30% допускает repair. Например300/1000 допустимо,301/1000 — отказ.
Если приехало только2% ROOT, отсутствует98%: repair по default не начинается.
Ещё не переданные чанки до END не считаются потерянными. Empty file обрабатывается
без деления на ноль. Следующие END используют актуальный остаток.

Оператор отдельно принял: служебные файлы списков не имеют процентного gate,
их разрешено чинить при любой доле пропусков в пределах остальных ограничений.
Иначе маленький список мог бы прекратить рекурсию из-за потери одного чанка.
Exemption определяется внутренним типом/контекстом, а не произвольным именем файла.

FT defaults сейчас находятся в file_transfer/core.py; централизованный config
слой относится к TODO_040. При реализации сделать одну authoritative ST настройку
и привязку к manager; не дублировать default в firmware/UI/sender/receiver.
Поддержка off/дробных процентов/формат override ещё относится к деталям config
implementation; выбран default30 и exemption служебных файлов.

### Нет прогресса: три завершённых цикла подряд

Оператор принял: каждый ROOT или служебный файл имеет свой счётчик no_progress.
Первый полный проверенный список задаёт исходный остаток и сам не расходует цикл.
Цикл состоит из доставки списка, досылки его родителя и нового END с последующей
сверкой остатка. Во время вложенной починки списка parent cycle ещё не завершён.

```text
Начальный остаток100.
После досылки100 → no_progress1
После досылки100 → no_progress2
После досылки 97 → no_progress0
После досылки 97 → no_progress1
```

Любое уменьшение числа отсутствующих чанков сбрасывает счётчик. Три завершённых
цикла подряд без уменьшения → вся операция failed, причина repair_no_progress,
пригодный partial ROOT сохраняется. Не обнулять parent счётчик из-за успешной
доставки дочернего списка. Duplicate/replayed список не завершает новый цикл.

Receiver считает реально сохранённые уникальные чанки. Sender отражает проверенный
полный список; local LINK_OK и число отправленных DATA не являются этим прогрессом.
Увеличение остатка требует диагностики receiver-state regression/restart, не
считается успешным прогрессом и не сбрасывает счётчик. Проверить отдельный recovery
переход, чтобы старый список не подменял новое состояние.

Порог не зависит от чанков/сек или времени цикла. Медленное продвижение допускается;
минимальная скорость, производная по времени, общий DATA budget3*M0 и фиксированный
лимит8 всех циклов не выбраны. В частности, один новый сохранённый чанк за цикл
сбрасывает no_progress: это согласованная политика прототипа, не обещание верхней
границы общего времени успешной починки.

### Таймауты, радио и отказ

Фиксированный часовой repair deadline не выбран как новый критерий этой схемы.
Старые ST defaults документированы выше, но не выдаются за адаптивную модель.
Не добавлять расчёт LoRa ToA/RTT, новый радио-ACK, собственные RF retries,
обязательные паузы между циклами или отдельную систему доставки запросов в ST.
Радиодоставка остаётся прошивке; дальнейший LoRa-SACK — отдельная firmware работа.

Существующие ошибки транспорта, отключение, ограниченные локальные ожидания и
cancel сохраняют значение. Если USB/BLE отвалился, ST может не получить даже END
и не сформировать список: это failure/recovery, а не завершённый no-progress cycle.
При реализации определить корректную фазовую привязку существующих deadlines к
parent/child; не оставлять старый восьмираундовый/часовой budget скрытым пределом
всей рекурсивной операции. Не ослаблять local ownership settlement и queue bounds.

Отрицательный RESULT остаётся способом сообщения ошибки FT1. Доставленный отказ
останавливает новые DATA; уже находящиеся в обработке tickets учитываются до
release. Failure дочерней передачи/исчерпание лимитов завершают ROOT с указанием
parent/depth/cause. Explicit cancel отменяет всю операцию с сохранением действующего
cancel contract; не обещать resumable bytes после разрушительного receiver cancel.

Не добавлять постоянный negative tombstone, запрещающий последующий same-ID ROOT
resume. Старый cached RESULT не должен завершать новую попытку. Проверить existing
failure/recovery semantics; отдельный attempt-token protocol не согласован и не
требуется этим docs-only шагом. Hash-invalid bytes остаются quarantine по contract.

## Scope, invariants and implementation details

- Host-side orchestration, service-file metadata/list codec, final repair после END,
  sender-visible остаток, depth8/no_progress3/ROOT30%, tests и документация.
- uint32 индексы/длины; stable ROOT identity, immutable prepared wire и source/META
  checks сохраняются. Обратная совместимость со старым FT1 не требуется; оба ST
  обновляются вместе. Version/layout и reject mismatch явно специфицировать.
- Firmware source/радиопротокол не меняются, flashing не требуется для этого scope.
- ROOT успех только после полного набора, wire/original SHA256, decompression при
  необходимости, atomic publication и durable completion. Успех LIST не равен ROOT OK.
- Точные encoding metadata, организация контекста и обработанных ID, внутреннее
  хранение/cleanup, API/UI представление являются деталями реализации.
- Recovery после restart должен быть безопасным: специфицировать сохранение связи
  parent/child либо bounded остановку внутренних сессий с явным ROOT resume по
  durable partial. Нельзя обещать уже реализованный persistent recursive stack.
- Midstream repair, FLOW/CAPS/FT1 QUERY, application watchdog, LoRa-SACK, расширение
  BINARY capacity и порционные MISSING остаются вне выбранного scope.

## Branch, merge and evidence workflow

1. По отдельному поручению оператора создана dev_tui_exp_recursive_missing от
   fd94bdeb1fd878e072b0f852b3e8f461d928e3cd. Текущие незакоммиченные документы
   перенесены при switch. Этот шаг правит только TODO/inventory, не runtime.
2. Implementation/validation вести в этой branch. Сохранить точные ST checkpoints
   и firmware digest перед аппаратными прогонами. Код запускать по отдельному
   старту implementation; этот docs task не запускает tests на радио/commit/push.
3. После принятия software/hardware gates выполнить обычный merge в dev_tui по
   поручению оператора, проверить resulting source и required regression/CI.
4. Сырые ST/HCI логи остаются вне Git в
   `/home/dream/coding/журнал экспериментов/TODO_042/`; путь пока планируемый.
   Старые stage8 bundles/hashes не редактировать и не выдавать за новую validation.
   Repo хранит code/tests/harness/parser/TODO и ссылки на evidence с digests.
5. Для run фиксировать UTC, branch/commit/dirty diff digest, source/runtime freeze,
   FW digest, file/compression/PHY/topology, fault injection, ROOT/child IDs и parents,
   depth, missing_total trajectory, no_progress, outcome, все три finalized ST logs.
   Каждый glitch имеет отдельную папку с описанием, логами, fixture и manifest.
6. Python high-level harness и streaming parser подготовить до matrix. Журналы
   не переключаются с веткой; многомегабайтные raw logs в Git не добавляются.
7. feat/ft1-batched-final-repair оставлена по указанию оператора; разработка там
   не ведётся. Промежуточное имя dev_tui_exp_multi_missing заменено до создания.

## Implementation checklist

- [ ] Закрепить service metadata/list format, version handling и parent association.
- [ ] Переиспользовать FT1 file engine для полного списка без предела28 ranges;
  explicit new child IDs, stable replay IDs, validated missing_total и uint32 ranges.
- [ ] Реализовать последовательный stack parent/child, suspend/restore и ownership;
  не запускать конкурирующие parent replay/worker/pipeline.
- [ ] Реализовать depth0..8 и propagation recursion_depth_limit до ROOT.
- [ ] Реализовать no_progress3 отдельно для каждого файла с reset на уменьшение;
  не считать duplicate и вложенную доставку списка новым parent cycle.
- [ ] Подключить будущий ROOT default30% и exemption внутренних service files.
- [ ] Отображать ROOT и repair остаток; внутренние файлы не публиковать пользователю.
- [ ] Проверить cancel, negative RESULT, LINK_FAIL, local disconnect/settlement,
  hash failure/quarantine и safe resume; определить restart semantics стека.
- [ ] Обновить FILE_TRANSFER/FT1_RESUME/AGENT_API/agent skill по реально
  реализованным semantics; сохранять generic profile segregation.
- [ ] Подготовить воспроизводимые harness/parser перед hardware validation.

## Validation checklist

- [ ] Полный список0/1/28/29/80 и >224 ranges, bursts, uint32 boundaries;
  malformed count/total/parent/type/version, hash failure и payload capacity.
- [ ] ROOT→LIST1 без дырок; ROOT→LIST1→LIST2 с обратным разворачиванием;
  depth8 допустим, необходимость depth9 даёт bounded ROOT failure.
- [ ] Повтор файла списка с тем же ID не запускает repair дважды; новый список
  с теми же bytes и новым ID учитывается как новый завершённый cycle.
- [ ] No-progress последовательности100→100→100→100 fail,100→100→97 reset;
  parent counter не меняется от child progress; child failure завершает ROOT.
- [ ] Прогресс по одному чанку допускается без минимальной скорости; разные
  PHY меняют elapsed, но не правила depth/no_progress.
- [ ] ROOT ниже/ровно/выше30%, empty/compressed stream; service file с >30%
  gaps допускает recursive repair. Fixtures >28 ranges соблюдают ROOT gate.
- [ ] ACK-repaired CRC loss не выдаётся за FT1 gap; host-side injected gap
  явно маркируется. Terminal DATA LINK_FAIL допускает переход к END и final
  repair; META/END/control LINK_FAIL остаётся отказом. USB hub loss и UNKNOWN
  требуют отдельного recovery/settlement, а не трактовки как потерянного DATA.
- [ ] Cancel/negative RESULT в initial DATA/repair/child/waiting, late tickets,
  потеря RESULT, same-ID ROOT resume; отсутствие двойной публикации и deadlock.
- [ ] Sender/receiver/both restart на выбранных границах, сохранение пригодного
  ROOT partial и документированный recovery вместо ложного завершения.
- [ ] Relevant regression и полный pytest на exact implementation checkpoint;
  commit/push/CI evidence только если действительно выполнены.
- [ ] На двух нодах >28 isolated ROOT gaps, missing service file, depth/no-progress
  failures и ROOT30% gate; четыре topology, оба направления, SHA256 exact.
- [ ] Измерить clean-file throughput, repair elapsed, service bytes, число циклов,
  depth и control overhead. PHY/files/checkpoints фиксированы; RF retries отдельно.
- [ ] После принятого merge resulting source/regression/required CI checkpoint.

## History and limitations

2026-10-11: TODO начат как DEFERRED wire-preserving batched final repair на
f9c8a8f + working tree. Затем повышен до CRITICAL; обсуждались missing_total:uint32,
порции MISSING, default30% и отказ от backward compatibility.

2026-10-12: оператор выбрал рекурсивную передачу полных списков служебными файлами
FT1 для прототипа вместо порционных MISSING. Глубина максимум8. Предложения
строить в ST новую PHY/RTT/retry систему и универсальный часовой deadline отвергнуты.
Старые portions/v2-layout/time/work-budget checklists заменены текущим design.

После сохранения документов в dev_tui оператор отдельно разрешил создание branch
и её docs edits. Создана dev_tui_exp_recursive_missing. Позднее явно согласованы
exemption service files от ROOT30% gate и три consecutive no-progress cycles,
с отдельным счётчиком каждого файла и reset при любом уменьшении остатка.

Схема ограничивает глубину и циклы без прогресса, но разрешает долгое успешное
продвижение. Точное место post-LINK_OK gaps и LoRa-SACK остаются отдельными работами.
Docs-only checkpoint сохранён в991ff0e. Далее оператор разрешил source implementation
и только targeted smoke, полную software/hardware матрицу оставил Luna medium.

## Result

Status: OPEN / CRITICAL
Implemented: recursive.py policy + META/END v2 codec, coordinator wiring, durable
identity fields и repair snapshot. Исправлена остановка ROOT/служебного файла
на terminal DATA LINK_FAIL: известный исход M1 освобождает ticket, ST продолжает
до END, а receiver запрашивает реальные дыры. META/END/control остаются fail-fast.
Firmware этой ST-правкой не изменена.
Validated: текущие software tests мигрированы на recursive multi missing; 571 pytest tests PASS, compileall и diff-check PASS (2026-10-12). Hardware smoke с новыми timing budgets выполнен: USB↔USB128KiB, по80 разрозненных ROOT holes и потеря DATA списка, успешный depth2/unwind в обе стороны; SF12 CRC/retry/LINK_FAIL и reboot/resume зажурналированы. Полная аппаратная матрица OPEN. Старый point8 evidence не доказывает recursive v2. Luna не запускалась.
Next action: разобрать отдельный firmware/RF SF12 CRC/LINK_FAIL кандидат и согласовать дальнейшую аппаратную матрицу. Текущая ST итерация и её измерения: `/home/dream/coding/журнал экспериментов/ST_TIMING_REVISION_20261012T131217Z/FINAL_REPORT.md`. Промпт:
`/home/dream/coding/журнал экспериментов/Проверка dev_tui_exp_recursive_missing/PROMPT_LUNA_MEDIUM.md`.
Не merge и не объявлять TODO закрытым до принятия результатов.


## Prototype implementation checkpoint — 2026-10-12

Wire VERSION2. META adds parent:uint64/depth:uint8; END adds repair_id:uint64.
Full list MRF2 + parent:uint64 + missing_total:uint32 + range_count:uint32 +
pairs(start:uint32,count:uint32), big-endian, exact20+8*range_count bytes.
Hash-verified child ID привязывает selective pass; stale END игнорируется.
Constructor policies integer ROOT0..100(default30), depth1..8(default8),
no_progress>=1(default3). Нет новой UI/agent config операции.
ROOT external lease, один outbox, serial selective repair, parent waits paused.
Service state internal; root resume fresh context после restart, не persistent stack.
Initial validation boundary: compact-MISSING assertions и fixed-ID fixtures требовали миграции. После последующего указания оператора они мигрированы на актуальные служебные файлы/уникальные child IDs; полный локальный suite 571 PASS. Совместимость v1 не является acceptance target. Аппаратная матрица остаётся отдельной проверкой.

Radio checkpoint: frozen f6a4b797 manifest, BLE→BLE100KiB integrity PASS62.29s
with11 gaps/listdepth1. Reboot100KiB produced34 gaps/19 ranges and service LINK_FAIL;
depth2 not observed. Found shared-dir service TX deleting peer RX part; fixed after
run, new focused regression PASS. Explicit RX-child cancellation and ROOT-scoped
abort also added. Old hardware freeze does not validate those fixes. Evidence:
`Проверка dev_tui_exp_recursive_missing/ПРОБЫ_100КБ_20261011T224333Z/УТОЧНЕНИЕ_РЕЗУЛЬТАТОВ.md`.

SF9/BW250 radio checkpoint ae00b746 manifest: ROOT44/452 isolated holes, LIST1
lost1/1, real LIST2 created(depth2). Driver rebooted LIST2 receiver too; LINK_FAIL
caused ROOT FAIL, so successful unwind pending. Revealed display_snapshot returning
terminal child instead of ROOT; fixed after run, shared-dir regression extended
with ROOT identity assertion and5 focused tests PASS. Source still uncommitted.
Latest operator scope: self-run targeted radio exploration; no Luna. Matrix allowed
after fixes/stability gates. No full coverage campaign claimed.


## DATA LINK_FAIL checkpoint — 2026-10-12

Пользовательская USB→USB передача SF12/BW500 обрывала ROOT на DATA33 до END;
поэтому recursive repair не запускался. Подтверждённый terminal M1 LINK_FAIL
теперь журналируется как binary_send_link_failed с repair_deferred=true и
remote_delivery_confirmed=false. Отсутствие ACK не доказывает отсутствие DATA.
ST не делает немедленный radio retry: после END receiver определяет реальные
дыры. Обработанный pipeline ticket удаляется без discard соседнего ticket.
Это применяется также к DATA служебных списков и selective repair. Прогресс TX
показывает обработанную часть потока; только RESULT OK подтверждает успех файла.

Добавлены11 тестов с настоящим ChatterMachineClient и виртуальными M1 peers:
clean window1/2, lost DATA/lost ACK window1/2, повторная потеря repair DATA,
потеря DATA списка с depth2, permanent loss/no_progress, fatal META/END.
До исправления7 из11 регрессий FAIL, после исправления11 PASS. Targeted suite
59 PASS; полный suite594 PASS (61.072с), без skip/errors. Первый полный прогон
593 PASS/1 FAIL выявил неизолированный BLE-cache test; исправлена его изоляция
через временный cache path, пользовательский cache не менялся.

Это software evidence: физическая причина SF12 no ACK пока не установлена,
новое поведение после этой правки на радио ещё не проверено. Полная аппаратная
матрица и TODO остаются OPEN. Отчёт и RED/GREEN/XML артефакты:
`/home/dream/coding/журнал экспериментов/SF12_USB_NO_ACK_20261012T191332Z/LINK_FAIL_FIX.md`.
