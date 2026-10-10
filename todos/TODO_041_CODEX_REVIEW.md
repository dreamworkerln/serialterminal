# TODO 41: глубокий разбор FT1, SerialTerminal и Chatter

Дата: 2026-10-11, Europe/Moscow.
Тип работы: анализ исходников, существующих тестов и fault injection на fake transports.
Это review к TODO_041, а не реализация и не новая задача с новым TODO-ID.

## Проверенный checkpoint и границы доказательств

- SerialTerminal: ветка dev_tui, HEAD ea4a0d8362fa4163e181e4d5a878a6cf80c3a0be.
- Firmware: ветка dev_chat_binary, HEAD 1e7cdd53f0e9d8816fb416b6ed8c638f9888c8aa.
- Оба working tree перед анализом были чистыми.
- Основной TODO: todos/TODO_041_FT1_FAILURE_RECOVERY_AND_RX_OBSERVABILITY.md.
- Прочитаны текущие FT1 codec/manager/resume/pipeline, Chatter adapters, session,
  Serial/BLE transports, journal/store, соответствующие тесты; firmware USER/ACK,
  deduplication, scheduler, terminal queues/framing и radio recovery.
- Исторические физические наблюдения A–D используются как сведения из TODO.
  Их временные raw logs заново не исследовались; физическая provenance тех прогонов
  здесь не устанавливалась.
- Новых аппаратных соединений, reset, flashing, firmware build, commit/push и CI
  в этой работе не было. Инъекции ниже не являются hardware PASS.
- Исходники не изменялись. Единственный создаваемый проектный файл — этот review.

Wrong-length fix уже входит в commit 4ff115e, предшествующий текущему HEAD.
В TODO и inventory осталось описание «локальный незакоммиченный фикс» относительно
b838ecbc; это историческая запись, а не состояние анализируемого дерева.
Названия функций и ссылки на строки далее относятся к указанным HEAD.

## Главный вывод

Нужная пользователю устойчивость должна быть FT1-протоколом между двумя ST поверх
существующего opaque BINARY USER транспорта нод. Дорабатывать firmware ACK для
знания о файлах не требуется. Направление TODO_041 — редкий durable progress,
ограниченное окно неподтверждённых original DATA, selective repair во время потока,
пауза и продолжение с сохранённого cursor — соответствует задаче.

Текущий runtime этого ещё не реализует. У него есть хорошая база: стабильная
идентичность файла, persistent partial/journal, earliest-missing resume и selective
repair после END. Однако несколько реальных путей всё ещё уничтожают partial,
завершают worker, продолжают бесполезную передачу или теряют идентичность retry.
Добавить один тип FLOW недостаточно: сначала нужны правильные lifecycle,
ownership и error semantics.

Нужно различать:
1. потерю локального USB/BLE/controller outcome;
2. отсутствие приёма или durable progress у удалённого ST;
3. потерю/повреждение конкретного FT1 сообщения;
4. постоянную недоступность RF, storage или конфликт идентичности;
5. осознанный operator cancel.

## 1. Что реально подтверждает каждый слой

~~~text
ST A -> USB/BLE -> node A -> LoRa USER -> node B -> USB/BLE -> ST B -> disk
          transport         radio transaction          application ownership

written             local bytes accepted by host transport
> [BINARY]          local node completed first successful physical TX
firmware USER ACK   peer node accepted USER identity
RESUME/MISSING      FT1 receiver state / request; see durability caveat below
RESULT OK           current intended contract: verified final publication
~~~

Firmware references:
- chatter/include/ProtocolFrame.hpp:25,47 — ACK payload 2 bytes, identity
  (sender session_id, USER tx_seq), BINARY modifier.
- chatter/include/Reliability.hpp:112–183 — recent USER window and duplicate policy.
- chatter/src/Scheduler.cpp:724 — local BINARY presentation after first successful TX,
  before waiting for radio ACK.
- chatter/src/Scheduler.cpp:1560 — ACK obligation is recorded independently of host
  delivery; duplicate USER is ACKed again but not presented again.
- chatter/src/TerminalIo.cpp:1065,1164,1369 — asynchronous USB/BLE output queues;
  output does not report host application acceptance back to scheduler.

В текущем Chatter wire v3 используется reliable USER с обычным ACK, а не файловый
SACK, несмотря на название репозитория lora-sack-protocol. 32-bit recent-user bitmap
в firmware — локальная история дедупликации, не FT1 SACK и не durable file bitmap.

Отсюда существенный сценарий: node B получил USER и подтвердил его, но USB/BLE
вывод до ST B потерян. Повтор того же radio USER может подавляться firmware как
дубликат. Исправлять это нужно новой host submission тех же FT1
transfer_id/chunk_index/bytes: она получает новую radio USER identity, а ST B
безопасно дедуплицирует файловый чанк.

