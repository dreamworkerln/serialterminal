# FT1: согласованность timeout settlement и same-ID resume

TODO-ID: TODO_050
Status: IMPLEMENTED / LOCAL VALIDATION PASS / RE-REVIEW OPEN
Severity: HIGH
Created: 2026-10-15
Source review: [REVIEW_002/F002](../reviews/REVIEW_002_DEV_TUI_EXP_RECURSIVE_MISSING_POST_FIX_IAR.md#f002--high-same-process-timeout-resume-exposes-terminal-state-before-ownership-release-so-identical-meta-can-be-rejected-as-terminal-invalid_metadata)
Finding checkpoint: [6fdeb00c220b3e27219fb6b5bb34f078f3bb717a](https://github.com/dreamworkerln/serialterminal/commit/6fdeb00c220b3e27219fb6b5bb34f078f3bb717a).
Related TODO: [TODO_041](TODO_041_FT1_FAILURE_RECOVERY_AND_RX_OBSERVABILITY.md) — stage-4 same-ID revival/resume и idle-timeout + matching-META gate.

## Purpose и Current behavior

Устранить гонку между публикацией terminal state receiver и освобождением
ownership, нарушающую same-process resume после idle timeout.

`core._terminal_record_settled()` публикует `record.terminal(...)` до завершения
`_release(...)` и очистки `_active_id`. Идентичный META в этом окне видит failed
record, но `manager._can_revive_timed_out_receiver()` отказывает в revival из-за
занятого `_active_id`. Далее `resumable._handle_meta()` возвращает terminal
`invalid_metadata: conflicting META for existing transfer_id`. Sender может
пометить outgoing journal terminal, хотя identity и retained chunks корректны.

Гонка существовала и на base `db740af94c700c7c4e6d96abef7e809dadfcaf1c`, где
аналогичное окно давало `protocol_error`; текущая классификация `invalid_metadata`
усиливает последствия для sender identity. Это finding текущего snapshot,
а не утверждение о новом появлении самой гонки в reviewed delta.

## Связь с TODO_041

Задача связана с контрактом same-ID revival/resume из TODO_041, но исправление
REVIEW_002/F002 и его regression/acceptance evidence ведутся отдельно в TODO_050
по решению оператора. Scope TODO_041 этим разбором не расширяется; закрытие
TODO_050 само по себе не закрывает остальные gates TODO_041.

## Target behavior и Invariants

- Terminal observability согласована с ownership/admission state.
- Matching timeout META во время settlement либо дожидается освобождения,
  либо распознаётся как та же resumable transfer. Временное освобождение
  ownership не превращается в terminal identity conflict.
- После settlement тот же transfer ID восстанавливает retained chunks и
  resume cursor; sender journal остаётся пригодным для resume.
- Действительно конфликтующий META по-прежнему отклоняется; concurrent admission
  не создаёт второго owner. Durable state сохраняется при timeout.

## Scope и Design

`core._terminal_record[_settled]()`, timeout/admission/revival в `manager.py`,
same-ID обработка META в `resumable.py` и связанные deterministic tests.
Matching META проходит через coalesced outbox barrier обратно в RX после полного
terminal job, включая recursive cleanup. Проверки identity и terminal
classification sender сохраняются.
Firmware, wire format и physical transport behavior в scope не входят.

## Implementation

- [x] Согласовать terminal publication, release и matching-META admission.
- [x] Сохранить корректное освобождение ownership при ошибке/cancel и защиту
  retained partial/journal от потери или двойного владельца.
- [x] Проверить соответствие `FT1_RESUME.md`, `AGENT_API.md`, `FILE_TRANSFER.md`
  и repo-local agent skill изменённому generic behavior.

## Validation / acceptance

- [x] Синхронизированный regression удерживает terminal→release boundary,
  повторяет идентичный META и затем снимает gate без зависимости от sleep/timing.
- [x] Проверить reopen того же ID, сохранность chunks/resume cursor и отсутствие
  terminal `invalid_metadata` и terminalization sender journal из-за этого окна.
- [x] Проверить действительно конфликтующий META, concurrent admission и
  cleanup/release failure paths без потери durable state или утечки ownership.
- [x] Compile check exact fix checkpoint.
- [x] Полный `pytest -q` без незакрытых failures на exact fix checkpoint.
- [ ] Независимое повторное ревью exact fix checkpoint; implementation и
  validation фиксируются раздельно.

## Evidence и текущий результат

Исходное evidence:
[synchronized repro](../reviews/evidence/REVIEW_002/repro_terminal_release_race.py),
[output](../reviews/evidence/REVIEW_002/repro_terminal_release_race.out),
[base attribution](../reviews/evidence/REVIEW_002/repro_terminal_release_race_base.out).
Ревью детерминированно подтвердило окно на production manager/store paths;
реальная частота на hardware не измерялась. Случайное прохождение существующего
same-process resume test не доказывает устранение этой гонки.

## Implementation checkpoint — 2026-10-15

Uncommitted change on base
[ee9e954339f37a541f303aeec98d560b09794758](https://github.com/dreamworkerln/serialterminal/commit/ee9e954339f37a541f303aeec98d560b09794758),
branch `dev_tui_exp_recursive_missing`. Это HEAD + patch, не validation чистого HEAD.

В `core.py` сохранён handle terminal outbox job. RX coalesces идентичные META
в один replay, который возвращается в bounded RX queue после terminal job.
Восстановление остаётся в RX, без transport waits и обхода recursive cleanup.
Ошибка release больше не освобождает runtime admission через `finally`;
неопределённый owner остаётся занятым до session cleanup. Matching replay при
unsettled/competing ownership получает `busy`, а не terminal identity error.
Overflow/discard deferred job виден как `meta_replay_failed`; последующий META
может повторить admission. Close не запускает новую RX attempt.

`file_transfer_close` возвращает `file_transfer_active` и сохраняет runtime record,
пока ownership/terminal job ещё активны: удаление записи в этом окне позволило бы
META обойти barrier и столкнуться с ещё живым старым recursive context.

Dependency direction проверено по `ARCHITECTURE.md`: изменение остаётся внутри
FT1, generic session/transports и controller profiles не менялись.
`AGENT_API.md`, `FILE_TRANSFER.md`, `FT1_RESUME.md` обновлены;
repo-local agent skill проверен и остаётся согласованным с authoritative
FT1_RESUME.md и требованием дождаться settlement перед explicit resume.
Существующие source comments сохранены; новые explanatory comments — на русском.

### Executed validation

- Новый `tests/test_file_transfer_timeout_settlement.py` содержит девять cases:
  реальные linked sender/receiver на gates drain/release/recursive cleanup,
  coalescing repeated META, same ID/cursor/chunks и active sender journal до
  завершения с точными final bytes; conflict/other admission, drain/release failure,
  competing owner после release, close и saturated outbox.
- Targeted command:
  `/usr/bin/python3 -B -m pytest -q -p no:cacheprovider tests/test_file_transfer_timeout_settlement.py tests/test_file_transfer_same_process_resume.py tests/test_file_transfer_resume_atomic.py tests/test_ft1_outbox.py tests/test_ft1_recursive_review.py`
  — **66 PASS / 26.26 s**.
- Весь FT1 + agent file-transfer набор: 25 modules
  (`tests/test_file_transfer*.py`, `tests/test_ft1*.py`,
  `tests/test_agent_file_transfer.py`), `/usr/bin/python3 -B -m pytest -q -p no:cacheprovider`
  с перечисленными файлами и isolated cache — **287 PASS / 81.71 s**.
  Log: `/tmp/st-050-validation-1jat4b_i/ft1-suite.log`.
- Дифференциальная проверка двух release cases на исходном core из base —
  **2 FAIL**, defect evidence, не acceptance PASS.
  Log: `/tmp/st-050-baseline-s1lb5370/regression.log`.
- Исходный synchronized REVIEW_002 repro на base выдаёт terminal
  `invalid_metadata`; на fix — `results []`, `final_state receiving`, тот же ID.
  Base log: `/tmp/st-050-baseline-s1lb5370/repro.log`.
- `/usr/bin/python3 -m compileall -q src serialterminal.py tools tests/test_file_transfer_timeout_settlement.py`
  с временным `PYTHONPYCACHEPREFIX` — PASS; `git diff --check` — PASS.
- Полный isolated-cache `/usr/bin/python3 -B -m pytest -q -p no:cacheprovider`
  — **779 PASS, 37 FAIL / 426.85 s**. Все failures находятся в BLE modules:
  burst RX (1), NUS (9), release (11), write-size resolution (15), write timeout (1).
  Log: `/tmp/st-050-validation-1jat4b_i/pytest.log`, SHA256
  `36b2fdaab2666684737222694eeb59a2f02b7acf1bb040e0ccb25dcf0d9046da`.
  BLE burst connect timeout отдельно воспроизведён и на baseline source
  (`1 FAIL / 11.07 s`); этот сбой не относится к FT1 fix. Все 37 failures на
  baseline повторно не прогонялись; BLE source этим изменением не затронут.
  Этот sandbox-прогон не является GREEN; unrelated BLE fixes не выполнялись.
- Уточнение причины BLE failures: в sandbox `socket.socketpair().send(b'x')`
  даёт `PermissionError: [Errno 1] Operation not permitted`. Отдельный minimal
  asyncio repro подтверждает, что `call_soon_threadsafe()` не будит loop, а callback
  выполняется только при последующем timer wakeup. Это объясняет connect/cleanup
  timeouts mock BLE transport; одного baseline FAIL было недостаточно, чтобы
  считать их дефектом BLE implementation.
  Контрольный `/usr/bin/python3 -B -m pytest -q -p no:cacheprovider tests/test_ble_burst_rx_completeness.py`
  вне sandbox — **1 PASS / 0.83 s**, без физических устройств.
  Полный isolated-cache `/usr/bin/python3 -B -m pytest -q -p no:cacheprovider`
  вне sandbox на том же source/test snapshot — **816 PASS / 95.99 s**.
  Log: `/tmp/st-050-validation-1jat4b_i/pytest-unsandboxed.log`, SHA256
  `0e32b188bb926ba53c79c9c82b5a85c11e39106c3cbed36bbaab1f749a302a24`.
  Все 37 BLE failures исчезли без изменения BLE source; причина подтверждена
  ограничением sandbox, а не регрессией transport implementation.

Exact source/test snapshot: 125 sorted `.py` files under `src` and `tests`,
path-length/content-length encoding as big-endian uint32/uint64, SHA256
`2e35fe94588153169b2160dd08e274a27eec089757db7b888f39d46b2b1cb060`.
Changed core SHA256:
`2d466b534d34a336988abcc5aeb1d61774cf7ad6922470b1647c6d08bce2008d`.
New regression module SHA256:
`fba51ce1a0c7acda9ff36c57dff71c8d87854a313e96aa532be68b52697937fa`.
Implementation/docs patch:
`/tmp/st-050-validation-1jat4b_i/implementation.patch`, SHA256
`cf608577581fae997f02e18283eb726200b6706ef7590fbc90283ffab648ddd6`.

Status: IMPLEMENTED; FT1 validation PASS (287 tests), full suite PASS (816 tests)
вне sandbox, independent re-review OPEN. TODO_041 и DEFERRED TODO_049
не изменялись этим implementation pass.
Hardware, firmware changes, commit/push и CI не выполнялись.
