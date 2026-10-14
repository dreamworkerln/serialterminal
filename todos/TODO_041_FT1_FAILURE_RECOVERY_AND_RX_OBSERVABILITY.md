# FT1: сохранение передачи при ошибках и диагностика остановок

TODO-ID: TODO_041
Status: PARTIAL / REMAINING IMPLEMENTATION OPEN / PHYSICAL VALIDATION OPEN
Created: 2026-10-10
Finding checkpoint: `dev_tui@b838ecbc5fa27039455480e2c7c5dfbdbe462371` + локальный незакоммиченный фикс wrong-length DATA.

## Разбор исторических ревью — 2026-10-14

Источники: [CODEX review](TODO_041_CODEX_REVIEW.md) и
[GPT review](TODO_041_GPT_REVIEW.md), оба для SerialTerminal
`ea4a0d8362fa4163e181e4d5a878a6cf80c3a0be`.
Это historical findings/design leads; выполненные stages ниже не подтверждают
автоматически каждый пункт. Перед исправлением проверить актуальный exact source.
Импорт в numbered registry и новый проход проверки здесь не выполняются.

| CODEX finding / GPT section | Профильный scope и acceptance |
| --- | --- |
| F01 / §17.1 | TODO_041 stage 1 и [TODO_013](TODO_013_SERIAL_SPP_WRITE_AMBIGUITY.md): termios/short/partial write, unknown outcome и accepted-TX settlement; generic command replay не становится FT1 replay |
| F02 / §4.1–4.3, §21 | TODO_041 stage 2 и error policy: bad DATA/END/MISSING не удаляют пригодные bytes; conflicting valid copies и hash failure не дают ложного trusted bitmap |
| F03 / §11, §24, §28 codec | TODO_041 terminal/control protection и corruption gates ниже; contradiction check alone не доказывает integrity RESULT |
| F04 / §17, §26 | TODO_041 bounded echo-loss/reconnect recovery с exact same bytes/identity, включая pipeline и repair |
| F05 / §14, §23 | TODO_041 stage 1: own accepted submission retirement/drain, operator cancel отдельно от remote protocol preemption |
| F06 / §4.4, §14 | TODO_041 stage 2: negative RESULT проверяется во всех loops/waits; не выдаёт новые DATA/repair и не вызывает чужой cancel |
| F07 / §4.5, §7 | TODO_041 stages 1–3: worker/disk/checkpoint/callback failure наблюдаемы, durable proof не продвигается без commit |
| F08 / §16–17 | TODO_041 stage 4: same-ID revive/resume, ownership и validated source/journal; F017 peer namespace отдельно в TODO_046 |
| F09 / §7 | TODO_041 stage 3 и future durable snapshot barrier: RESUME/FLOW не подтверждают только memory bitmap |
| F10 / §4, §7 | TODO_041 stage 2: cleanup только created-by-operation state, corrupt existing part не удаляется автоматически |
| F11 / §12, §23 | TODO_041 coordinator/outbox: bounded RX/control queues, один submission lane, repair/cursor ownership; correlation overlap уже в [TODO_011](TODO_011_CHATTER_PRESENTATION_CORRELATION.md) |
| F12 / §18–19 | TODO_041 local RADIO_UNAVAILABLE policy: retain state, typed profile error, bounded wait for explicit recovery; firmware reprobe и скрытый reboot вне host scope |
| F13 / §10–12 | TODO_041 stage 3: immutable raw/gzip representation для original и repair; identity/data mode сохраняются при resume |
| F14 / §16–17 | TODO_041 stage 4 и REVIEW_001/F001 в TODO_043: atomic durable/runtime/lease restore, post-checkpoint rollback проверяется отдельно |
| F15 / §13, §15, §26 | TODO_041 общие remaining deadlines и no-progress budgets; healthy useful repair не ограничивать произвольным total batch count |

### Непринятые design proposals и недостающие gates

Пункты CODEX D01–D10, GPT §31 и automated/physical matrices сохранены как
открытая работа TODO_041. Они не выбирают новую архитектуру или encoding сами
по себе. FLOW/CAPS/QUERY, checked DATA и remote-progress extension остаются
отложенными для текущей implementation series; отдельный старт/согласование
требуется перед реализацией. При разборе добавлены явные gates:

- [ ] CODEX D01/F03: определить защиту всех state-changing terminal/control
  messages, включая META/END/RESULT/RESUME/MISSING. Проверить corrupt identity/body
  до mutation; не считать одно согласование ok/code полной защитой RESULT.
- [ ] D02–D04 / GPT §8–10, §24: выбрать ownership `flow_session`, request/reply
  correlation, issued/covered frontier и partial-batch proof scope. Не перечисленные
  ranges не означают delivered chunks; loss последнего CAPS confirm, delayed confirm,
  fallback, peer restart и stale runtime control имеют детерминированную policy.
- [ ] D05 / GPT §10–11: выбранные chunking/data mode заморожены до META и persisted;
  existing 227-byte journals не перекраиваются в 223-byte checked transfers.
  Token остаётся runtime state; default checked mode и compatibility надо согласовать.
- [ ] D06 / GPT §4.2, §21: conflicting valid duplicate не перезаписывает durable
  bytes без независимого chunk truth. Invalidation commit предшествует replacement;
  bad CRC не позволяет использовать недостоверный index для изменения bitmap.
- [ ] D07 / GPT §14, §23: protocol preemption не вызывает operator cancel;
  issued tickets имеют bounded drain/retirement, terminal control не теряется при
  outbox coalescing, publication/final RESULT принадлежат одному coordinator.
- [ ] D08–D09 / GPT §7, §13, §15: durable snapshot barrier при DATA во время fsync,
  progress/credit по доказанному durable prefix, tail gaps по issued frontier,
  bounded unchanged retries и responsive cancel/close на каждой phase.
  Query/credit/gap defaults — measurement proposals, не утверждённые constants.
- [ ] D10: согласовать отложенный [TODO_038](TODO_038_FT1_REMOTE_PROGRESS_WATCHDOG.md)
  с одним FLOW coordinator; сохранить pre-extension baseline и не вводить второй
  независимый watchdog. Исторический full-set MISSING plan согласовать с текущим
  recursive [TODO_042](TODO_042_FT1_BATCHED_FINAL_REPAIR.md), не возвращая legacy
  wire behavior вопреки действующему branch contract.