Radio CRC не защищает последующий текст/base64 канал до ST и disk state.
Локальный echo и firmware ACK нельзя использовать как разрешение пропустить
чанк после process restart. Каждый ST должен обходиться своей локальной нодой;
совместный доступ одного процесса к двум нодам не является условием recovery.

## 2. Текущий FT1: что сохранять и на что нельзя рассчитывать

Публичный FileTransferManager экспортируется из file_transfer/__init__.py и имеет
цепочку pipeline_manager -> manager -> resumable -> core. Анализ только core
приводит к неверным выводам о timeout/resume и production DATA pipeline.

Работающие механизмы:
- FT1 v1: META, DATA, END, RESULT, MISSING, optional RESUME.
- При Chatter capacity 243 legacy DATA header 16 bytes, payload до 227 bytes.
- END/MISSING selective repair; одинаковый корректный DATA идемпотентен.
- Wrong-length DATA теперь даёт chunk_rejected, сохраняет остальные чанки;
  плохой по длине дубликат не портит правильную сохранённую копию.
- Receiver sparse map и partial сохраняются в receive_dir и
  .serialterminal-state/incoming.
- Public manager fsync-ит partial до продвижения manifest; JSON manifest
  fsync/atomic replace, затем fsync его parent directory.
- Manifest является доказательством restart cursor; длина sparse file этим
  доказательством не является.
- Sender journal проверяет source hash, wire hash, compression, chunk_size;
  gzip reconstruction детерминирована.
- Completed tombstones и publishing-state reconciliation покрывают потерю RESULT
  и process restart без повторной публикации проверенного файла.
- USB sticky identity, BLE current-generation filtering и ordered notifications;
  generic session сбрасывает незаконченную входную строку на connection boundary.
- Controller epoch отличается от connection_generation, что правильно для reboot
  при остающемся открытым USB tty.
- DATA pipeline ограничен двумя submissions, ambiguous recoverable error вызывает
  fallback от earliest outstanding DATA.

Пока отсутствуют:
- negotiated FLOW/CAPS/QUERY и checked DATA;
- periodic end-to-end progress и remote receive credit;
- midstream selective repair с остановкой original cursor;
- полная автоматическая классификация local errors;
- общий безопасный control outbox/coordinator.

RESUME сейчас coarse cursor, не sparse SACK. Если есть ранняя дырка и сотни
сохранённых чанков после неё, sender повторяет suffix от первой дырки. MISSING
запрашивает точные отверстия после END. Это корректная базовая совместимость,
но с заметной ценой для больших файлов и длительного disconnect.

## 3. Findings: текущие дефекты и последствия

### F01. P0: termios.error может завершить session TX worker

Источник: transports/serial.py:456; session.py:624.
SerialTransport.write ловит SerialException/OSError, но termios.error в проверенном
Linux Python наследуется непосредственно от Exception, не от OSError.
Исключение из flush проходит и через обработчики ManagedSession.tx_loop.

Инъекция FakeSerial.flush -> termios.error(5, ...) подтвердила:
- исключение вышло из SerialTransport.write;
- TX worker завершился;
- accepted tx_id остался без written/unknown outcome.

Это объясняет класс «local_tx_timeout после USB disconnect» лучше, чем расширение
FT1 retry set само по себе: мёртвый worker новые сообщения не отправит.
Нужны нормализация backend error, правильный ambiguous outcome и наблюдаемый
worker failure. Нельзя просто превратить любой flush error в safe generic retry.

Также ser.write(data) сейчас не проверяет возвращённое число bytes; исключение
после возможной записи превращается в обычный TransportError и generic retry.
Это существующий scope TODO_013. Его существенную часть нужно учитывать в
TODO_041, сохранив generic write ambiguity для произвольных команд.

### F02. P0: часть одиночных RX ошибок по-прежнему удаляет всё накопленное

Источник: core.py:1253,1269,1328,1577; resumable.py:464.
Фатальные пути:
- index вне META range;
- одинаковый index/length с другими bytes;
- неверный END chunk_count;
- >capacity ranges в legacy MISSING;
- ошибка отправки MISSING;
- hash/decompression/storage failure.

resumable._fail_incoming удаляет manifest, core._fail_incoming удаляет partial,
снимает runtime incoming и отправляет отрицательный RESULT. Следующие DATA этого
transfer_id больше не обрабатываются. Matching META failed record не равно
matching META retained idle-timeout record.

Wrong-length fix закрывает только один класс проблемы. Это полезное исправление,
но ещё не общий recovery.

Bad index/END следует отвергать без удаления остальных проверенных bytes.
Conflicting duplicate требует explicit invalidation/quarantine, а не произвольного
выбора копии. Hash failure не разрешает публикацию и не позволяет объявить весь
bitmap корректным: сохранить для диагностики можно, доверять для skip — нельзя.

### F03. P0 для гарантии success: legacy RESULT не защищён от same-length corruption

