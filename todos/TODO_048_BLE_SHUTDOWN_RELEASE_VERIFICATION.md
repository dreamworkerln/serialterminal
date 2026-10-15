# BLE: проверяемое освобождение соединений при завершении ST

TODO-ID: TODO_048
Status: IMPLEMENTED / LOCAL SOFTWARE VALIDATION PASS / HARDWARE OPEN
Created: 2026-10-15
Implementation base: `6fdeb00c220b3e27219fb6b5bb34f078f3bb717a`

## Purpose

После штатного завершения SerialTerminal его собственные BLE-соединения должны
быть освобождены в Linux. Локального сброса `is_connected` недостаточно: BlueZ
может продолжать держать соединение, а нода — отсутствовать в свежем BLE scan.

## Evidence / current behavior

В аппаратном suite `003_restart`, run `20261015T143812Z_a2e627`, шесть USB cases
прошли; case `007_ble_ble_A-B_sender` остановился после SIGKILL собственного ST:
`target absent from ST discover: LoRa-Chatter-1B44/ble`. После завершения ST
проверка BlueZ показала `Connected: yes`; адресное `bluetoothctl disconnect`
успешно освободило ноду. Это наблюдение после crash, а не доказанный сбой graceful
shutdown; точная первопричина не установлена.

На указанном source base `_cleanup_client_async()` подавляет исключения
`stop_notify()` и `disconnect()`, а `disconnect()` очищает локальное состояние
даже после таймаута. Проверки фактического BlueZ Connected после cleanup нет.

## Обязательный scope — реализовать сейчас

- При штатном close/EOF/выходе TUI и обрабатываемом аварийном выходе выполнить
  bounded cleanup клиентов, созданных этим экземпляром ST.
- Сначала штатно отключить клиента. На Linux/BlueZ проверить фактический
  `org.bluez.Device1.Connected` именно для его устройства/адаптера, независимо
  от локального флага Bleak.
- Если оно осталось подключённым, адресно выполнить BlueZ `Disconnect` и
  проверить результат. Повторная проверка обязательна; принятый D-Bus вызов
  сам по себе не доказывает освобождение.
- При отказе доступа, timeout или неизвестном состоянии сохранить явный
  failure/unknown с причиной; не выдавать его за подтверждённое отключение.
  Ошибка одной ноды не должна отменять cleanup остальных.
- Сохранять identity/generation, результат обычного cleanup, состояние BlueZ,
  необходимость forced disconnect и итог в логах; machine API получает
  проверяемый итог при close, EOF сохраняет его до закрытия логов.
- Не оставлять поздний connect способным восстановить соединение после close.
  Повторный close безопасен; старый cleanup не отключает новую generation.

## Invariants / design

Проверка и адресное отключение принадлежат generic BLE transport/backend, без
LoRa-specific имён, UUID-политики или команд в session core. Linux-зависимость
изолирована и optional для остальных платформ/serial-only imports. Никаких
сканирований всех устройств, перезапуска BlueZ, unpair/remove, sudo или глобального
сброса адаптера. Принудительный disconnect касается только клиента текущего
экземпляра, а не произвольного адреса из cache. Локально закрытая session и
подтверждённо освобождённое host connection — разные состояния.

Сохранить отдельные streams, generation guards, неопределённые TX outcomes и
FT1 EOF-suspension/durable state; не превращать shutdown в file cancellation.
Связано с [TODO_022](TODO_022_BLE_CONNECT_TIMEOUT_OWNERSHIP.md), но эта задача
не объявляет все его отдельные connect-timeout требования закрытыми.

## Implementation

- [x] Bounded штатный cleanup и независимая BlueZ post-check.
- [x] Адресный forced disconnect с повторной проверкой и явным failure/unknown.
- [x] Сериализация lifecycle/закрытия и защита от позднего connect.
- [x] Итог cleanup в close/logging и cleanup остальных sessions после ошибки.
- [x] Согласовать AGENT_API.md, LOGGING.md, архитектуру и runtime skill.

## Validation / acceptance

Новые тесты писать и выполнять вместе с реализацией. Для воспроизводимого
негативного теста не требуется заставлять реальную ноду зависнуть: fake backend
разделяет локальный Bleak connected и независимый BlueZ Connected.

- [x] Обычное отключение подтверждено: forced disconnect не вызывается.
- [x] Bleak disconnect вернулся успешно, но BlueZ остался connected: forced
  disconnect только своего exact object path, затем подтверждение false.
- [x] Ошибка/таймаут disconnect и зависший stop_notify: bounded завершение,
  последующая проверка и принудительное освобождение при необходимости.