- [ ] GPT §20, §28 scalability: определить bounded sparse memory/range representation
  и исключить O(n) recount на каждый chunk; synthetic large-count и fragmented-loss
  tests проверяют память/очереди без огромных allocations. Interval set — proposal,
  структура не выбрана этим разбором; overlap TODO_043/S2 и TODO_045 учитывать.
- [ ] GPT §19, §22: typed rejection classification остаётся в profile; observer/TUI
  различают original issued/local settled/receiver durable, repair/pause и local
  recovery. INPUT TOO LONG classification не подменяет доказательство его причины.
- [ ] CODEX regression gates 1–15 / GPT §28–29: трассируемая automated и physical
  matrix на exact checkpoint, включая lost echo при delivery, negative RESULT во
  всех waits, snapshot/crash boundaries, stale control, no remote ST при RF ACK,
  restarts/reconnect и явную границу RADIO_UNAVAILABLE. Physical work отдельно;
  host-only TODO не требует изменения firmware или автоматического reboot.

Существующие implementation/physical статусы сохранены. Этот разбор не запускал
исправления или validation и не объявляет historical findings исправленными.

## Architecture-repair execution checkpoint

Experimental series baseline: SerialTerminal `b7f58f8`, Chatter `2d8723ca`.
The cross-project order is recorded in Chatter's
`chatter/ARCHITECTURE_REPAIR_EXECUTION_PLAN_2026-10-11.md`.

Stage 1 implements conservative serial write outcomes, accepted-TX settlement on
worker/session stop, addressable cancellation and owned host drain, visible RX
worker/idle-sweep failures, and shared adapter/recovery deadlines. Firmware queue
settlement remains outside the legacy host fence.

Stage 2 implements partial retention/quarantine, non-destructive rejection of bad
DATA/END, creation-owned cleanup, negative RESULT stop in original/pipeline/repair
and contradictory RESULT decoding checks.

Stage 3 implements immutable raw/gzip snapshots, checkpoint-before-RESUME and one
destination from durable publishing intent through completed tombstone before OK.
Fault injection covers bytes, intent, rename, directory, tombstone and RESULT delivery
for compressed/uncompressed streams. Local stages 1–3 checkpoint: 477 pytest tests
passed with an isolated device cache. Stage 4 is preserved at `f9c8a8f`: same-ID
revival, atomic lease/rollback and bounded control/recovery deadlines (494 tests).
The experimental working tree adds the shared local machine contract, one FT1
coordinator, bounded RX/control/outbox queues and protected Chatter machine client.
Current full host suite: 543 PASS with isolated cache. Physical baseline small-file
BLE→BLE and USB→USB passed; process-restart BLE discovery was BLOCKED by a stale
host connection after SIGKILL, not accepted as RF failure. Four-transport machine,
restart/reset and performance acceptance remain open. No power-loss PASS is claimed.

The current implementation series retains FT1 v1 and the existing radio USER/ACK.
FLOW/CAPS/QUERY, checked DATA and remote-progress watchdog extensions below remain
deferred design material; their presence is not an instruction to implement them in
this series. Historical findings below are retained and must be checked against the
actual source before each fix.

## Manual-reset EOF finding, 2026-10-11

Physical frozen v5 USB tests: sender1B44 reset during DATA completed the same
30 KiB transfer `7f7e90780e92f035` in 20.017 s with exact SHA256 and one publication.
Reverse receiver1B44 reset caused bounded sender `LINK_FAIL` at 72/136 chunks;
receiver had 73/136. Normal agent EOF then left a suspended manifest without `.part`.
Evidence: journal `ЭТАП8_РУЧНОЙ_RESET_20261011T173207Z` and separate
`20261011T173720Z_receiver_reset_LINK_FAIL` / `20261011T173720Z_shutdown_manifest_without_part`.

Root cause of EOF deletion: `_AgentJsonlRunner._shutdown()` invoked destructive
`cancel_file_transfers()` before the resumable manager close/suspension path. The
RX cancellation deleted bytes; close could concurrently checkpoint the same incoming
object, leaving a dangling manifest. Local fix removes implicit FT user-cancel on
EOF; explicit cancellation remains unchanged. Regression reproduces absent bytes
before the fix and passes both EOF-retain/resume and explicit-cancel cases after it.
Full updated isolated-cache pytest: 545 PASS/48.56s; compileall/diff-check PASS.
Frozen v6 manifest is recorded in artifacts/HOST_MANIFEST_v6.json. Physical
EOF/retention/same-ID resume gate pending; no closure claimed.
Sender LINK_FAIL during peer downtime is separate from this deletion finding.

## Purpose

Устранить остановки FT1, при которых повреждение одного сообщения или потеря
локального подтверждения уничтожают накопленные чанки либо выглядят как молчаливое
прекращение приёма. Сохранить bounded recovery, устойчивую идентичность передачи,
докачку END/MISSING/RESULT и обязательную итоговую проверку SHA-256.

Это исходниковая задача SerialTerminal. Создание TODO не запускает следующие
исправления, аппаратные прогоны, flashing, commit или push.

## Related documents

- [FT1_RESUME.md](../FT1_RESUME.md) — действующий контракт recovery/resume.
- [TODO_029](TODO_029_FILE_TRANSFER_RECONNECT_REPAIR.md) — END/MISSING/RESULT,
  selective repair и одно сообщение для полного набора missing ranges.
- [TODO_030](TODO_030_CHATTER_FT1_NO_TELEMETRY.md) — локальное BINARY presentation
  как backpressure, без зависимости FT1 от telemetry.
- [TODO_035](TODO_035_FT1_SAME_PROCESS_PAUSE_RESUME.md),
  [TODO_036](TODO_036_FT1_PERSISTENT_RECEIVER_RESUME_STATE.md),
  [TODO_037](TODO_037_FT1_PERSISTENT_SENDER_AND_RESUME_HANDSHAKE.md) — локальное
  восстановление, durable RX partial, sender journal и resume handshake.
- [TODO_038](TODO_038_FT1_REMOTE_PROGRESS_WATCHDOG.md) — отдельный будущий watchdog
  молча остановившегося удалённого ST. Реакция на уже полученный отрицательный
  RESULT в TODO_041 не требует реализации этого watchdog.