Источник: protocol.py:316,383,483; resumable.py:749;
core.py:966 и resumable.py:678.
Ни common header, ни RESULT body не имеют application checksum.
При decode проверяется статус 0/1, но не согласованность ok и code.
Sender завершает передачу по result.ok и удаляет journal.

Инъекция одного byte в encoded отрицательном RESULT, offset 12, 1 -> 0, дала
ResultMessage(ok=True, code=storage_failed). Наличие final SHA-256 на receiver
не исправляет ложную интерпретацию ответа на sender.

Это демонстрация достижимого пути при повреждении local textual channel, а не
утверждение, что такой false success произошёл в физических логах.
В negotiated режиме защита только FLOW/QUERY/CAPS и DATA_CHECKED недостаточна.
Нужны checked terminal/control semantics, включая RESULT, END, META и RESUME
либо новый защищённый envelope/эквивалент с явной совместимостью.
Успех следует принимать только как корректно связанный verified completion,
а не из любого parseable ok bit. Legacy limitations должны быть честно обозначены.

### F04. P1: потерянный локальный echo ещё завершает TX

Источник: resumable.py:32,70; pipeline_manager.py:13;
binary_user.py:548; binary_pipeline.py:143.
Автоматический recovery включает только local_tx_unknown, local_disconnect,
local_controller_reset. binary_presentation_timeout туда не входит.

Файл может уже иметь этот DATA на peer ST, но sender завершится с
binary_send_failed. Физический случай B в TODO согласуется с исходниками.

Для FT1 допустим bounded replay тех же bytes/index/identity, в pipeline — от
earliest ambiguous outstanding. После recovery нужен remote durable status;
local echo не становится end-to-end ACK.
Не переносить эту replay policy на arbitrary commands.

### F05. P1: local timeout оставляет accepted сообщение в session queue

Источник: binary_user.py:356,470,548; session.py:439,624;
profile adapter binary_pipeline.py:281 (discard_binary_pipeline).
Adapter может закончить ожидание local_tx_timeout, но очередной tx_id не отменён.
Discard pipeline очищает correlation tickets, не generic outgoing queue и не
firmware queue.

Инъекция с disconnected fake session:
- FT1 получил binary_send_failed/local_tx_timeout;
- одно accepted сообщение осталось в session.outgoing;
- recovery state не был начат.

После reconnect это сообщение способно физически уйти уже после failed transfer
или освобождения lease. Если просто добавить local_tx_timeout в recoverable set,
можно накопить дополнительные /help и /bin copies, не выяснив судьбу старых.

Нужен per-submission lifecycle: queued-unwritten, written, unknown, retired/cancelled
или явное bounded ожидание прежнего tx_id. Очистка должна касаться только
собственных outstanding submissions, а не чужой очереди. Generic accepted-TX
ownership может потребовать расширения механического API session, без знания FT1.

Фрейминг тоже часть этой задачи. BLE firmware сбрасывает input parser на connection
epoch; USB parser не имеет эквивалентного disconnect callback. Текущий /id+newline
connect preamble помогает завершить старую линию, но не доказывает, что оборванная
команда корректно принята. Не считать INPUT TOO LONG всегда постоянной ошибкой
размера: при штатном /bin limit корректного packet это может быть вторичный эффект
оборванной/склеенной строки. Такая гипотеза требует targeted tests и корреляции,
она не устанавливает причину физического случая A.

### F06. P1: remote negative RESULT не прекращает DATA promptly

Источник: core.py:341,887,1034; resumable.py:652; pipeline_manager.py:80.
RESULT записывается и будит condition, но DATA loops проверяют cancel, не RESULT.

Инъекция negative RESULT на DATA 0 у 4096-byte файла:
sender всё равно отправил все 19 DATA, затем завершился remote_failed.
Это отдельно подтверждает кодовый дефект из физического случая C.

Проверка terminal outcome должна стоять перед каждой новой submission, после
settle/recovery и внутри repair. Нужен также wakeup блокирующего settle.
Уже accepted <=2 tickets нельзя выдать за «не отправленные»; их судьба должна
завершаться по отдельной policy, не через превращение remote failure в operator
cancel и не через indiscriminate /cancel all.

### F07. P1: RX исключения скрываются; idle sweep действительно убивает worker

Источник: core.py:1052; manager.py:364; binary_user.py:252.
META/DATA/END handler exception подавляется общим except Exception: continue.
DATA disk I/O и durable checkpoint errors могут оставаться без transfer event.
_expire_stale_incoming в queue.Empty path расположен вне handler protection.

Инъекция checkpoint OSError в idle sweep подтвердила:
RX thread умер, snapshot остался receiving.
Base64 parse failure хранится лишь в last_parse_error; receiver callback exception
также подавляется без structured application failure.

Нужно сохранить изоляцию общего session notifier, но регистрировать layer, phase,
transfer_id, cause и worker state. Disk failure не может продвигать durable ACK.
Нужен supervisor/observable bounded failure, а не silent loop continuation.

