# Chatter + SerialTerminal: порядок выполнения архитектурных исправлений

Дата: 11 октября 2026, Europe/Moscow.
Статус: экспериментальная реализация; этапы 1–7 реализованы и проверяются локально.
Этап 4 перепроверен; аппаратная приёмка новой machine-реализации и линия R открыты.
Область: оба проекта — Chatter firmware и SerialTerminal.

Основание: [ARCHITECTURE_REPAIR_PLAN_2026-10-11.md](ARCHITECTURE_REPAIR_PLAN_2026-10-11.md).
Исходный аналитический документ сохраняется без изменений. Настоящий файл уточняет
порядок реализации, зависимости и критерии завершения; он не заменяет анализ,
тематические TODO, их inventory или authoritative handoff.

## 1. Исходное состояние и границы доказательств

При подготовке этого файла проверены текущие ветки, HEAD и рабочие деревья:

| Проект | Каталог | Ветка | Наблюдаемый HEAD |
|---|---|---|---|
| Chatter | `/home/dream/coding/c++/lora-sack` | `dev_chat_binary` | `556898a19d588411f9ee39f2e09b89f89784ed23` |
| SerialTerminal | `/home/dream/coding/python/serialterminal` | `dev_tui` | `71cb23c6bad337da03b67a9c812f49890e1e54b5` |

Оба рабочих дерева были чистыми до создания этого файла. Эти SHA фиксируют
наблюдаемое состояние, но не означают, что baseline проверен тестами или принят
по результатам аппаратных испытаний. Они новее SHA, приведённых в исходном анализе.

При составлении порядка работ исходники повторно не анализировались; актуальность
каждого описанного дефекта требуется проверить перед соответствующим исправлением.
Сборки, тесты, fault injection, аппаратные подключения и flashing не выполнялись.
Наличие дефекта в аналитическом документе не означает, что он обязательно остаётся
в текущем HEAD.

Перед началом каждой задачи нужно установить её точную pre-change base revision,
проверить локальные изменения и прочитать применимые инструкции проекта. Начальные
SHA этого плана не подменяют base последующих этапов.

## 2. Сохраняемые ограничения

- Существующие LoRa USER/ACK и FT1 v1 остаются; текущая серия не реализует batch/SACK.
- Нормальный DATA-путь не получает новых служебных радиопакетов.
- Сохраняются capacity BINARY USER 243 байта и FT1 DATA до 227 байт.
- Firmware не получает знания о файлах, transfer_id, chunk_index и durable bitmap.
- RF ACK означает приём радиотранзакции peer node, а не сохранение файла remote ST.
- Session written, firmware queue accepted, physical TX outcome, link outcome и
  durable remote progress имеют разные значения.
- Существующее ограниченное radio recovery сохраняется; ST не строит вторую
  лестницу автоматического восстановления радио и не делает автоматический reboot
  по отсутствию remote progress.
- FLOW/CAPS/QUERY, DATA_CHECKED и расширение pipeline window отложены.
- Native tests и успешная сборка не подменяют аппаратную приёмку.

## 3. Выбранная последовательность

| Этап | Владелец | Соответствие исходному плану | Зависимость | Статус |
|---|---|---|---|---|
| 0 | Оба проекта | Проверка текущего baseline, FW-1 | Перед изменениями | Baseline build/native и host pytest проверены; hardware открыт |
| 1 | ST | ST-1, защита workers из ST-6, deadlines из ST-4 | 0 | Реализован; local tests PASS |
| 2 | ST | ST-2, ST-3, согласованность RESULT decoder из ST-5 | 1 для учёта outstanding операций | Реализован; local tests PASS |
| 3 | ST | Immutable source и durable cursor из ST-4; ST-5 | 1–2 | Реализован; local tests PASS |
| 4 | ST | Остальная часть ST-4: resume и bounded replay | 1–3 | Реализован `f9c8a8f`; 494 local tests PASS, restart hardware частично BLOCKED |
| 5 | Chatter + ST | Спецификация FW-2 и FW-3/ST-7 | Уточнённые исходы и ownership из 1–4 | Shared exact contract + golden vectors, local PASS |
| 6 | ST | Остальная часть ST-6: scheduling и bounded outbox | 1–5 | Один coordinator, bounded queues/outbox; 530 host tests PASS |
| 7 | Chatter + ST | Реализация FW-2 и FW-3/ST-7 | 5–6 | Protected codec/session/FW/client реализованы; native/build PASS, hardware открыт |
| 8 | Оба проекта | Аппаратные gates и матрица TODO_013 | 7 и стабильное радио | Baseline USB→USB/BLE→BLE PASS; новая матрица открыта |
| R | Chatter | FW-4, диагностика silent-deaf RX | 0; независимая линия | Диагностические readback расширены; причина/physical gate открыты |