- [TODO_011](TODO_011_CHATTER_PRESENTATION_CORRELATION.md) — корреляция ошибок
  презентации с pending submissions; учитывать при работе с pipeline.
- [TODO_MANAGEMENT_POLICY.md](../TODO_MANAGEMENT_POLICY.md).

## Current behavior and findings from source review

Публичный manager — цепочка `pipeline_manager -> manager -> resumable -> core`.
Не делать вывод о действующем поведении только по базовому `core`.

### 1. Фатальная ошибка RX удаляет накопленное и прекращает приём

`resumable.FileTransferManager._fail_incoming()` удаляет incoming manifest, затем
`core.FileTransferManager._fail_incoming()` удаляет `.part`, снимает `_incoming`,
пытается отправить отрицательный RESULT и переводит record в terminal state.
Последующие DATA этого transfer_id игнорируются: `_incoming_for()` возвращает None.
Повторный совпадающий META для такого failed record обычно отвергается; это не
тот же путь, что восстановление retained partial после idle timeout.

Оставшиеся входы в этот путь:

| Событие | Текущее последствие |
| --- | --- |
| DATA с индексом вне диапазона META | `invalid_chunk`, удаление всех накопленных чанков |
| Дубликат DATA правильной длины, но с другими байтами | `invalid_chunk`, удаление всех накопленных чанков |
| END с неправильным `chunk_count` | `missing_chunks`, удаление накопленного |
| Полный список пропусков не помещается в один MISSING | `repair_too_large`, удаление накопленного |
| Не удалось отправить MISSING | Ошибка отправки из `_handle_end()` становится фатальной ошибкой RX с удалением накопленного |
| Несовпадение wire SHA-256, original SHA-256/size, ошибка распаковки или storage | Фатальное завершение, обычно удаление partial |
| Явный operator cancel | Намеренная отмена; отличается от автоматического recovery |

Ошибки целостности нельзя просто игнорировать. Их безопасное поведение и судьба
partial должны быть определены отдельно от обычной потери сообщения.

### 2. Потеря локального BINARY echo завершает TX

В `resumable._send_message()` и DATA pipeline автоматически восстанавливаются
только `local_tx_unknown`, `local_disconnect`, `local_controller_reset`.
`binary_presentation_timeout` не входит в recoverable set: спустя 30 секунд
ожидания точного локального `> [BINARY]` FT1 завершает TX с `binary_send_failed`.
Это не доказывает, что DATA не ушёл в эфир или не дошёл до второго ST.

Другие неавтоматически восстанавливаемые ошибки, которые нужно классифицировать:
`local_tx_timeout`, `local_tx_failed`, `controller_ready_timeout`,
`binary_presentation_unavailable`, ошибки pipeline и `send_rejected`.
Последний возникает по строкам `[SYS] INPUT TOO LONG`, `[SYS] SEND QUEUE FULL`,
`[SYS] RADIO UNAVAILABLE`, `[SYS] BINARY ...`, `TX FATAL ...`,
`TX FRAME BUILD ERROR ...`. Не считать все причины одинаково временными и не
повторять постоянную ошибку бесконечно.

Sender journal при обычном failed TX сохраняется; явная отмена его удаляет.
Сохранённый журнал позволяет возобновление, но не означает, что текущая попытка
автоматически продолжится.

### 3. Отрицательный RESULT не останавливает отправку DATA сразу

`feed_binary()` сохраняет remote RESULT и уведомляет condition. Однако циклы
обычной, pipelined и repair DATA отправки проверяют cancel, а не remote failure.
RESULT проверяется при resume handshake и ожидании завершения после DATA/END.
Поэтому уже отказавший RX может игнорировать хвост передачи, а TX продолжает
занимать эфир. Это подтверждено физическим логом ниже.

### 4. Некоторые исключения действительно подавляются без события ошибки

- `core._rx_loop()` делает `except Exception: continue` вокруг обработчиков
  META/DATA/END. В частности, OSError из чтения/записи чанка или ошибка durable
  checkpoint могут не получить диагностического transfer event.
- Вызов `_expire_stale_incoming()` после `queue.Empty` находится вне этой защиты.
  Ошибка принудительного checkpoint при idle sweep может завершить общий FT1 RX
  worker, оставив приём без работающего обработчика.
- `ChatterBinaryUserAdapter.feed_line()` сохраняет `last_parse_error` при плохом
  base64, а исключение application receiver callback подавляет. Это дополнительные
  границы потери данных, которые нужно сделать наблюдаемыми без остановки общего
  session notifier.
- Неразбираемый FT1 payload отвергается без transfer failure. Отбрасывать повреждённое
  сообщение допустимо; диагностика должна отличать это от остановки всего приёма.

Выводы этого раздела получены чтением исходников; ошибки диска/worker death не
были физически воспроизведены в описанных прогонах.

### 5. Idle timeout и bounded limits уже имеют отдельную семантику

Действующий публичный `manager._expire_stale_incoming()` через 120 секунд без
META/DATA/END сохраняет durable partial/manifest и освобождает runtime ownership.
История показывает `failed / remote_sender_timeout`, но совпадающий META может
снова открыть накопленное в том же процессе. Не заменить это удалением partial.

TX ограничивает local recovery 60 секундами, repair — 8 раундами, control replay —
3 повторами с интервалом 30 секунд; общий result deadline — 3600 секунд.
Истечение лимита должно быть явным и сохранять пригодное resumable состояние.
Также различать настоящий runtime failure, ошибку старта по журналу/идентичности
и intentional cleanup по TTL/бюджету хранения.

## Physical evidence: 2026-10-10

Топология измерений: TX или RX через USB — LoRa-Chatter-72E0; вторая нода,
LoRa-Chatter-1B44, соединена со ST через BLE. Обе были запитаны через USB.
PHY: 470 MHz, SF7, BW500, TX power 2 dBm. PNG: `2.png`, original 760052 bytes,
wire 758496 bytes, 3342 DATA chunks, обычный payload чанка 227 bytes.
Все указанные ниже часы — Europe/Moscow (UTC+03:00).

### A. PNG USB -> BLE: INPUT TOO LONG на 30,08%