### F08. P1: same-process retry failed TX может сменить transfer_id

Источник: resumable.py:552; manager.py:62,306; core.py:1682.
Journal retained после failed TX. Но start_send, обнаружив old transfer_id в
_records, отказывается от candidate и создаёт новый ID.

Инъекция missing-echo failure и второй start_send того же файла:
00000000000000c9 -> 00000000000000ca, resumed=false, два matching journals.
На следующем выборе это способно привести к ambiguous_resume_state.
Это противоречит ожиданию «продолжить ту же передачу».

После file_transfer_close старый runtime record удаляется, и journal может быть
использован; process restart тоже убирает memory collision. Поэтому утверждение
«journal retained значит следующий start в том же процессе автоматически resume»
сейчас неверно без дополнительных условий.

Нужна явная policy reuse/revive failed/suspended sender record с ownership checks,
либо поддерживаемое explicit resume той же identity. Новое ID допустимо при
реальном изменении source identity или осознанном fresh transfer.

### F09. P1: replayed META активного RX возвращает memory cursor вместо durable cursor

Источник: resumable.py:317,328; manager.py:211.
_send_resume вычисляет _earliest_missing по incoming.received.
Для active matching META перед ответом нет forced checkpoint.
Memory map может быть впереди manifest.

Инъекция с deliberately lagging checkpoint:
memory_chunks=1, durable_ranges=[], RESUME_FROM=1.
При обычных defaults окно меньше, но путь тот же.

После receiver crash manifest восстановит более раннюю позицию; final repair
может спасти ситуацию, поэтому это не самостоятельное доказательство неверной
публикации. Но ответ не соответствует заявленному receiver-proven durable cursor.
Для нового FLOW/credit это нельзя оставлять: перед proof нужен fsync+manifest
либо расчёт по отдельному authoritative durable map.

### F10. P1: отказ начать RX может удалить partial, который не создавал

Источник: resumable.py:384; manager.py:200.
При обнаружении stale/corrupt manifest или существующего part raises storage_failed,
после чего unconditional part.unlink выполняется в except.

Инъекция corrupted manifest + retained part подтвердила:
storage_failed, manifest сохранился, existing part исчез.
Существующий тест corrupt_receiver_manifest проверяет отсутствие unsafe publication,
но не сохранность этих bytes.

Нужно вести created-by-current-operation ownership и удалять лишь свои временные
файлы. Corrupt state отклонить/карантинировать; не считать это разрешением стереть
сохранённые bytes. Initial checkpoint failure после reserve также требует rollback.

### F11. P1: текущий RX path нельзя напрямую использовать для midstream control

Источник: resumable.py:317; core.py:1328,1099,1117.
RESUME, MISSING и claimed RESULT могут синхронно ждать send_binary.
Это блокирует единственный RX worker на local write/presentation/recovery.
RESULT replay/reject создаёт отдельный thread на сообщение без bounded outbox.

Новый FLOW reply в том же path усугубит проблему: пока ответ ждёт USB/BLE,
приём следующего DATA и checkpoint задерживается, queue растёт.
_rx_queue и remote_missing deque сейчас unbounded.

Нужен bounded coalescing outbox и единый отправочный lane. Inherited send_binary
использует _send_lock, pipeline submit использует отдельный
_pipeline_submit_lock: будущая конкурентная control submission не сериализуется
автоматически с DATA. Корреляция rejection тоже пока не привязана к конкретному
ticket; это известный TODO_011, особенно важный при stop/drain/replay.

### F12. P1/граница firmware: RADIO_UNAVAILABLE не восстанавливается одним ST retry

Источник: chatter/src/RadioRecoveryPolicy.cpp:30;
RadioRecoverySupervisor.cpp:88; RadioUnavailable.cpp:8;
main.cpp:309,337; chatter/include/Scheduler.hpp:47.

Firmware имеет bounded radio-only recovery. Но после exhausted recovery:
- MCU и USB/BLE остаются доступны;
- RF выключен;
- telemetry явно сообщает reprobe=disabled, recovery=manual_reboot;
- /reboot запускает повторную radio init;
- main loop больше не вызывает нормальный radio health/protocol path.

Если пользователь отключил/вернул только питание SX1278 и прошивка уже перешла
в это состояние, восстановление питания само по себе не обещает возвращения RF.

В host-only TODO можно сохранить state, показать RF unavailable и дождаться
отдельно восстановленной ноды. Автоматический firmware reprobe — отдельная
firmware задача. ST не должен скрытно делать /reboot или бесконечно долбить /bin.
READY контроллера также не является доказательством RF readiness.

### F13. P2: prepared stream для Compression.NONE не является immutable snapshot

Источник: resume_source.py:55–82.
При GZIP DATA читается из подготовленного временного wire file.
При NONE wire_path — исходный пользовательский path, открываемый позже для
original DATA и repair.