Это порядок завершения этапов, а не требование выполнять весь этап одним коммитом.
Независимый небольшой fix можно завершить раньше, если он не нарушает зависимости.
FW-4 можно исследовать независимо от ST fixes; нестабильное радио блокирует итоговую
аппаратную приёмку и измерение производительности.

## 4. Этап 0 — установить актуальный baseline

1. Сопоставить текущие изменения с ревизиями исходного анализа и выяснить, какие
   выводы ещё актуальны. Сохранить пользовательские локальные изменения.
2. Установить current-state TODO_012/016/017: уже реализованное recovery,
   существующие проверки и оставшиеся hardware gates. Не повторять завершённую работу.
3. Выполнить применимые baseline-проверки по инструкциям каждого репозитория;
   отдельно зафиксировать существующие failures и warnings.
4. Уточнить необходимые обновления TODO_041 и ссылок на общий план; historical
   design не удалять, задачи без реализации не закрывать.

Критерий завершения: установлены точные исходные ревизии, актуальные дефекты,
существующая программная база recovery и ограничения baseline evidence.

## 5. Этап 1 — исходы отправок и устойчивость workers

Порядок небольших изменений:

1. Нормализация backend errors, включая termios.error; контроль short write.
2. Различение доказанного отсутствия записи и возможной записи. После возможной
   записи — unknown без слепого generic replay.
3. Наблюдаемый исход для каждого принятого tx_id; неожиданный выход TX worker
   завершает или приостанавливает зависимые операции с видимой причиной.
4. Адресное снятие ещё не начатой отправки и drain/fence собственных операций;
   lease не освобождается через простую очистку correlation deque.
5. Защита RX worker и idle sweep; исключения callback/storage получают событие
   и определённый исход transfer.
6. Общий monotonic deadline: вложенные ожидания получают остаток времени.
   Протягивать этот контракт в изменяемые recovery paths на последующих этапах.

Generic session владеет queued/writing/written/unknown; Chatter-specific outcomes
и FT1 replay policy остаются выше этой границы.

До нового machine interface host-side fence не доказывает завершение firmware
queue или RF операции. Если legacy echo не даёт достаточного доказательства,
состояние остаётся явно неопределённым; безопасный replay не обещается.

Критерий завершения: short/partial write, flush failure и worker exception не
оставляют принятую операцию без наблюдаемого исхода; чужие отправки не отменяются;
общий deadline ограничивает изменённые пути ожидания.

## 6. Этап 2 — сохранить partial и остановить отправку после отказа

Сначала ST-2:

- Bad DATA length/index и некорректный END отвергают сообщение, сохраняя хорошие chunks.
- Идентичный duplicate — идемпотентный no-op.
- Конфликт разных bytes одного index — suspend/quarantine с причиной; не выбирать
  автоматически последнюю копию и не считать сомнительный bitmap durable evidence.
- Ошибка MISSING, idle/recovery timeout и repair_limit не удаляют пригодный partial.
- При неудачном старте cleanup касается только файлов, созданных самой операцией.
- Ошибка storage останавливает продвижение durable state; explicit cancel получает
  отдельный документированный cleanup-контракт.

Затем ST-3:

- Remote terminal outcome будит coordinator отдельным событием.
- Проверять его перед каждой новой submission и после wait/recovery в original,
  pipeline и repair paths.
- Уже выданные операции учитывать bounded способом через этап 1.
- Remote failure не превращать в cancel_event или /cancel all.
- RESULT decoder отвергает противоречие ok=True и failure code без новых wire bytes.

