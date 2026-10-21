# FT1: durable ownership без обязательного POSIX fcntl

TODO-ID: TODO_049
Status: DEFERRED
Severity: BLOCKER
Created: 2026-10-15
Source review: [REVIEW_002/F001](../reviews/REVIEW_002_DEV_TUI_EXP_RECURSIVE_MISSING_POST_FIX_IAR.md#f001--blocker-non-posix-ft1-requires-fcntl-so-the-documented-windowsbest-effort-transfer-path-cannot-claim-durable-ownership)
Finding checkpoint: [6fdeb00c220b3e27219fb6b5bb34f078f3bb717a](https://github.com/dreamworkerln/serialterminal/commit/6fdeb00c220b3e27219fb6b5bb34f078f3bb717a).

## Purpose и Current behavior

Восстановить документированный Windows/non-POSIX путь FT1 с best-effort
durability. `ResumeStateStore.namespace_lock()`, `claim()` и `_protected()` в
`src/serialterminal/file_transfer/resume_store.py` импортируют `fcntl` без
fallback. Обязательный outgoing claim из `FileTransferManager.start_send()`
поэтому завершается `ModuleNotFoundError` до admission обычной передачи на
платформе без `fcntl`. Incoming/recursive admission и cleanup retained state
используют тот же механизм ownership.

Это противоречит описанным в `README.md`, `AGENT_API.md` и `FT1_RESUME.md`
Windows/non-POSIX возможностям. Дефект блокирует базовый single-process FT1,
а не только более сильные cross-process гарантии.

## Target behavior и Invariants

- Отсутствие `fcntl` обрабатывается явно; обычные TX/RX и cleanup работают в
  документированном single-process best-effort режиме без внутренней import error.
- POSIX cross-process ownership, защита live partial/journal и координация
  publication сохраняются.
- Non-POSIX гарантии описаны точно: cross-process namespace/lease coordination
  нельзя обещать без эквивалентного механизма.
- Формат FT1, transfer identity, retention и порядок durable checkpoint/publication
  не меняются ради обхода import error.

## Scope и Design

Host-side durable namespace/lease ownership, связанные TX/RX/recursive admission
и cleanup; необходимые regression tests и согласование документации.
Конкретный fallback/backend ещё не выбран. Сохранить существующий контракт
single-process best-effort; эквивалентный Windows cross-process backend не является
автоматически согласованным расширением задачи. Снятие поддержки платформы
требует отдельного явного решения оператора.

Firmware, physical transport behavior и новые wire-команды в scope не входят.

## Implementation

- [ ] Обработать отсутствие `fcntl` во всех обязательных namespace/lease путях.
- [ ] Сохранить rollback, cleanup и защиту live state при частичных ошибках.
- [ ] Согласовать платформенные гарантии в `README.md`, `AGENT_API.md`,
  `FILE_TRANSFER.md`, `FT1_RESUME.md` и repo-local agent skill по применимости.

## Validation / acceptance

- [ ] Детерминированные no-`fcntl` tests: outgoing admission, incoming admission,
  recursive admission и cleanup retained state; single-process transfer завершается.
- [ ] POSIX regression coverage: cross-process leases, live partial retention и
  publication без overwrite/двойного присвоения одного итогового path.
- [ ] Полный `pytest -q`, compile check и независимое повторное ревью exact fix
  checkpoint; implementation и validation фиксируются раздельно.

## Evidence и текущий результат

Исходное evidence:
[repro](../reviews/evidence/REVIEW_002/repro_non_posix_fcntl.py),
[output](../reviews/evidence/REVIEW_002/repro_non_posix_fcntl.out).
Ревью симулировало отсутствие `fcntl` на Linux и получило
`ModuleNotFoundError No module named 'fcntl'`; запуск на Windows не выполнялся.

Status: DEFERRED. Отложено по решению оператора 2026-10-15;
возврат к работе — по отдельной команде оператора.
Implementation и acceptance validation не выполнены.
Physical hardware validation этим разбором не выполнялась и не авторизована.

## Imported REVIEW_004/F006 — 2026-10-21

[Ревью](../reviews/REVIEW_004_IMPORTED_FIRMWARE_CLIENT_2026-10-21.md) = Chatter REVIEW_006/F006,
client `a34631e861d1477c48f5ad2bc15dad15564f73f6`. Supplied repro публичного start_send на настоящем Windows
CPython 3.12 получил ModuleNotFoundError fcntl до передачи. Это дополняет прежний
Linux no-fcntl repro; локально Windows проверка не выполнялась.
[Repro](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/repro_client_failures.py),
[команды/exit codes](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/checks.json).

Status: DEFERRED по решению оператора 2026-10-15. Разбор ревью не возобновляет
реализацию и не согласует снятие Windows поддержки.

- [ ] При отдельном возобновлении: реальный Windows TX/RX/resume/cleanup и
  сохранение POSIX cross-process ownership/publication guarantees.
- [ ] Не подавлять ImportError с потерей защиты ownership/publication.