Изменение/замена файла во время длинной передачи может отправить новые bytes под
старой identity. Final SHA это обнаружит, но seamless repair уже нельзя гарантировать.
TODO требует «тот же prepared wire representation», и это условие нужно сделать
реальным: immutable source snapshot/spool или чётко контролируемая source policy.
Повторный hash между запусками не закрывает изменение в процессе передачи.

### F14. P2: revive/restore должны быть атомарны относительно runtime ownership

Источник: manager.py:314,352; resumable.py:213.
Manager сначала меняет timed-out record из failed в receiving, затем пытается
restore. Если другой transfer активен, restore возвращает None; предыдущая
история/terminal retention уже изменена.
Restore existing record устанавливает _active_id до _claim и не имеет полноценного
rollback при claim exception.

Это кодовый вывод, отдельной инъекцией не проверялся. Для нового coordinator
восстановление record, session lease, incoming и terminal history должно либо
завершиться целиком, либо оставить прежний suspended/failed state.

### F15. P2: текущие timeout names не равны общему строгому recovery budget

Источник: resumable.py:70; binary_user.py:356,395,470,548; core.py:966,1052.
60-second local recovery deadline появляется после первого recoverable exception.
Вложенный send/controller-ready/mode wait не получает остаток общего deadline.
controller_ready_timeout, local_tx_timeout и binary_mode_unknown могут оборвать
попытку раньше; очередная blocking attempt может, напротив, выйти за deadline.

3600-second result_timeout начинается в _await_remote_completion после initial END,
не в начале всей передачи; это не one-hour total transfer limit.
Idle timeout 120 seconds проверяется при queue.Empty и относится к активности,
не к durable progress. Поток malformed/unrelated/rejected traffic не должен
позволять в будущем держать lease бесконечно.

Новый coordinator должен иметь явные phase и no-progress deadlines, передавать
remaining budget вниз и отличать recent traffic от подтверждённого продвижения.

## 4. Оценка выбранного дизайна TODO_041

### Что выбрано правильно

1. End-to-end host control поверх opaque BINARY USER, без изменения firmware ACK.
2. Один coordinator соединяет original sending, local recovery, resume и repair.
3. При gaps sender перестаёт создавать original DATA, завершает outstanding и
   читает только requested indexes; next_original хранится отдельно.
4. Repair подтверждается durable receiver state, затем поток возвращается к cursor.
5. Gaps считаются только ниже доказанного frontier. Tail loss обнаруживается QUERY/END.
6. Partial batches решают >packet-capacity holes без переопределения legacy MISSING.
7. Runtime token, sequence, duplicate/stale semantics и finite retries обязательны.
8. Time checkpoint плюс credit limit закрывают отсутствие самого receiver ST.
9. Final END/SHA/decompression/publication/RESULT остаются обязательными.
10. Capability negotiation и old/new fallback нужны на уровне ST, не firmware version.

Это скорее cumulative durable ACK + selective NACK/repair batches, чем полный
positive sparse SACK. Функционально пользователь получает нужную selective repair;
термин SACK не должен скрыть точное значение каждого поля.

### Решения, которые ещё нужно закрепить до реализации

**D01. Protect all state-changing messages.**
FLOW CRC и DATA_CHECKED нужны, но RESULT/META/END/RESUME/MISSING тоже могут быть
повреждены после RF. Для negotiated режима определить checked envelope/types,
покрывающие identity и весь body. CRC проверить до применения даже index/frontier.
Legacy encodings не менять молча. CRC не заменяет final SHA.

**D02. Missing batch не является full SACK snapshot.**
Если reply сообщает только первую порцию и MORE_GAPS, не перечисленные индексы
нельзя считать полученными. Durable prefix подтверждает только непрерывный префикс.
frontier означает область обсуждения, не доказательство доставки всей области.
Repair complete обязан иметь scope: token, frontier, repair/query identity.

**D03. Unsolicited FLOW и solicited reply должны иметь ясную корреляцию.**
flow_session + status_seq защищают от старых snapshot, но сами по себе не определяют,
какой QUERY или repair verification закрыт. Нужен query/request ID либо эквивалентный
однозначный контракт. Retransmit того же request не создаёт новый logical repair.
После process restart/re-negotiation token меняется; controller reconnect сам по
себе не обязан менять host runtime token.

**D04. Loss последнего CAPS confirm и restart peer — отдельные сценарии.**
Нельзя получить состояние «sender считает peer legacy, receiver ждёт только checked»
либо обратное. Определить допустимые messages на каждом handshake phase, retry,
fallback и обработку delayed confirm.
Если RX процесс потерял runtime state, old FLOW_QUERY должен приводить к bounded
re-negotiation/META restore, а не к permanent silence.