Критерий завершения: проверены сохранность partial для перечисленных ошибок,
ownership cleanup и остановка новых DATA во всех путях после negative RESULT.
При legacy MISSING сохраняется лимит 28 ranges; превышение сообщает repair_limit
и оставляет возможность явно определённого resume, без скрытого дробления full-set.

## 7. Этап 3 — неизменные bytes и durable завершение

Внутренний порядок:

1. Immutable snapshot/spool prepared wire representation, включая Compression.NONE;
   исходный пользовательский файл не перечитывается как неизменный wire source.
2. Durable map/checkpoint; active-META RESUME использует durable map либо следует
   только после успешного checkpoint.
3. Crash-recoverable публикация с одним выбранным destination:

```text
проверить hashes и размеры
→ подготовить и fsync окончательные bytes
→ сохранить durable publishing intent с выбранным destination
→ атомарно опубликовать destination
→ fsync каталога destination
→ сохранить durable completed tombstone
→ отправить RESULT OK
→ очистить больше не нужный partial/manifest
```

Критерий завершения: изменение исходного файла не меняет prepared bytes; отказ
checkpoint не создаёт ложного RESUME cursor. Fault injection на границах публикации
показывает восстановление без второй публикации и без раннего RESULT OK.
Ограничения файловой системы и модели crash должны быть явно описаны; simulated
fault injection не объявляется физическим испытанием отключения питания.

Причина порядка: resume должен опираться на устойчивую identity и однозначное
состояние уже опубликованного файла.

## 8. Этап 4 — same-ID resume и конечное восстановление

- Same-ID resume после failed attempt в том же процессе и после restart.
- Атомарные restore/revive, claim lease и смена active_id с rollback при отказе.
- Resume проверяет immutable representation из этапа 3.
- Bounded recovery потерянных echo/MISSING/RESULT использует общий deadline.
- Replay допускается только для идемпотентного FT1 сообщения с прежними bytes/id/index
  после учёта судьбы предыдущей операции.
- Не расширять recoverable set всех timeout/rejection без анализа queues и ownership.

Критерий завершения: same-process и process-restart resume сохраняют identity;
lost echo после реальной доставки не вызывает бесконтрольного накопления tickets.
Неопределённость, которую legacy interface не позволяет разрешить, приводит к
видимому unknown/suspend, а не к заявлению об успешном восстановлении.

## 9. Этап 5 — закрепить локальный machine contract

До реализации подготовить небольшой общий контракт для двух проектов:

- Точный encoding, version, epoch/request identity, types, lengths и checksum.
- Ограничения размера frame, delimiter и bounded resynchronization.
- Ownership USB/BLE machine session, её reconnect/restart и outstanding submissions.
- Значение queue accepted, physical TX outcome, link outcome, rejection и unavailable.
- Реальная ёмкость admission, резервирование и момент возврата credit; окно остаётся 2.
- Правила обработки старых epochs, corruption, overflow и состояния unknown.
- Машинный путь независимо от /chat, /tele и /both.
- Локальное согласование версии, human terminal и явные legacy limitations.
- Общие test vectors для codec/parser обеих реализаций.

Размеры полей, checksum algorithm и команды здесь намеренно не фиксируются:
исходный документ требует отдельного точного контракта до реализации. К этому
этапу нужно разрешить семантические решения, которые нельзя вывести из существующих
требований, а затем закрепить согласованный контракт.

Критерий завершения: обе стороны могут реализовать один и тот же формат и lifecycle
без самостоятельного выбора противоречащих semantics; FT1 и radio bytes не меняются.

## 10. Этап 6 — один владелец FT1 scheduling

После стабилизации поведения переносить владельцев состояния по одному:

1. Bounded outbound lane/outbox; RX worker не ждёт transport/RF отправки ответа.
2. Ограниченные RX/control queues; overflow имеет видимый исход.
3. Один coordinator вместо дальнейшего наращивания manager inheritance.
4. Отделённые sender/receiver state, immutable source, durable store и codec.
5. Инкрементальный учёт received bytes вместо O(n) sum на каждом DATA.

Не создавать thread на каждый RESULT. Сложное дерево интервалов и универсальная
ARQ/HAL система не являются предварительным условием этого этапа.