- [x] Forced disconnect отказал/завис/не изменил Connected: явный failure;
  D-Bus недоступен или property unknown: не подставлять false.
- [x] Нет клиента, повторный close, исчезнувший Device1 и non-BlueZ backend.
- [x] Shutdown во время connect, delayed callback и конкурирующий reconnect
  не создают соединение после завершения и не отключают новую generation.
- [x] Agent close/EOF сохраняют итог до закрытия логов; ошибка одной ноды
  не мешает закрыть другую. Human/TUI используют тот же cleanup.
- [x] Relevant regressions, полный pytest и compileall/diff-check.
- [ ] Отдельно разрешённый physical smoke: штатный ST open/close/EOF и проверка
  BlueZ после выхода, без ручного предварительного подключения в Blueman.

Уже наблюдавшийся crash case можно использовать как evidence ограничения, но
SIGKILL не вызывает Python cleanup и не является acceptance текущего scope.
Для будущего crash repro: ST подключает выделенную ноду, завершается только его
PID, после чего фиксируется фактический BlueZ Connected. Если backend сам отпустил
соединение, это не воспроизведение зависания; не подменять его ручным подключением
другой программы. Сейчас этот аппаратный repro не запускается.

## DEFERRED — обнаружение оставшихся соединений при следующем поиске

Отложено по решению оператора; не является условием закрытия текущей части.
В будущем объединить свежий scan с подходящими известными BlueZ устройствами,
включая connected/non-advertising. Сам поиск ничего не отключает: соединение может
использовать другая программа. Для автоматического освобождения необходимо
надёжно установить, что оно осталось от погибшего ST; иначе — отдельное явное
действие. Ownership/provenance после crash, новый discovery/recovery API и UI
потребуют отдельного решения. Не реализовывать их скрыто в этой задаче.

## Подтверждённое ограничение: SIGKILL оставляет BLE в BlueZ — 2026-10-15

**UNRESOLVED / DEFERRED.** При `SIGKILL` процесс ST не выполняет Python cleanup.
На этом Linux host после такого завершения собственное BLE-соединение может
остаться подключённым в BlueZ. Исправление graceful shutdown выше этот случай
**не устраняет**. Оператор отдельно попросил сохранить именно это наблюдение.

Воспроизведение произошло дважды в `luna_runs/003_restart`:

- `20261015T143812Z_a2e627`: первый BLE case
  `007_ble_ble_A-B_sender` после намеренного SIGKILL sender ST не смог повторно
  найти LoRa-Chatter-1B44. После завершения всех ST BlueZ показывал Connected=yes;
  координатор выполнил адресный disconnect, получив Connected=no.
- [execution.json повторного прогона](/home/dream/coding/luna_runs/003_restart/results/20261015T152621Z_7f5683/execution.json):
  UTC 15:26:21–15:34:51, шесть USB cases PASS, тот же первый BLE case FAIL.
  Sender A PID `209356` намеренно завершён с `exit_code=-9`;
  повторный A PID `209539` не обнаружил target в ST discovery:
  `planned process restart did not reopen ready endpoints: target absent from ST discover: LoRa-Chatter-1B44/ble`.
  После прогона живых ST/runner процессов не обнаружено, но пассивная проверка
  `bluetoothctl info 44:1B:F6:8D:B7:A9` снова дала Connected=yes.

В повторном прогоне runtime_before == runtime_after; entry — локальный
`serialterminal.py`, HEAD `6fdeb00c220b3e27219fb6b5bb34f078f3bb717a` плюс dirty
реализация TODO_048. Python-tree fingerprint, записанный runner:
`b601e5b63727f7ef8153e1ef57e57c39a684441f1f16a8efe6cc03c6bf9309c2`.
Это воспроизведение **с уже добавленным graceful cleanup**, а не доказательство,
что Луна использовала старый runtime. У killed A нет ble_release/run_stop —
это ожидаемое отсутствие cleanup при SIGKILL.

Разовое устранение последствий, уже выполненное координатором после проверки
отсутствия живого ST:

```bash
bluetoothctl disconnect 44:1B:F6:8D:B7:A9
bluetoothctl info 44:1B:F6:8D:B7:A9
```

Получены `Successful disconnected` и Connected=no. Bluetooth service/adapter и
ноды не перезапускались, pairing/cache не удалялись, suite не запускался повторно.
Это адресное ручное освобождение — **не реализованное автоматическое recovery**.

Следствие для 003: штатный cleanup нельзя исполнить внутри процесса после -9.
Без отдельного решения по внешнему владельцу/recovery этот BLE crash case может
снова оставлять соединение и останавливаться на discovery. Не заменять SIGKILL
штатным EOF ради PASS и не считать отсутствие в scan доказательством RF отказа.
Обнаружение connected/non-advertising устройств и установление принадлежности
соединения погибшему ST остаются в DEFERRED части; произвольные соединения других
программ автоматически не отключать. Новый recovery adapter/API не реализован.