**D05. Freeze wire identity before META.**
Legacy header: 12+4=16, chunk payload 227 при capacity 243.
Proposed checked DATA header: 12+4+4=20, payload 223.
Conservative 223 подходит и legacy DATA для нового transfer, но нельзя пере chunk
у старого 227-byte journal без новой identity.
Текущий _send_worker всегда выводит chunk_size из legacy capacity; потребуется
выбор из validated journal/negotiated plan, а не поздняя смена размера.
Решение о default checked mode и throughput measurements ещё открыто.

**D06. Durable invalidation должна переживать crash.**
При конфликтующем DATA сначала удалить доказательство этого индекса из authoritative
manifest с durable commit, затем принимать replacement; нельзя сначала переписать
bytes под старым durable bit.
Для CHECKED packet с плохим CRC не доверять повреждённому index и не инвалидировать
по нему чужой правильный чанк.
Два conflicting valid copies не выбирать по принципу «последняя лучше».
Нужны проверенная immutable sender representation, repair provenance и finite policy.
Whole-file hash mismatch не локализует corrupt chunk сам по себе; для post-storage
corruption потребуются retained chunk checksums или quarantine/explicit restart.

**D07. <=2 означает host pipeline, не две мгновенно отменяемые RF передачи.**
Node queue имеет depth 8 и один active reliable USER; local echo появляется до ACK.
В штатном двухticket lane хвост ограничен. Но error/replay может оставить accepted
generic TX или controller work вне correlation deque.
Stop выдачи и drain/recover tickets нужно определить вместе с retirement policy;
discard deque не равно остановке эфира. После negative RESULT не выдавать repair.

**D08. Credit и liveness считать по настоящему progress.**
256 chunks и 10 seconds — начальные экспериментальные параметры, не доказанный
оптимум. 256 * 227 = 58112 bytes неподтверждённого original payload.
На быстрых и медленных PHY wall-clock время этого окна сильно отличается.
Credit считать по issued original frontier и durable contiguous prefix; replay не
добавляет новых bytes. Одна старая дырка не разрешает бесконечный обход.
Нужны no-progress limit и rate-limited queries, не независимые watchdog loops.

**D09. Общие lifetime counters должны быть bounded, но не запрещать нормальный repair.**
8 раундов годится как legacy final-repair guard, но не как лимит всех midstream
batches большого файла. Считать repeated batch without progress отдельно от
successful useful repair. При каждом transient reconnect не сбрасывать весь
operation budget бесконечно. Cancel/close проверять в каждом wait.

**D10. Согласовать TODO_038 и текущий roadmap.**
TODO_041 уже выбирает объединённый progress/repair exchange.
TODO_038 остаётся deferred, inventory next-work text ещё предлагает сначала
делать TODO_041 «without enabling TODO_038». Нужно разделить legacy hardening
checkpoint и negotiated extension checkpoint с сохранённым throughput baseline.
Вторая реализация watchdog поверх FLOW не нужна.
Исторический TODO_029 также содержит superseded telemetry/restart prose; опираться
на текущий code + FT1_RESUME, затем синхронизировать изменённые контракты.

## 5. Рекомендуемое поведение recovery

~~~text
SEND ORIGINAL
   | valid gap report / checkpoint-credit due
   v
STOP NEW ORIGINAL -> DRAIN/RESOLVE OWN PENDING <=2
   | local lifecycle failure
   +-> WAIT LOCAL NODE / bounded same-message replay
   |
   v
QUERY / RE-NEGOTIATE / RESTORE META as necessary
   |
   +-> receiver unavailable: low-rate bounded wait, retain journal
   |
   v
REPAIR bounded oldest missing batch
   |
   v
QUERY durable closure of same repair/frontier
   +-> remaining gaps: next batch / bounded retry without progress
   |
   v
CONTINUE original at saved next_original
   |
   v
FINAL DURABLE DRAIN -> END -> VERIFY/PUBLISH -> checked RESULT OK
~~~

Нельзя отправлять весь suffix от первой дырки как обычную midstream repair.
Пример cursor=600, gaps=12,90..92,410: послать пять DATA, подтвердить их durable
closure и продолжить с 600. Coarse RESUME suffix остаётся compatibility fallback.

### Error policy