Критерий завершения: bounded память и отсутствие transport waits в RX path;
проверки этапов 1–4 сохраняют результаты после каждого структурного переноса.

## 11. Этап 7 — firmware machine path и адаптер ST

Порядок интеграции:

1. Firmware: typed BINARY RX/TX/status events и bounded очереди полных сообщений.
   Human presentation становится отдельным потребителем; Scheduler не блокируется
   на host output.
2. Firmware: machine ownership/epoch, адресные outcomes, реальный admission credit.
   Сохраняются drops/high-water counters; short USB writes и BLE timeout/stale drops
   учитываются даже при переполненной output queue.
3. Firmware: защищённое framing в обе стороны и bounded resynchronization.
   Corrupt frame целиком отвергается; его хвост не превращается в обычный RF USER.
4. ST: codec, correlation и lifecycle нового Chatter adapter; учёт старого epoch,
   reconnect, unavailable и обновление recovery paths с использованием новых outcomes.
5. Совместные contract tests и интеграционная проверка обоих направлений.

Локальная оболочка снимается до radio USER и заново создаётся принимающей нодой.
Firmware не интерпретирует FT1; RF RX/ACK сохраняет приоритет. Queue acceptance
не считается link delivery, а link ACK не считается durable remote progress.

Критерий завершения: corruption, truncation, склейка, потеря delimiter, reconnect,
stale epoch, конкурирующие USB/BLE sessions и queue overflow дают определённый исход.
Machine channel работает во всех output modes; текущие USER/ACK, dedup, retry limits
и recovery correlation сохранены.

## 12. Независимая линия R — silent-deaf RX

После этапа 0 можно начать FW-4 независимо от ST fixes:

- Расширить before/after snapshots на transitions/errors.
- Разделять SPI/digital liveness, проверку RX entry registers и реальный peer RX.
- Проверить RX-only restart до собственного TX и известный peer frame;
  сравнить BW500 с BW250/125.
- RX errata RadioLib считать диагностическим кандидатом, пока причина не доказана.
- Исправлять установленную причину узким изменением, сохраняя existing recovery.

Не делать reset только из-за отсутствия трафика; не вводить регулярные RF probes.
RADIO_UNAVAILABLE остаётся терминальным до явного operator recovery.

Критерий завершения: результат подкреплён отдельным аппаратным evidence либо
гипотеза честно остаётся открытой. Без стабильного радио performance acceptance
не выполняется.

## 13. Этап 8 — аппаратная приёмка и производительность

Порядок завершения аппаратных gates:

1. Существующие recovery contracts TODO_012/016/017, reset recovery TODO_014,
   BLE reconnect и RX acceptance TODO_015.
2. Корректность и recovery в четырёх сочетаниях transport на концах:
   USB→USB, USB→BLE, BLE→USB, BLE→BLE.
3. Производительность TODO_013 после принятия стабильного baseline.

Для BLE измерений требуется учитывать competing host Bluetooth audio; sustained
аудиопоток отключается до measured run по operating contract аппаратного исполнителя.
BLE flapping требует отделить environmental factor от firmware failure.

Сравнивать original bytes / полное время при одинаковых файле, compression, PHY
и topology. Отдельно учитывать retries и wall-clock ожидания; подтверждать отсутствие
новых обязательных FT1 control messages на нормальном DATA-пути.

Native и physical acceptance учитываются отдельно. Run-specific executor prompts
готовятся в чате; этот файл хранит только устойчивые criteria и порядок gates.

## 14. Завершение этапов и связь с существующим учётом

Каждый этап делится на небольшие изменения с проверками изменённого и соседнего
поведения. Перед source changes нужен принятый base; для Chatter обязательны review
всех удалений, контроль сохранности functions/branches и проверка полного diff по
правилам AGENTS.md. После разрешённого commit подтверждается совпадение committed
результата с reviewed diff; CI проверяется по правилам проекта.

При изменении поведения проверять актуальность README, ARCHITECTURE, соответствующих
TODO/inventory, durable recovery state и agent/test contracts. Обновлять только
артефакты, чья документированная истина изменилась.