Run basename: `/tmp/chatter-usb-ble-20261010T173919Z`.
В 20:47:50.088 USB-нода напечатала `[SYS] INPUT TOO LONG: max 243 bytes`.
ST завершил TX с `binary_send_failed / send_rejected`: 1005 settled chunks,
228135 bytes, elapsed 130.064 s. RX имел 1006 chunks / 30,11%; сам в этот момент
не прекращал приём. Позже операторская отмена через агента завершила RX.
Не приписывать эту отмену автоматическому отказу приёмника.

### B. PNG USB -> BLE: локального echo нет, но чанк доставлен

Run basename: `/tmp/chatter-png-20261010T180405Z`, transfer_id `49360f461337dc14`.
После USB reconnect ST восстановил отправку, затем в 21:06:04.597 завершил TX с
`binary_send_failed / binary_presentation_timeout`: 164 settled chunks / 4,91%,
elapsed 55.464 s. RX имел 165 chunks / 4,94%.

Офлайн-разбор сырых логов подтвердил: ST отправил DATA index 164 длиной 243 bytes
(227 data bytes), и принимающий ST через BLE получил этот DATA целиком.
В USB RX отправителя точное локальное echo index 164 не обнаружено; index 163
наблюдался. Доставка состоялась, но потеря локального подтверждения остановила TX.
RX позже был явно отменён агентом, чтобы закончить попытку.

### C. PNG BLE -> USB: обрезанный DATA, отказ RX, продолжающийся TX

Тот же run basename; reverse start переиспользовал sender journal/transfer_id,
но RX начал сбор с нуля. Не описывать его как новый transfer_id.

- Передающий ST записал полный DATA index 2254: 243 raw bytes / 227 data bytes /
  324 base64 chars в 21:11:37.814, forensic log line 40727.
- В сыром USB RX принимающего ST строка уже короче: 195 raw bytes / 179 data bytes /
  260 base64 chars; удалены 64 подряд идущих base64 символа из середины.
  RX fragments — forensic lines 40744–40746, 21:11:38.018–.025.
- В старой логике RX удалил partial и завершился с `invalid_chunk` на 2254 chunks /
  67,46%. Terminal event появился в 21:11:43.290 после доставки error RESULT.
- TX получил отрицательный RESULT уже в 21:11:38.412, затем ещё раз в
  21:11:43.507, однако продолжал DATA. Агент явно отменил TX в 21:12:32.074
  на 2664 chunks / 79,73%. Это не автоматическая остановка TX.

В логе ядра USB-хаб выдавал ошибки с 21:11:37.967, затем отключился вместе с
обоими USB-устройствами около 21:11:38.490. USB-тракт — основной подозреваемый
для потери 64 символов, но точный компонент/место потери не доказаны.
Обрезанная строка полностью пришла до регистрации disconnect в ST; не объяснять
её склейкой строк после reconnect и не приписывать её LoRa CRC без доказательств.
После исследования оператор сообщил о прямом подключении нод к ноутбуку;
повторный прогон с этой топологией ещё не выполнялся.

### D. Более ранний WEBP: USB disconnect и local_tx_timeout

Run basename: `/tmp/chatter-usb-ble-20261010T172307Z`.
WEBP USB -> BLE остановился на 15,11% с `binary_send_failed / local_tx_timeout`
после USB disconnect; в TX thread наблюдалась ошибка `termios` / I/O во время flush.
RX имел 20 chunks / 16,78% и позже был явно отменён. Это отдельный отказ;
его нельзя называть тем же `invalid_chunk` или тем же presentation timeout.

### Evidence boundary and checksums

Это временные QUICK-логи, не опубликованный canonical RUN bundle. Если файлы из
`/tmp` исчезнут, не утверждать, что оригинальные артефакты по-прежнему доступны.
У каждого basename были `.log`, `.console.log`, `.fttiming.jsonl`; последний
содержит структурированные `ft1_event` и timestamps, сырые байты — в `.log`.
Полные payload/base64 не вставлять в TODO, stdout агента или контекст при анализе.

SHA-256 `.fttiming.jsonl`:

- `chatter-usb-ble-20261010T173919Z`:
  `381dd3a4d16b79a789f91dc69019b7e073f95c70e77f5b1c7ac22d13e01b1374`.
- `chatter-png-20261010T180405Z`:
  `05c3d9eb7e9f8d1454f6083f2869194c4ebae01ff5dd87047ac01c9b2bbd5628`.
- `chatter-usb-ble-20261010T172307Z`:
  `4a2628b6252c89ebb62bd2123cd123d596ef42e0dd1f7065a82dabb7263d8219`.

Наблюдения сделаны до wrong-length fix. Они не доказывают физическую валидность
изменённого дерева и не фиксируют проверенную firmware build provenance.

## Already implemented locally

- [x] DATA неправильной длины отбрасывается с событием `chunk_rejected`, не
  удаляет partial/bitmap; END/MISSING запрашивает отсутствующий чанк.
- [x] Если правильная копия уже сохранена, плохой по длине дубликат её не портит.
- [x] Добавлены 5 parametrized regression cases: укороченный средний чанк,
  повторное повреждение при repair, короткий/длинный последний чанк,
  плохой дубликат после правильного.
- [x] Синхронизированы README, AGENT_API, FILE_TRANSFER, FT1_RESUME и локальный
  `.agents/skills/serialterminal-agent/SKILL.md` для wrong-length behavior.

Незакоммиченный implementation checkpoint поверх указанного HEAD:

- `src/serialterminal/file_transfer/core.py` SHA-256:
  `b2696d54319f879836046fd2870eb188a30431458c2d9d8727a30654f496b779`.
- `tests/test_file_transfer_core.py` SHA-256:
  `9679ec79f7b9ed30093ebb93ef84e9abbaceeecb1355aef88ec14017f8366838`.

Validation до создания TODO: targeted `bad_length` — 5 PASS; full suite —
427 PASS с изолированным `SERIALTERMINAL_CACHE_FILE`. Первый full-suite запуск
зависел от реального device cache; изоляция cache устранила эту внешнюю зависимость.
Новый физический PNG smoke после исправления не выполнялся.

## Target behavior and design decisions to resolve

1. Повреждённое отдельное DATA/END не должно уничтожать валидные накопленные
   чанки. Неизвестный/невалидный индекс безопасно отвергать; продолжать bounded
   ожидание корректных сообщений и сохранять пригодную для resume идентичность.
2. Конфликт одинакового индекса с разными байтами не разрешать произвольным
   выбором копии. Определить безопасную invalidation этого индекса в memory и
   durable bitmap и повторный запрос; итоговая SHA-256 остаётся обязательной.
