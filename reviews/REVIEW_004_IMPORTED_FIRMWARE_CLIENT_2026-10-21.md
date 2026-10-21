# Imported client scope: firmware/client review 21 октября 2026

REVIEW-ID: REVIEW_004
Разобрано в TODO: TODO_013, TODO_049, TODO_058, TODO_059, TODO_060, TODO_061, TODO_062
Status: COMPLETE
Verdict: RED (client software snapshot)
Date UTC: 2026-10-21 (точное время исходного review UNKNOWN)
Reviewer: Imported; исходный автор не указан; Codex оформил клиентскую часть Chatter REVIEW_006.

## Reviewed state и provenance

Repository: https://github.com/dreamworkerln/serialterminal
Branch: `dev_tui_exp_recursive_missing`
Reviewed snapshot mapped to commit: [a34631e861d1477c48f5ad2bc15dad15564f73f6](https://github.com/dreamworkerln/serialterminal/commit/a34631e861d1477c48f5ad2bc15dad15564f73f6)
Base / range: N/A — snapshot review; accepted regression base не выбирался.
Checkout при импорте: clean до docs updates; 277/277 inventory files совпали с working tree и committed bytes.
Original target: F:\LoRa\client без Git metadata на Windows review-хосте.
Firmware counterpart: `3d085959ffb5e79e48675574358a02a4b0b76be0`, 281/281 files совпали.

Источник: [Chatter REVIEW_006](../../../c++/lora-sack/chatter/reviews/REVIEW_006_CODE_REVIEW_FIRMWARE_CLIENT_2026-10-21.md),
[побайтный оригинал](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/original_report.md), SHA-256 `f92b12ac683613bef3e872034a998136b6cb681d0decf9db2592be604b05eede`.
[Import verification](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/import-verification.json).
Номер 006 принадлежит Chatter; здесь выделен независимый REVIEW_004 по local policy.
Это регистрация того же прохода, не новое ревью и не повторный test run.
F-ID сохранены из общего отчёта; F002/F009/F010/F011 — firmware scope.
Previous review: исходный client audit 20 октября не приложен; REVIEW_002/F001 уже ведётся в TODO_049. Локальный REVIEW_003 имеет другой TUI scope.

## Scope

Chatter lifecycle, ownership очереди, SPP/BLE ambiguous writes, Windows FT1/TUI
и exception-safe open. Full pytest/Linux CI, real radio/USB/BLE и rendering
acceptance не выполнены исходным проходом. Успех repro подтверждает дефект.

## Findings

### F001 P1 Пользовательский текст становится доказательством перезагрузки

Follow-up: [TODO_058](../todos/TODO_058_CHATTER_LOCAL_LIFECYCLE_GRAMMAR.md).

**Место:** [machine_client.py:293](../src/serialterminal/profiles/chatter/machine_client.py), `ChatterMachineClient.feed_line`; последствие в [discard_binary_pipeline:379](../src/serialterminal/profiles/chatter/machine_client.py). Аналогичная неограниченная проверка маркеров есть в [binary_user.py:364](../src/serialterminal/profiles/chatter/binary_user.py).

`feed_line()` ищет `ESP-ROM:`, `rst:` и `[SYS] CHATTER READY` через `marker in line`. Разбор не отделяет локальную boot-строку от обычного принятого текста. Между тем firmware выводит текст USER как `< [RSSI/SNR Q] message`, а agent и TUI передают такие строки этому же адаптеру. [Firmware presentation](../../../c++/lora-sack/chatter/src/Scheduler.cpp), [agent forwarding](../src/serialterminal/agent_core.py), [TUI forwarding](../src/serialterminal/tui_core.py).

**Воспроизведение:**

1. Production `Scheduler` с native radio stubs принимает обычный текстовый USER `first:`. Production `TerminalIo` формирует `< [-30/8 Q0] first:`.
2. Production `ChatterMachineClient` согласует epoch 41 с локальной моделью node и получает ACCEPTED для request 1. Узел не перезапускается; request остаётся outstanding.
3. В адаптер передаётся строка, полученная на шаге 1. Подстрока `rst:` внутри `first:` вызывает `mode=failed` и `local_controller_reset`.
4. `settle_binary()` завершается этой ошибкой. `discard_binary_pipeline()` принимает ложный reset как доказательство и очищает `pending/order`, хотя у модели node request 1 остаётся активным в epoch 41.

```text
line                         < [-30/8 Q0] first:
machine mode                 machine -> failed
settle error                 local_controller_reset
host pending after discard   0
node outstanding             [1]
node epoch                   41, не изменился
```

Дополнительно воспроизведены обычные chat-строки с текстом `log says [SYS] CHATTER READY` и `log says ESP-ROM:esp32s3`. Последняя меняет ещё и legacy controller lifecycle. Для `first:` получается противоречивый статус: legacy controller остаётся `ready`, а machine layer сообщает reset.

**Последствие:** обычное сообщение или цитата диагностического текста может прервать файловую операцию, запустить ненужное восстановление и снять локальный учёт незавершённой radio submission без доказательства её исчезновения. Полное повреждение файла или физический повтор RF этим repro не утверждаются.

**Исправление:** единый profile-owned разбор локальных lifecycle-событий с точной грамматикой и исключением USER presentation. Не считать произвольную подстроку доказательством reset. Одного ужесточения `rst:` до `rst:0x` недостаточно: цитата полного boot-маркера останется достижимой.

**Acceptance:** chat/echo с `first:`, `rst:0x…`, `ESP-ROM:` и `[SYS] CHATTER READY` не меняет epoch/mode и не освобождает pending. Настоящие boot/reset строки продолжают распознаваться. При незавершённой отправке сохраняется прежняя identity до terminal outcome или достоверного reset/new-epoch proof.

**Evidence:** [production firmware output](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/false-reset-firmware.log), [host reproduction](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/repro_false_reset.py), [три результата](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/false-reset.json). Уверенность высокая. Это составная software-проверка production компонентов с подставной физикой, не аппаратный прогон.

### F003 P1 Команда для прежнего устройства отправляется новому

Follow-up: [TODO_059](../todos/TODO_059_TX_QUEUE_TARGET_OWNERSHIP.md).

**Место:** [terminal.py:464](../src/serialterminal/terminal.py), `_change_device`; [session.py:714](../src/serialterminal/session.py), `tx_loop`.

Смена устройства заменяет `self.transport`, сохраняя общую очередь. Её элементы не привязаны к прежней физической цели, а worker выбирает текущий transport при отправке. Production `TerminalSession` воспроизвёл: `/reboot` поставлен для отключённого A, затем выбран B, после запуска TX worker команду получил B. A ничего не получил; итог записан как `written`.

**Acceptance:** queued work сохраняет ownership цели. Смена цели должна либо завершить/отменить старую очередь, либо ожидать безопасного разрешения её операций. Уже начатая запись учитывается отдельно; молчаливый перенос запрещён.

**Evidence:** [repro_target_switch.py](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/repro_target_switch.py), [результат](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/target-switch.log). Только fake transports, реальная команда устройству не отправлялась. Прежний client F001; **OPEN**.

### F004 P1 SPP автоматически повторяет неоднозначную запись

Follow-up: [TODO_013](../todos/TODO_013_SERIAL_SPP_WRITE_AMBIGUITY.md).

**Место:** [bluetooth_spp.py:405](../src/serialterminal/transports/bluetooth_spp.py); [session.py:795](../src/serialterminal/session.py).

Исключение `sendall()` становится обычным `TransportError`, который session повторяет после reconnect. Но исключение не доказывает, что peer получил ноль байтов. Проверены два сценария настоящих SPP adapter и TX worker: socket принимает 3 либо все 8 байт `COMMAND\n`, затем сообщает ошибку. После reconnect session повторяет все 8 байт и сообщает `written`, без `unknown`.

**Acceptance:** после возможного побочного эффекта возвращать `TransportWriteOutcomeUnknown` и исключить generic replay; безопасный повтор разрешён только при доказанном отсутствии записи. Проверить partial, full-before-error и pre-write failure.

**Evidence:** [repro](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/repro_spp_replay.py), [результат](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/spp-replay.log). Прежний client F002; **OPEN**.

### F005 P1 Ошибка первого BLE фрагмента считается безопасной для повтора

Follow-up: [TODO_060](../todos/TODO_060_BLE_FIRST_WRITE_AMBIGUITY.md).

**Место:** [ble_nus.py:969](../src/serialterminal/transports/ble_nus.py), [ble_nus.py:998](../src/serialterminal/transports/ble_nus.py), [ble_nus.py:1034](../src/serialterminal/transports/ble_nus.py).

`completed_chunks` увеличивается только после успешного возврата backend. Если первый `write_gatt_char()` принял байты и затем бросил ошибку, счётчик равен нулю. Вместо `TransportWriteOutcomeUnknown` наружу выходит повторяемый `TransportError`. Timeout и ошибка после ранее завершённого фрагмента уже классифицируются осторожнее; первый фрагмент остаётся непокрытым.

**Repro:** backend принял `COMMAND\n` и сообщил `OSError`; production adapter вернул `TransportError`, `classified_unknown=false`. Частота такого отказа реального BLE backend не измерялась.

**Acceptance:** отличать доказанный отказ до submission от ошибки после входа в потенциально изменяющий состояние backend. После принятого первого фрагмента session не повторяет логическую запись автоматически; безопасные pre-write ошибки остаются retryable.

**Evidence:** [repro_client_failures.py](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/repro_client_failures.py), [client-failures.log](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/client-failures.log). Прежний client F003; **OPEN**.

### F006 P1 FT1 на Windows блокируется обязательным fcntl

Follow-up: [TODO_049](../todos/TODO_049_FT1_NON_POSIX_DURABLE_OWNERSHIP.md).

**Место:** [resume_store.py:63](../src/serialterminal/file_transfer/resume_store.py), [resume_store.py:97](../src/serialterminal/file_transfer/resume_store.py).

Namespace lock и transfer claim безусловно импортируют POSIX `fcntl`. На настоящем Windows CPython 3.12 публичный `FileTransferManager.start_send()` завершается `ModuleNotFoundError: No module named 'fcntl'` до передачи. Это блокирует заявленный non-POSIX путь, а не только тестовый fixture.

**Acceptance:** реализовать документированный Windows backend или явно ограничить поддержку Linux. Нельзя просто подавить ImportError и потерять защиту ownership/publication. Проверить TX/RX/resume/cleanup на Windows и сохранение POSIX cross-process гарантий. Существующий [TODO_049](../todos/TODO_049_FT1_NON_POSIX_DURABLE_OWNERSHIP.md) отложен; этот review сам по себе не возобновляет реализацию.

**Evidence:** [client-failures.log](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/client-failures.log). Прежний client F004; **OPEN**.

### F007 P2 TUI не импортируется на Windows

Follow-up: [TODO_061](../todos/TODO_061_WINDOWS_TUI_DISPLAY_WIDTH.md).

**Место:** [tui_text.py:8](../src/serialterminal/tui_text.py).

`CDLL(None).wcwidth` при импорте вызывает `TypeError: argument of type 'NoneType' is not iterable` на Windows CPython 3.12. Основной TUI не доходит до запуска интерфейса; установка windows-curses эту ветку не исправляет. `--classic` обходит TUI, но не устраняет F006.

**Acceptance:** платформенно корректный расчёт display width, импорт и штатный старт TUI на Windows; сохранить работу Linux и ширину Unicode/combining/wide символов. Увеличение шрифтов или размеров элементов для этого не требуется.

**Evidence:** [windows-tui.log](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/windows-tui.log), реальный import. Прежний client F005; **OPEN**.

### F008 P2 Неудачный open оставляет незарегистрированный BLE поток

Follow-up: [TODO_062](../todos/TODO_062_AGENT_OPEN_EXCEPTION_SAFE_OWNERSHIP.md).

**Место:** [agent_core.py:679](../src/serialterminal/agent_core.py), создание adapter/FT1 manager до регистрации и cleanup.

BLE transport уже создаёт event-loop thread. Если создание файлового приложения падает, исключение выходит до регистрации session. `close_all()` не видит этот объект и не закрывает его. Repro с production BLE transport, без connect, и внедрённым исключением конструктора FT1: sessions=0, thread alive=true, closing=false после `close_all()`.

**Acceptance:** общий exception-safe ownership от создания transport до передачи его зарегистрированной session. Проверить отказ profile adapter, receive_dir/FT1 и конкурентный open. Поток, созданный этим repro, затем адресно закрыт самим repro.

**Evidence:** [client-failures.log](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/client-failures.log). Прежний client F006; **OPEN**.


## Validation и assessment

Supplied Windows Python 3.12: selected client tests **126 PASS** (8 модулей);
targeted repros подтвердили findings, TUI import ожидаемо FAIL. F006/F007
проверялись исходным автором на настоящем Windows; hardware backends в fault
injection подставные. Команды/JUnit доступны в общем evidence.

Локально выполнены SHA-256 reconciliation snapshot/commit, проверка наличия
25 прямых evidence pointers, JSON/JUnit metadata и source inspection error paths.
Сырые logs не загружались. Repro/pytest/CI/platform/hardware rerun: NOT RUN.

F001 дополнительно найден исходным проходом. F003–F008 отмечены STILL_PRESENT
относительно client audit 20 октября; сам audit не передан, независимая
историческая атрибуция этим импортом не заявляется.

## Result

Status: COMPLETE. Verdict: RED только для перечисленного client software scope.
Семь findings распределены по TODO; TODO_049 сохраняет DEFERRED по решению
оператора. Остальные implementation/acceptance OPEN. Исходные tests PASS не
закрывают findings. Дальше: selected fixes, общий CI, independent re-review exact
checkpoint и отдельно обязательные platform/hardware gates соответствующих TODO.