- ST TODO_041: этапы 1–4 и 6; FLOW extension остаётся отдельным deferred-направлением.
- Chatter TODO_012/016/017: сохранение реализованной основы и оставшиеся hardware gates.
- Chatter TODO_014: actual reset recovery после ST fixes.
- Chatter TODO_015: silent-deaf RX и BLE reconnect acceptance.
- Chatter TODO_013: performance на принятом baseline.
- Новый machine contract: совместная отдельная задача двух проектов.

Для checkpoint фиксировать revisions обоих компонентов, реально выполненные checks,
результаты, limitations и оставшиеся hardware gates. Завершение реализации не
объявляется аппаратным PASS. Этот план не даёт отдельного разрешения на commit,
push, flashing или запуск аппаратных сценариев.

Первая реализационная задача: этап 1 — ST-1 вместе с защитой workers и общими deadlines.

## 15. Текущий checkpoint реализации — 2026-10-11

Демаркационные коммиты: Chatter `2d8723caf2c294f3281093797bf61050acb9a36e`,
SerialTerminal `b7f58f83760091dd68678bececa260205467fe0a`. Firmware source не менялся;
Этапы 1–3 SerialTerminal сохранены локальным коммитом
`6da12fe0e0bcba334a425a196c7a746ecada915c` на ветке `dev_tui`.
Этот checkpoint Chatter содержит только обновление execution plan; firmware code
совпадает с демаркационным baseline. Push и аппаратные проверки не выполнялись.

Baseline evidence:

- Host на точном demarcation SHA через изолированный `git archive`: 427 pytest PASS.
- Запуск с пользовательским BLE cache выявил внешнюю зависимость одного CLI test;
  повторные проверки используют временный `SERIALTERMINAL_CACHE_FILE`, не меняют cache.
- Chatter `pio run -e esp32-s3-n16r8`: PASS, RAM 50164 bytes, flash 1083309 bytes.
- `ci/run_local_ci.sh --stage native-composed-recovery`: оба native сценария PASS.
- Hardware, flashing, CI на удалённом сервере не выполнялись.

Этапы 1–2: итоговый локальный полный прогон 462 pytest PASS. Проверены uncertain
serial writes, worker exit, owned cancel/drain, общие deadlines, сохранность partial
и quarantine, отрицательный RESULT в original/pipeline/repair, MISSING overflow
без скрытой pagination. Локальный drain ограничен 10 s; firmware/RF fence этим не
доказывается. `compileall` прошёл; отдельный `ruff` недоступен в окружении.

Этап 3: полный host pytest — 477 PASS. Raw/gzip snapshots исключают повторное
чтение изменяемого source; restart пересоздаёт snapshot и проверяет wire identity
по journal. Active-META RESUME следует только после checkpoint. Проверены
прерывания bytes/intent/rename/directory/tombstone/RESULT для NONE и GZIP,
восстановление одного destination, отсутствие раннего OK и повторной публикации.
POSIX fsync failure останавливает commit; non-POSIX directory fallback остаётся
best effort. Это simulated fault injection, не физическое отключение питания.

Этапы 4–8 и линия R ещё не приняты. Midstream repair отсутствует в scope этой серии:
repair остаётся END → MISSING → DATA. FLOW/CAPS/QUERY по-прежнему отложены.
Исходный `ARCHITECTURE_REPAIR_PLAN_2026-10-11.md` не изменялся.

## 16. Продолжение экспериментальной реализации — 2026-10-11

Авторизация оператора: продолжить этап 4 и далее для обоих проектов, подключённые
нодовые испытания; вести отдельный журнал каждого неожиданного сбоя. Source bases:
ST `f9c8a8f0798db362f6c04b7df12de7f53256975a`, Chatter
`22edc704f1f6f7c2916d42bdc0dfedcef6ea5d3c`. Новые изменения пока не закоммичены.
Исторический checkpoint раздела 15 сохранён как исходное состояние, не current claim.

- Этап 4: 494 pytest PASS. Frozen-runtime BLE→BLE и USB→USB 8 KiB: exact bytes/SHA,
  по одному destination. Sender-process SIGKILL сохранил journal/receiver partial;
  возобновление через BLE BLOCKED на discovery при stale host connection. Это
  ограничение physical evidence, не доказанный RF failure или PASS persistent resume.