3. Потерю точного локального BINARY echo для идемпотентного FT1 сообщения
   обрабатывать bounded replay/recovery, включая fallback pipeline к earliest
   outstanding DATA. Generic команды не повторять автоматически.
4. При неудачной отправке MISSING или исчерпании recovery сохранить пригодные
   partial/manifest и явно показать причину остановки/ожидания возобновления.
5. `repair_too_large` остаётся явной границей FT1 v1. Сохранить накопленное и
   определить поддерживаемый следующий шаг/explicit resume. Для negotiated
   extension ниже выбрать явные bounded repair batches; legacy MISSING не
   переопределять и не вводить бесконечный whole-file restart.
6. Уже полученный отрицательный RESULT должен своевременно остановить выдачу
   новых DATA, включая repair и pipeline. Учесть максимум два уже выданных DATA,
   корректно освободить ownership и не отменять посторонние операции.
7. Ошибки RX handler, callback, disk/checkpoint и idle sweep должны давать
   диагностическое событие с transfer_id/phase/reason. Общий RX worker не должен
   молча умирать или пропускать ошибки без объяснения; нельзя продвигать durable
   bitmap, если bytes/manifest не удалось сохранить.
8. Для hash/decompression/identity conflicts отдельно выбрать безопасный путь:
   данные не публиковать, сомнительный bitmap не использовать как доказательство
   корректных чанков. Без per-chunk checksum нельзя обещать точечную локализацию
   произвольного повреждения только по итоговому SHA-256.
9. Явный cancel, shutdown, timeout/recovery exhaustion, ошибка metadata/identity,
   cleanup policy и повреждение одного сообщения должны иметь различимые
   результаты. Не менять намеренную operator cancellation на вечное resume.

## Selected architecture: repair during DATA, before END

Design update: 2026-10-10, по запросу оператора после физических прогонов.
Это выбранное направление следующей реализации, а не описание уже работающего
протокола. Все параметры ниже — стартовые значения для тестов и измерений.

### Два уровня подтверждения и общий путь восстановления

Firmware USER ACK продолжает подтверждать radio transaction между нодами.
Он не содержит файлового состояния и не заменяется: ST не может вкладывать в него
repair, поскольку firmware не знает, какие чанки дошли через USB/BLE до ST.

Нужен отдельный FT1 host-to-host ответ принимающего ST, функционально похожий на
редкий ACK с selective repair. Он передаётся как обычный BINARY USER через
существующую firmware. В отсутствие пропусков подтверждает durable progress;
при пропусках несёт ranges для докачки. Название `FLOW` / `REPAIR_STATUS` пока
проектное; окончательные enum/encoding фиксируются перед реализацией.

```text
ST sender -> local node -> LoRa -> peer node -> ST receiver
                 firmware USER/ACK остаётся прежним

META + negotiated flow capability
DATA 0..N                         -> durable bitmap, gaps
          <- FLOW(progress, missing ranges)
stop new original DATA; drain <=2 outstanding submissions
REPAIR DATA for requested ranges -> fsync/checkpoint
FLOW_QUERY                        ->
          <- FLOW(repair complete / remaining gaps)
continue original DATA at saved cursor N+1
...
final FLOW drain + END             -> size/hash/decompression verification
          <- RESULT OK only after verified publication
```

Один FT1 coordinator владеет состоянием передачи и выбором следующего сообщения.
Он связывает local-node recovery, resume и repair; reset ноды сам по себе не
разрешает стирать file state или объявлять доставку.

### Ownership и concurrency

- Generic Transport/ManagedSession доставляют непрозрачные bytes и local outcomes.
  Profile adapter знает `/bin`, controller lifecycle и точное local echo.
- FT1 coordinator знает transfer identity, источник, durable bitmap, запросы
  control/repair и ограничения. Protocol codec только кодирует/проверяет сообщения.
- RX обработчик быстро разбирает сообщения, обновляет состояние и помещает работу
  в bounded control outbox. Он не должен блокировать обработку следующего DATA,
  RESULT или lifecycle event на ожидании отправки собственного ответа.
- Для одной локальной сессии scheduler сериализует control/repair/DATA submissions.
  Не запускать конкурирующие бесконтрольные sender threads или вложенные repair loops.
- Приоритет: cancel/terminal outcome, local lifecycle recovery, нужный control
  exchange, repair DATA, новый original DATA. Периодический status coalesce;
  terminal/repair request не теряется из-за переполнения очереди status.
- Временный disk/checkpoint failure не позволяет объявить durable progress.
  Состояние/причина видны в agent/TUI; восстановление ограничено deadline.

### Receiver: что считать пропущенным и когда просить repair

Хранить отдельные memory received set, durable received map и observed frontier.
Bitmap/диапазоны описывают sparse chunks, а не только длину `.part`.
`durable_prefix` — индекс первого чанка, который receiver не может доказать
сохранённым; sparse durable chunks после него также сохраняются.

Не считать отсутствующими все ещё не отправленные чанки до конца файла.
В ранний repair включать только отверстия ниже доказанного frontier: из реально
полученных следующих DATA или из валидного sender checkpoint с exclusive
`next_original`. Пропуск последнего/хвоста, за которым новых DATA нет, обнаруживается
по checkpoint/END, а не по догадке. Короткое bounded окно на переупорядочение и
задержку приёма уменьшает лишнюю докачку; валидный дубликат безопасен.

Trigger оценивается по encoded ranges, а не по количеству байтов файла:

1. После coalescing диапазонов control reply заполнен примерно на 70–75%.
2. Либо накопилось значимое число missing chunks, даже если они занимают один range.
3. Либо oldest confirmed hole ждёт дольше repair latency budget.
4. Либо sender запросил очередной progress checkpoint / final drain.

До ответов, на которые sender будет полагаться, сохранить bytes и checkpoint
manifest. Сам запрос «эти чанки отсутствуют» не считается подтверждением доставки.
Ошибочно объявленная дырка в ещё не checkpointed чанке приводит максимум к
безопасному повтору, но не к пропуску несохранённых bytes после crash.

Стартовая политика для эксперимента: около 18 ranges при capacity 25 ranges,
либо 32 missing chunks, либо возраст подтверждённой дырки около 10 s.
Значения вывести из transport capacity и настройки policy; не зашивать 243/25
в общий FT1 код. Немедленный repair на каждом DATA не требуется.