### Контрольное отличие от graceful EOF в том же прогоне

Companion B PID `209377` завершился штатно через EOF, exit 0. Его
[fttiming](/home/dream/coding/luna_runs/003_restart/results/20261015T152621Z_7f5683/raw/007_ble_ble_A-B_sender/st-B/serialterminal.fttiming.jsonl)
содержит `ble_release` в segment `adff5d3ef2d1402186896f3e0443e138`:
обычный disconnect дал TimeoutError, затем backend=bluez, forced=true,
connected_before=true, connected_after=false, result=disconnected. То есть
forced branch graceful cleanup физически наблюдалась на B. Это ограниченное
evidence от прогона Луны, не самостоятельный полный physical smoke TODO_048
и не исправление оставшегося соединения после SIGKILL A. Общий hardware gate OPEN.

## Result

Implemented: uncommitted working tree on `6fdeb00c220b3e27219fb6b5bb34f078f3bb717a`; no commit/push.
Validated: 2026-10-15, LOCAL SOFTWARE PASS; полный physical smoke не выполнен.
Позднее внешнее наблюдение graceful EOF и нерешённого SIGKILL описано выше.
Status: IMPLEMENTED / LOCAL SOFTWARE VALIDATION PASS / HARDWARE OPEN.
Future discovery/recovery: DEFERRED, outside current acceptance.

### Implementation contract

`BleNusTransport` serializes lifecycle operations and prevents new connects after
permanent close. Connect cancellation waits for the bounded old-client cleanup
rather than dropping its reference or allowing that cleanup into a replacement
connection. Notifications and ordinary disconnect have separate finite budgets.
The Linux-only `bluez_release.py` opens a temporary system-bus connection, reads
Connected at the exact captured client path, optionally calls Disconnect once,
then rechecks the property. UnknownObject means the device object is gone;
permission/service/property/timeout errors are explicit failed/unknown outcomes.
No discovery enumeration or orphan recovery was added. Non-BlueZ results identify
client-state evidence rather than claiming independent host verification.

Generic Transport.release_report is published by session stop in forensic events
and returned as optional close.transport_release; EOF retains it in logs. A local
closed response/process exit 0 alone is not proof of release. The full report is
also in timing/application logs; an unconfirmed release produces stderr and an
application error without preventing other sessions' cleanup. README, API,
architecture, logging and runtime skill describe this contract.

### Exact local validation checkpoint

- New fake-backend regression module: 29 PASS / 1.18 s. Independent host and
  client state reproduces successful Bleak disconnect with persistent BlueZ
  Connected, without touching physical nodes. Includes exact-path isolation,
  access failure, timeouts, unknown/missing objects, EOF and real TUI-finally
  logging order, old cleanup cancellation, reconnect serialization and socket
  cleanup after a cancelled system-bus connect.
- Existing targeted BLE/session/agent/human set after the cancellation fix:
  156 PASS / 13.03 s; the subsequent bus/TUI additions are included in final full.
- Final full isolated-cache pytest: **804 PASS / 84.71 s**, command
  `/usr/bin/python3 -B -m pytest -q -p no:cacheprovider`.
- Full log: `/tmp/st-048-final-Ln8poD/pytest.log`; SHA256 `7ca125ef059d9b4cfcfd39158ad329ecf88bf90721c6c3a5901fe1ead7ec458c`.
- Source/test snapshot: 124 sorted `.py` files under `src` and `tests`,
  path-length/content-length encoding as big-endian uint32/uint64, SHA256
  `b38e3ed99f21daf84a359dc64341d3f53cebfb73125c5e75252baa2a4c835940`. Snapshot identifies this uncommitted implementation, not base HEAD.
- `/usr/bin/python3 -m compileall -q src serialterminal.py tools tests/test_ble_release.py`
  PASS with temporary PYTHONPYCACHEPREFIX; `git diff --check` PASS.
- AST definition inventory against base: no existing class/function definition
  removed in changed production modules. Semantic diff reviewed; existing stream,
  TX outcome and FT1 suspension behavior retained by regressions.
- Ruff unavailable in system Python/PATH; no lint PASS is claimed.
- Hardware, firmware changes, branch changes, commit/push and CI were not run.

During implementation the extra shutdown-during-stale-cleanup repro first failed
with a missing release report. Cleanup cancellation was then made to wait under
the lifecycle lock; the repro and final full suite pass on the snapshot above.
A prior 801-test run preceded that correction and is not the final checkpoint.