- Этап 5: одинаковый `CHATTER_MACHINE_PROTOCOL_V1.md` в обоих проектах; CRC,
  canonical base64, bounded resync, epoch/request, two-slot credit, cached local QUERY.
  QUERY не является отложенным FT1 FLOW/CAPS/QUERY и не добавляет radio packets.
- Этап 6: один coordinator вместо цепочки manager inheritance; сохранены policy
  functions. Bounded outbox/RX/control, nonblocking RX controls, incremental unique
  DATA byte accounting, discard/terminal shutdown и retained ownership при unknown.
- Этап 7: FW typed metadata проходит только local queues и снимается перед radio;
  logical ACK/retry/dedup/recovery сохранены. Machine output независим от human mode.
  Host выбирает legacy только по явному old-firmware rejection; unknown/lost outcome
  не вызывает blind SUBMIT replay. Full host pytest 543 PASS, isolated cache.
- R: snapshots расширены; RX-only before/after и recovery journal сохраняют cfg,
  detect, 0x36/0x3A, FRF. Нет corrective writes или новой recovery ladder.
- Native codec/session, composed recovery/RX restart, protocol, SPI и policy PASS.
  `pio check` PASS с предупреждениями; Lizard threshold warnings остаются, включая
  новые Session.admit / machine dispatcher / parser branches. CI не запускался.

Hardware evidence и новые сбои хранятся в `/home/dream/coding/журнал экспериментов`:
отдельный каталог на сбой, описание и неизменённые ST `.log`/`.console.log`.
Wrong-baud test classified as executor setup error; corrupted bootstrap USER cause
remains a hypothesis. Exact raw bytes недоступны в старых default-redacted logs;
новые forensic runs должны сохранять base64 explicitly.

На frozen v3 (host manifest `5ab64ed5…`) новая image `c430201a…` проверена на обеих
нодах. USB→USB и USB→BLE 8/64 KiB: exact bytes/SHA, NONE, one final publication.
BLE→USB 8 KiB также exact, но с 29 s локальным outcome stall и одним QUERY;
оставшиеся BLE-sender points тогда остановлены. `/tele` на обеих нодах не мешал
USB8KiB; ordinary idle human USER/ACK в двух направлениях PASS. Aggregate output
counters росли, все observed parse/corrupt=0; источник конкретных drops не доказан.
Это application correctness evidence, не clean-output или full performance acceptance.

Host v4 (`9480ee24449342b6c02f83b19d49cc055fa5a693ec7ef348dd38537e88b780c8`)
добавляет startup-after-durable-store ordering, bounded outcome drain и ранний
same-request QUERY при full-credit STATUS для принятого ticket до обработанного
request ID. Grace100ms позволяет доставить соседний outcome; STATUS сам не является
успехом. Нет повторного SUBMIT, midstream RF repair или обязательного QUERY на обычном
DATA. 542 pytest PASS/46.56s, compileall/diffcheck PASS; v4 physical матрица отдельно.

PIO build PASS RAM55044/flash1093969; native codec/session и CI worker54tests PASS.
`pio check` PASS: HIGH0/MEDIUM31/LOW43. Lizard exit1: 501functions/41threshold warnings;
new/worsened Session.admit, machine request dispatcher, parser/output branches
сохранены явно, а не объявлены clean. Полный source semantic review выполнен по
base22edc704: существующие functions/branches не удалены; review артефакты отдельно.
Source include/src hashes совпадают с deployed frozen manifest; joint spec уточнён
после freeze только для host early-query поведения, бинарная прошивка не менялась.
Clean-release manifest gate закономерно FAIL на dirty tree. Commit/push/remote CI
не выполнялись; experimental image не объявляется release или accepted CI checkpoint.

Same-ID process resume и RX-only known-peer/BW получили отдельные физические
результаты ниже. Active controller reset, BLE reconnect и full performance acceptance
остаются самостоятельными gates. Original analytic plan не редактируется.

### Подтверждённый checkpoint v5 и аппаратные результаты