### Control packet budget: legacy и новая negotiated extension

Legacy MISSING: 12-byte common header + 1-byte count + 8 bytes/range.
При capacity 243 влезает `floor((243-13)/8) = 28` ranges.
Длинный непрерывный пропуск может быть тысячами chunks и занимать один range;
множество одиночных пропусков заполняет пакет намного быстрее.

Предпочтительная новая FLOW reply схема для расчёта бюджета:

```text
FT1 common header (including transfer_id)       12 bytes
flow_session: uint64                             8
flags: uint8                                    1
status_seq: uint32                               4
frontier: uint32 (exclusive covered frontier)    4
durable_prefix: uint32                           4
repair_id: uint32                                4
range_count: uint8                               1
message_crc32: uint32                            4
ranges: repeated (start:uint32, count:uint32)    8 each
fixed total                                    42 bytes
```

При capacity 243: `floor((243-42)/8) = 25` ranges; 18 ranges дают 186 bytes,
оставляя запас. Если финальное encoding меняет header, пересчитать capacity и
порог через codec. QUERY/CAPS могут иметь отдельное компактное encoding.
Не передавать JSON по радио; uint32 overflow и malformed fields проверяются.

Новая extension явно разрешает bounded partial repair batches. Один FLOW запрос
содержит самостоятельную порцию oldest missing ranges и признак, что есть ещё
пропуски. Это не утверждение, что перечислен весь missing set. Receiver не обязан
собирать все дырки в одном пакете: после исправления порции сообщает следующую.
Таким образом даже накопившиеся за долгий disconnect >25 ranges не уничтожают
передачу. Нет необходимости буферизовать/пересобирать многостраничное сообщение.

Это явное расширение host FT1, а не скрытая смена смысла legacy MISSING.
Для legacy peer правило «один MISSING для полного набора» остаётся; если он не
помещается, сохранить partial и показать explicit resume/unsupported repair limit.
Нельзя обещать безлимитную раннюю selective repair со старым протоколом.

### Sender: приостановка, repair и возвращение к потоку

Хранить отдельно:

- `next_original` — следующий ещё не выданный original DATA index;
- pending local submissions (сейчас максимум 2) и их ambiguous outcomes;
- активный `repair_id`, bounded queue ranges и repair cursor;
- receiver-proven durable progress и известные gaps;
- checkpoint/retry deadlines и сохраняемый sender journal.

При валидном FLOW с gaps перестать выдавать новые original DATA. Уже выданные
максимум два сообщения не «отправить повторно наугад» и не потерять: штатно drain
или local bounded recovery. Затем читать requested indexes из той же prepared
wire representation и посылать те же transfer_id/chunk_index/bytes.
Repair seek не меняет `next_original`; progress counters не считают дубликаты как
новые байты и не растут за 100%.

Все ranges валидировать относительно chunks_total, matching flow_session и
фактически issued frontier. Запрос будущего невыданного индекса отвергать безопасно.
Negative RESULT обрабатывать во всех состояниях сразу; больше не выдавать DATA.

После repair batch сделать контрольную проверку, что receiver durably принял
исправления. Local echo repair DATA недостаточно. Receiver отвечает ещё missing
ranges либо repair complete для согласованного frontier. Если есть старые gaps,
чинить следующую bounded порцию, затем продолжать original поток с сохранённой
позиции. Не рекурсировать при повторных запросах и не восстанавливать current
state из одного overwritten `remote_missing` slot: нужны очередь/merge и явный
активный repair exchange.

Пример: original cursor = 600; receiver имеет 0..599 кроме 12, 90..92 и 410.
FLOW вызывает отправку 12,90,91,92,410; после durable подтверждения sender
возвращается к 600, а не гонит suffix с 12 и не ждёт конца большого файла.

### Надёжность control, stale replies и bounded recovery

Receiver хранит активный repair request до durable закрытия соответствующих gaps.
Потерянный запрос не считается исполненным по факту local send: повторить тот же
repair_id/status snapshot с ограниченной частотой либо ответить на sender query.
Когда bitmap изменился, формировать новый sequence/snapshot; не создавать новый
request на каждый ещё приходящий original DATA.

`flow_session` — новый случайный uint64 для согласованной runtime flow-сессии.
После process restart/re-negotiation создавать новый session token, сохраняя
transfer_id. CAPS selection и QUERY/ответы связаны с этим token. Старые control
messages предыдущего runtime не могут подтвердить текущие pending repairs.
`status_seq` монотонен внутри token; дубликаты идемпотентны, старые snapshots
не откатывают state. Явная invalidation конфликтующего чанка может уменьшить
proven prefix и должна отличаться от stale reply; не применять безусловный max
к prefix в обход invalidation. Перед переполнением seq/id обновить token явно.

Sender тоже регулярно инициирует редкий checkpoint: если RX потерял большой
отрезок или вообще перестал получать DATA, threshold-trigger может не возникнуть.
Стартовая оценка — query примерно раз в 10 s активной передачи и hard credit
limit порядка 256 original chunks сверх receiver-proven durable contiguous prefix.
Кто сработал первым, приостанавливает original submissions, drain локальный
pipeline и оставляет окно эфира для control reply. Exact counters/timeout требуют
тестов: sparse progress не разрешает бесконечно обходить одну старую дырку.
Нормальная передача не ждёт host ACK после каждого чанка.

Periodic progress и ранний repair используют один control exchange. Это
согласованный design с TODO_038; не реализовывать второй независимый watchdog,
второй таймер или конкурирующий sender loop. Предыдущая отсрочка TODO_038 остаётся
для runtime implementation до согласования/измерения нового baseline; этот TODO
сейчас документирует объединённую архитектуру по явному запросу оператора.

После bounded retry/deadline без ответа — observable remote stall/suspend с
сохранением journal/partial. Recovery может повторить handshake и продолжить
тот же файл. Пределы repair считать по отсутствию прогресса/повтору одной порции,
а не прежними 8 раундами на всю жизнь большого файла: штатных порций может быть
гораздо больше. Общий deadline/budget остаётся конечным, cancel всегда доступен.
Параметры retries и timeout фиксируются и проверяются при реализации.

### Целостность локального USB/BLE текстового канала