| Событие | Рекомендуемая реакция | Судьба сохранённого |
|---|---|---|
| Bad length/index, corrupt checked packet | Reject; request proven gap later | Correct chunks retained |
| Conflicting same-index bytes | Durable invalidation/quarantine of affected index, bounded repair | Other valid chunks retained |
| Wrong END fields/checksum | Reject, replay checked END | Partial retained |
| Lost local echo/ambiguous write | Resolve old ticket; bounded replay exact FT1 message | Identity/journal retained |
| USB/BLE disconnect or controller reboot | Wait/probe local lifecycle; restore mode knowledge and replay | File state independent of node epoch |
| Receiver ST disconnected/dead | Stop at time/credit boundary, bounded recovery/renegotiation | Journal and RX partial retained |
| Lost FLOW/QUERY/MISSING/RESULT | Retry same logical control / query; tombstone completion when verified | No destructive reset |
| Too many legacy MISSING ranges | Explicit suspended unsupported-limit/resume path | Partial retained |
| Temporary disk/checkpoint error | Stop proof of progress, explicit storage wait/failure | No false durable bits; preserve previously committed state |
| Hash/decompression/identity conflict | No publication; quarantine untrusted state, explicit disposition | Do not use suspect bitmap to skip |
| Local RF unavailable | Observable RF state, wait only bounded policy or operator restore | File state retained; no hidden reboot |
| Operator cancel | Cancel own work, intentional documented cleanup | Distinct from suspend/recovery exhaustion |
| Recovery budget exhausted | Stable observable suspended/failed result with resume policy | Retain usable identity/state |

Failure state in UI/history and persistent-state disposition are different axes.
«Failed attempt» не обязано означать удаление partial. Но после operator cancel
автоматически воскрешать отменённую операцию нельзя.

## 6. Как пользовательские аварии должны проходить

| Авария | Сейчас | Для принятия TODO_041 |
|---|---|---|
| TX node reboot, USB tty остаётся | Есть epoch/READY/replay база; readiness/timeouts могут стать fatal | Same ID, bounded wait, remote durable reconciliation |
| TX BLE disconnect/reconnect | Current-generation transport + replay некоторых errors | Same owned tickets, no stale callbacks/echo, deadline propagation |
| RX USB/BLE unplug, MCU жив | Нода может ACK без ST; sender не знает до END | Time/credit pause; META/state restore; bounded repair batches |
| Долгий RX disconnect, >28 isolated gaps | Legacy repair_too_large удаляет partial | Negotiated batches; legacy retained explicit limit |
| Кабель выдернут во время /bin write | Возможен unknown/prefix/flush failure; termios worker death | Safe write outcome, framing resync, owned queue retirement |
| DATA потерян/обрезан в середине файла | Wrong length survives, repair лишь после END | Early bounded repair, сохранение original cursor |
| Peer ST restart | Manifest resume есть, active handshake semantics ограничены | Fresh runtime token, durable state restore, no stale proof |
| Sender ST restart | Journal/identity проверяются, explicit start нужен | Receiver-proven continuation; no new ID from stale runtime record |
| Только radio power возвращён после exhausted recovery | Firmware остаётся RF disabled | ST preserves file; восстановление RF требует отдельного действия/firmware work |
| Lost final RESULT | Tombstone/replayed META/END база работает | Checked completion, no second publish, bounded retry |

Важная оговорка: физическое unplug может также обесточить MCU. Для анализа и
acceptance нельзя смешивать «host link missing, node alive», «MCU reboot» и
«только radio unavailable». У них разная нижняя граница восстановления.

## 7. Порядок реализации

### Checkpoint A: legacy safety и worker/ownership foundation

- Исправить termios propagation/unknown outcome и закрыть необходимые TODO_013 cases.
- RX failure disposition: bad messages не удаляют пригодные chunks;
  storage/identity errors различимы.
- Prompt remote terminal handling в original/pipeline/repair/recovery waits.
- Safe accepted-TX retirement/drain, framing и bounded local error classification.
- Structured errors, alive/supervised RX worker, guarded idle sweep.
- Не удалять existing part на failed creation; rollback при revive/claim.
- Same-process same-ID retry и durable RESUME proof.
- Regression tests сохраняют старые compatibility/tombstone/cancel guarantees.

### Checkpoint B: agreed checked wire contract

- Codec/capability negotiation, terminal protection, token/query/sequence semantics.
- Dynamic packet budgets и checked/legacy source identity.
- Malformed/stale/duplicate/reordered/lost-confirm tests прежде runtime default.
- Согласовать TODO_038/029 и сохранить pre-extension throughput baseline.

### Checkpoint C: единый coordinator и midstream repair

- Receiver memory/durable/frontier state; bounded control outbox.
- Sender cursor, tickets, remote prefix, active batch/request, phase deadlines.
- Stop/drain/repair/confirm/continue; final repair drain + END/RESULT.
- Crash-safe invalidation, fresh runtime negotiation, resume/tombstones.
- Observability: issued versus receiver durable, gaps/ranges, retry budget, pause cause.

### Checkpoint D: end-to-end acceptance

- Deterministic fault matrix, затем full suite и required CI.
- Отдельные реальные USB->BLE и BLE->USB runs с точной firmware/ST provenance.
- Throughput/latency/control traffic comparison при одинаковом PHY/file/topology.
- Только после этого заявлять устойчивость пользовательским unplug/reboot сценариям.

Это рекомендации к реализации. Ни один checkpoint этим review не объявляется выполненным.

## 8. Проверка, выполненная в этой работе

### Existing automated baseline

Запущены 15 relevant test modules, 125 tests PASS, 8.10 s:

~~~text
tests/test_file_transfer_core.py
tests/test_file_transfer_protocol.py
tests/test_file_transfer_resume.py
tests/test_file_transfer_resume_edges.py
tests/test_file_transfer_receiver_restart_edges.py
tests/test_file_transfer_resume_compat.py
tests/test_file_transfer_resume_hardening.py
tests/test_file_transfer_resume_safety.py
tests/test_file_transfer_sender_journal_safety.py
tests/test_file_transfer_same_process_resume.py
tests/test_ft1_binary_pipeline.py
tests/test_chatter_binary_user.py
tests/test_chatter_controller_lifecycle.py
tests/test_serial.py
tests/test_session.py
~~~

Исполнение:
~~~text
/usr/bin/python3 -B -m pytest -q -p no:cacheprovider --basetemp <temporary>/pytest <modules above>
PYTHONDONTWRITEBYTECODE=1
SERIALTERMINAL_CACHE_FILE=<temporary>/device-cache.json
~~~
Wrapper использовал tempfile.TemporaryDirectory; временные файлы удалены.
Исходники/pytest cache/bytecode не менялись.
Весь test suite заново не запускался; firmware tests/build/CI не выполнялись.

125 PASS доказывает сохранность проверенного baseline, а не отсутствие Findings:
некоторые tests прямо ожидают старое fatal behavior для conflicting duplicate и
oversized MISSING. Их контракт потребуется изменить вместе с новой semantics,
не ослабляя проверку конечных bytes/hash.

### Additional fault injections

| Probe | Наблюдённый результат |
|---|---|
| Serial flush -> termios.error | Exception leaks; is_oserror=false |
| ManagedSession TX with that backend | Worker dead; tx_outcome=null |
| Existing partial + corrupt manifest + matching META | storage_failed; part deleted; manifest remains |
| Negative RESULT on DATA 0 | All 19/19 DATA submitted; final remote_failed |
| Failed TX then same-process start same source | ID c9 -> ca; resumed=false; 2 journals |
| Idle checkpoint OSError | RX worker dead; state still receiving |
| RESULT failed status byte 1->0 | Parsed ok=true with code storage_failed |
| Disconnected accepted TX, short adapter deadline | local_tx_timeout; outgoing queue still contains 1 item |
| Active META with uncheckpointed DATA | memory 1 chunk; durable []; RESUME_FROM 1 |

Все probes использовали fake session/transport, временный receive_dir и synthetic
payload. Ни один serial port/BLE device не открывался. Это реально выполненные
code-path experiments; остальные отмеченные source/design risks ими не подменяются.

### Недостающие regression gates

1. Unplug during USB write/flush, short write, prefix accepted, reconnect before/after deadline.
2. META/DATA/END/control reset на обоих концах, включая USB tty без disconnect.
3. Lost echo при фактически доставленном original/repair DATA, production pipeline.
4. Negative RESULT во всех waits/loops; only-own ticket cleanup.
5. Same-ID same-process retry и повтор после recovery budget exhaustion.
6. Durable RESUME/FLOW до/после fsync, manifest replace, invalidation и crash.
7. RX write/read/checkpoint/cleanup errors; worker failure event and bounded ownership.
8. Early sparse/burst/tail gaps, >capacity batches, repair loss и repeated no-progress.
9. No remote ST, RF ACK without host consumption, time/credit bound.
10. Lost/delayed/duplicate CAPS/QUERY/FLOW/RESULT; restart runtime token and stale replies.
11. Checked corruption identity/index/frontier/result до применения state.
12. New/new, new/old, old/new; old journals 227 and new checked 223; terminal tombstones.
13. Mutable uncompressed source и exact prepared-wire repair.
14. Operator cancel/close на каждой phase, без resurrection или чужого cancel.
15. Реальные direct USB/BLE interruption + radio-power cases с явным учётом
    RADIO_UNAVAILABLE/manual recovery и измерением speed overhead.

## Итог review

TODO_041 выбран в правильном направлении, но это значимая переделка FT1 state machine,
а не небольшой retry patch. Требуемая пользователю схема — «приёмник сообщил
дыры/неподтверждённый progress, отправитель остановил новый поток, восстановил нужные
чанки, получил durable подтверждение и продолжил» — достижима поверх текущих нод.

Перед внедрением нужно закрыть разрушительные legacy paths, worker death,
accepted-queue ownership, same-ID retry, durable proof и protected terminal controls.
Далее реализовать один negotiated progress/repair coordinator с bounded batches,
deadlines и compatibility fallback. Самовосстановление RF после firmware
RADIO_UNAVAILABLE остаётся отдельной задачей; host-only layer не может обещать его.

Current implementation: early FLOW/repair не реализован.
Current automated evidence in this review: 125 baseline PASS + listed fault injections.
Current physical validation: не выполнялась; требуемая матрица остаётся OPEN.