Current host frozen manifest:
`f4f5fc4ef277c7bf8d1da895786097e2b7d172097ccbe86cd836f214aa3c083b`.
Same-epoch WELCOME сохраняет monotonic request counter; новый epoch сбрасывает его.
Регрессия воспроизведена на v4 и исправлена в v5. Full pytest: 543 PASS/54.77s;
compileall и diffcheck PASS. Два lost-control fixture failures предыдущего полного
прогона сохранены в `artifacts/pytest-v5-final.log`: test-only replay interval
20→80 ms учитывает durable/outbox scheduling, сохраняет max_replays=2,
deadline=0.3s, outer elapsed<1s, same-ID/hash/one-publication assertions.
Runtime retry budgets не менялись; итоговый лог `pytest-v5-checked.log`.
Сводка: `/home/dream/file_transfer_logs/architecture-repair-20261011/artifacts/LOCAL_VALIDATION_v5.json`.

Forward physical matrix v4 (1B44→72E0): все четыре USB/BLE сочетания, 8/64 KiB,
8/8 application integrity PASS; пять точек потребовали END/MISSING repair.
Во всех девяти первоначально missing DATA sender LINK_OK подтверждён, initial
receiver machine DATA отсутствовал. Установлена граница после peer radio ACK
до host DATA; конкретный output queue/worker и RF-причина не установлены.
Один BLE→USB8KiB QUERY point завершился за5.044s вместо прежних33.593s;
BLE→BLE64KiB имел5QUERY. Это локальные cache QUERY, не midstream RF repair.
Clean transport acceptance остаётся OPEN. Отдельные cases с полными исходными
логами и payload/correlation сохранены в журнале экспериментов.
Отчёт: `v4/MATRIX_REPORT_SEPARATED.json`; исходная conservative classification
`v4/MATRIX_REPORT.json` сохранена без перезаписи.

На v5 USB1B44→USB72E0 verified same-ID recovery после SIGKILL:
- sender process после28/289chunks: PASS, ID `c775be1160bb5d4b`,
  same-ID/resumed, resume cursor30, 65536bytes/SHA, одна публикация;
- receiver process после31chunks: PASS, ID `1a40837737ec848f`,
  тот же sender автоматически завершил END/MISSING recovery, TX104.567s;
- оба процесса после30chunks: PASS, ID `57fdf9c7d3771fb2`,
  receiver запущен первым, sender resumed с тем же ID, exact SHA/one publication.
Данные и sender/receiver journals не удалялись, все own PIDs завершены.
Это USB process-fault coverage одного направления, не доказательство всех
BLE/reconnect/active-controller-reset scenarios.
Отчёты: `v5/restart_sender/REPORT.json`, `v5/restart_receiver/REPORT.json`,
`v5/restart_both/REPORT.json`.

Idle receiver-controller reboot в том же ST process: новый machine epoch,
автоматическое восстановление READY/RX без receiver file_send_start; следующий
8KiB файл ID `998e6080b18990f3` exact/SHA/one publication PASS, TX4.976s.
Это idle reset, а не reset посреди DATA.

R RX-only known-peer: BW500/250/125, SF7/470MHz/power2 — три PASS.
Каждый `/radio rx-restart` имеет before/after register snapshots и
`attempts=1 tx=0 reset=0 reinit=0`; уникальный peer USER получен receiver,
sender наблюдал matching logical ACK. Startup radio TX POST происходил до
runtime diagnostic; после первого marker receiver уже передавал ACK.
Silent-deaf state не воспроизведён, его root cause OPEN. Обе ноды возвращены
к BW500/CHAT/quiet/power2, own PIDs завершены.
Отчёт: `v5/restart_controller_R/REPORT.json`.

Пользователь отдельно поручил Luna полную текущую v5 файловую матрицу:
оба направления × USB→USB/USB→BLE/BLE→USB/BLE→BLE × 8/64KiB, SF7/BW500.
Инструкция и результаты находятся в `/home/dream/coding/журнал экспериментов`.
Пока матрица выполняется, её 16/16 completion не заявляется. Каждая аномалия
получает свою папку, описание, payload и все три ST лога. Timing-log сохраняется
при выполнении ST close/cleanup, в том числе при аварии сценария; SIGKILL/crash
без cleanup может лишить timing-log. Наличие третьего лога проверяется после
завершения процесса. Finalized logs не редактируются.

Original analytic plan неизменён. Midstream repair не реализован.