Radio CRC не защищает base64/bytes после ноды на пути к ST. Обрезание часто видно
по длине, но повреждение одинаковой длины может поменять chunk index, range или
proven prefix. Новые FLOW/QUERY/CAPS должны иметь CRC32 по целому сообщению,
включая header/identity/control fields и body, исключая само CRC поле. Проверка
до применения полей; точную CRC variant/byte order/test vectors закрепить в codec.
Это защита от случайной порчи, а не аутентификация.

Для раннего обнаружения повреждения DATA предпочтительна negotiated capability
`checked_data_v1` и отдельный optional DATA_CHECKED type:
12-byte common header + uint32 chunk_index + uint32 CRC + payload. При capacity
243 полезный chunk_size <=223. CRC покрывает identity/index/payload; невалидный
пакет отвергать целиком, не используя недостоверный index для изменения bitmap
или observed frontier. Пропуск обнаружится по следующим достоверным DATA/QUERY.

Для нового файла выбирать META chunk_size с учётом checked encoding до отправки
META и замораживать identity. Conservative size 223 допустим и для legacy DATA,
поэтому после CAPS fallback не меняет chunks_total внутри уже объявленной передачи.
Старый retained journal с chunk_size 227 нельзя молча переделать: продолжать его
existing DATA encoding и явно обозначить отсутствие chunk CRC, либо начать новый
transfer_id по отдельному решению оператора. Старые peers не получают DATA_CHECKED
без согласования; final SHA-256 остаётся обязательным при любом encoding.

Итоговый выбор checked DATA/default chunk policy закрепить перед реализацией и
измерить изменение throughput. До этого не обещать точечную починку произвольной
same-length corruption для legacy DATA только по финальному SHA-256.

### Capability negotiation и совместимость

Старые DATA/META/END/RESULT/MISSING/RESUME encoding не переопределять. Предпочтение —
новые optional FT1 control types/capability поверх существующего opaque transport.
Номера enum и точная схема CAPS согласуются вместе с tests/compatibility contract.

После META провести bounded CAPS advertise/select/confirm с поддержкой
`midstream_repair_v1`, привязанной к свежему flow_session. До взаимного подтверждения
не считать early FLOW поддерживаемым. Отсутствие поддержки/ответа даёт явный
legacy fallback с известными ограничениями; старый peer не должен зависнуть от
unknown message. New/new, new/old и old/new проверить отдельно.

Runtime resume после перезапуска начинает fresh flow negotiation. Durable bitmap
и wire identity сохраняются, runtime repair queue и старые control tokens не
объявляются durable автоматически. Completed tombstone по-прежнему завершает
replayed META/END без повторной публикации файла.

### Finalization и failure contract

До END выполнить final repair drain до chunks_total либо bounded unresolved state.
END остаётся обязательным: durable chunks и FLOW progress не заменяют итоговую
wire SHA-256/original SHA-256, распаковку и атомарную публикацию. После END возможны
поздний gap, повторный запрос repair и повторный END; success только по RESULT OK.

Для ошибочного DATA индекс/длина -> reject/invalidate gap с сохранением остальных;
для lost local presentation -> bounded same-message replay; для control loss ->
same-request retry/query; для отсутствия peer ST -> pause/suspend; для disk failure
-> явная ошибка без ложного durable ACK; для несовпадения file identity/hash ->
не публиковать и не выдавать сомнительные чанки за корректные. Физический node reset
остаётся отдельно авторизуемой операцией и не требуется для обычной докачки.

### Observability

Показать sender-issued и receiver-durable progress отдельно, число missing chunks
и ranges, active repair_id, saved original cursor, retries/deadline и причину паузы.
Agent/TUI различают original sending, waiting flow, repairing, recovering local node,
remote stalled/suspended и final verifying; точные публичные state/event names
фиксировать в AGENT_API при реализации, а не объявлять уже существующими.
Байты файла не выводить; logs содержат IDs, counts, timing и hashes.

## Invariants and scope boundaries

- Только SerialTerminal; firmware source/ACK/PHY, reset и flashing вне scope.
- Сохранить существующие FT1 message encoding, payload capacity и DATA pipeline
  window. Новые control types вводить только через явную negotiated extension
  с capability/fallback contract, описанную в выбранной архитектуре выше.
- Stable transfer_id/chunk_index и точная prepared wire identity обязательны.
- Local presentation не доказывает RF delivery; RF ACK не доказывает приём ST.
- Не ослаблять wire/original SHA-256, декомпрессию, ограничения размеров,
  безопасные пути и проверку sender journal.
- Bounded retries, deadlines и responsive cancel/close обязательны.
- Каждый ST управляет только своей нодой. Recovery не должен зависеть от общей
  видимости двух нод одним coordinator.
- Совместить planned periodic progress TODO_038 и ранний repair в одном control
  exchange. Документирование этой архитектуры не включает её в runtime; перед
  реализацией синхронизировать TODO_038 и baseline/compatibility contract.
- USB-хаб/кабельная проблема объясняет окружение прогона; этот TODO исправляет
  устойчивость ST и не обещает починить физический USB.

## Implementation

- [ ] Зафиксировать negotiated control codec/CAPS, token/sequence semantics,
  packet budget, control CRC/checked DATA policy и old/new fallback;
  синхронизировать related TODO_029/038.
- [ ] Реализовать receiver gap tracking/triggers и durable FLOW reply с bounded
  batches, coalescing и control outbox без блокировки RX worker.
- [ ] Реализовать единый sender scheduler: stop new DATA, drain pipeline,
  selective midstream repair, durable confirmation и возврат к saved cursor.
- [ ] Добавить общий progress/repair checkpoint с time/credit bound, control retry,
  stale token rejection и сохранением partial/journal при отсутствии ответа.
- [ ] Сделать final repair drain и END verification совместимыми с late gaps,
  process restart, tombstones и legacy peer.

- [ ] Зафиксировать таблицу error -> retry/suspend/fail/cancel -> судьба partial,
  manifest и sender journal; сверить её с FT1_RESUME и TODO_029/035/036/037.
- [ ] Исправить remaining DATA/END rejection без разрушения пригодного RX state.
- [ ] Определить безопасную invalidation конфликтующего DATA и её durable ordering.
- [ ] Добавить bounded recovery для потерянного локального echo и классифицировать
  остальные BINARY failures; сохранить ограничения pipeline и generic write ambiguity.
- [ ] Сохранять RX partial при неудачной отправке MISSING и `repair_too_large`.
- [ ] Обрабатывать отрицательный remote RESULT во всех DATA submission/repair loops.
- [ ] Устранить silent exception paths и защитить FT1 worker, включая idle sweep.
- [ ] Обеспечить диагностические agent events/status и понятное TUI состояние без
  вывода содержимого файла; runtime failure не должен выглядеть как зависший процент.
- [ ] Проверить, что ошибка cleanup/создания durable state не удаляет существующий
  partial, который текущая операция не создавала.
- [ ] Обновить AGENT_API, FILE_TRANSFER, FT1_RESUME, README и agent skill после
  принятия/реализации новой семантики; inventory отражает точный checkpoint.

## Validation

### Automated

- [ ] Gap возникает задолго до END: threshold/age/checkpoint вызывает repair,
  original cursor приостановлен, чинятся только gaps, поток продолжается с cursor.
- [ ] Threshold зависит от encoded range count: contiguous burst и isolated gaps
  учитываются правильно; missing tail обнаруживается по frontier QUERY.
- [ ] >packet-capacity gaps после reconnect обрабатываются несколькими bounded
  batches без удаления partial и без многопакетной reassembly legacy MISSING.
- [ ] Lost/duplicated/delayed FLOW/QUERY/CAPS, reordered reports и старые runtime
  tokens не теряют запросы, не подтверждают неверные chunks и не вызывают loops.
- [ ] Контрольная проверка repair опирается на durable RX, а не local echo;
  crash до/после fsync/manifest даёт safe repeat с правильным итоговым hash.
- [ ] No DATA reaches receiver, receiver process dies или peer отвечает только
  firmware ACK: time/credit bound останавливает original stream, сохраняет resume.
- [ ] Corrupt control header/body, same-length DATA corruption и ошибочный chunk
  index выявляются до изменения state; legacy limitations и checked/unchecked
  resume identity проверены.
- [ ] Wrong transfer/session/id/frontier/range и conflicting duplicate не двигают
  cursor неправомерно; explicit invalidation корректно уменьшает proven prefix.
- [ ] Pipeline window <=2; early repair/negative RESULT/cancel учитывают уже выданные
  submissions, включая local recovery и repair-on-repair, без новых sender threads.
- [ ] New/new, new/old, old/new, restart обоих host процессов и tombstones;
  legacy full-set MISSING limit остаётся явным и сохраняет пригодный partial.

- [ ] Bad index, conflicting duplicate, wrong END count сохраняют пригодные
  остальные чанки и дают наблюдаемую причину; повторы/repair идемпотентны.
- [ ] Потерянное/повреждённое локальное echo при реально доставленном DATA
  вызывает bounded replay и завершение с правильным hash, не duplicate corruption.
- [ ] Те же случаи в pipeline, после fallback и во время selective repair.
- [ ] Постоянное отсутствие echo/repeated rejection исчерпывает лимит без hang,
  сохраняет resumable state; cancel/close остаются отзывчивыми.
- [ ] Отказ отправки MISSING, oversized missing set и повторная попытка после
  сохранения partial: результат детерминирован, пригодные чанки не теряются.
- [ ] Отрицательный RESULT в середине обычной/pipelined/repair DATA отправки
  останавливает новые submissions; поздний/дублированный RESULT безопасен.
- [ ] Injected OSError, fsync/manifest/callback failures, включая idle sweep:
  ошибка видна, worker работает или явно завершён управляемым образом,
  durable bitmap не продвигается без сохранения bytes.
- [ ] Idle timeout + совпадающий META продолжают retained partial в том же
  процессе; restart sender/receiver/both сохраняет identity и корректную докачку.
- [ ] Hash/decompression/identity failure никогда не публикует неверный файл.
- [ ] Existing cancellation, completed tombstones, lost-RESULT и compatibility
  tests остаются зелёными; full suite с изолированным device cache.

### Physical

- [ ] Большой файл с missing ranges в середине: repair начинается до END,
  исходный поток возобновляется с saved cursor и final SHA-256 PASS.
- [ ] Потеря самого repair request/reply и долгое отсутствие принимающего ST:
  finite time/credit window, bounded recovery и same-transfer resume.
- [ ] Измерить число control packets, latency до repair, размер batches и overhead
  при sparse/burst gaps и без ошибок относительно одинакового baseline.

- [ ] Малый файл и большой PNG USB -> BLE и BLE -> USB, неподвижные ноды,
  прямое подключение к ноутбуку, power 2 dBm; final size/SHA-256 PASS.
- [ ] Повторить сценарии USB/BLE reconnect и same-transfer resume; различать
  controller lifecycle, local presentation, RF delivery и ST acceptance.
- [ ] Проверить recovery потерянного echo/повреждённого DATA через управляемую
  инъекцию, если естественный сбой не повторяется; отмечать инъекцию явно.
- [ ] Сравнить скорость/repair overhead с baseline при одинаковой топологии/PHY.
- [ ] Анализировать raw byte logs офлайн с ограниченным stdout; сохранять итоговые
  числа, timestamps и hashes без размещения PNG/base64 в контексте агента.

## Result

Status: PARTIAL. Wrong-length DATA fix локально реализован и автоматически проверен;
остальной scope OPEN. Физическое подтверждение изменённого кода OPEN.
Commit/push/CI для этих локальных изменений не выполнялись. Документ содержит
выбранную по запросу оператора архитектуру early repair/flow control; она ещё не
реализована и не протестирована. Создание и дополнение TODO меняют только
документы задачи и inventory; новые runtime changes отсутствуют.

Final experimental checkpoint 2026-10-11: v6 EOF-retain/same-ID resume physically
PASS; frozen-v5 normal transport matrix 16/16 application PASS; v6 USB/BLE
META/END resets, repeated reset and recovery cancel PASS; four-topology recovery
coverage and current HCI interval7.5ms/MTU247/DLE251/244+117 writes recorded.
Full software suite remains 545 PASS/48.56s. Results and evidence boundaries:
`/home/dream/coding/журнал экспериментов/ИТОГИ_ПУНКТОВ_1-8_2026-10-11.md`.
TODO_041 broader FLOW/midstream scope remains OPEN; TODO_042 remains DEFERRED.
No new commit/push/current-head CI. Work stopped at experimental stage8.
