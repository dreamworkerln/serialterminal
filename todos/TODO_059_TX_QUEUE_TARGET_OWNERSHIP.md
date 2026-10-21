# Ownership queued TX при смене устройства

TODO-ID: TODO_059
Status: OPEN
Severity: P1
Created: 2026-10-21
Source review: [REVIEW_004/F003](../reviews/REVIEW_004_IMPORTED_FIRMWARE_CLIENT_2026-10-21.md)
Finding checkpoint: `a34631e861d1477c48f5ad2bc15dad15564f73f6`.

## Current behavior и purpose

`terminal.py::_change_device` заменяет transport при общей outgoing queue. `session.py::tx_loop` берёт текущий transport: команда для A уходит B и получает written.

## Target behavior и invariants

Queued item сохраняет ownership физической цели. Switch безопасно завершает/отменяет старую очередь либо ждёт разрешения операций. Уже начатая запись учитывается отдельно; команда A не уходит B.

Repro использует /reboot только как bytes для fake transport; реальный reboot не нужен.

## Scope и constraints

Только SerialTerminal source/runtime; firmware read-only. Profile-specific semantics остаются в profile.
Решение ещё не реализовано. Разбор TODO не запускает fixes, commit/push, flash
или hardware runs. RF protocol/SACK не расширяется.

## Implementation

- [ ] Выбрать явную политику switch (cancel/settle либо wait), привязать item к target и синхронизировать switch с началом write.
- [ ] Сохранить same-target reconnect, FIFO, truthful written/unknown/cancelled и документировать выбранное поведение.

## Validation / acceptance

- [ ] Production terminal/session + fake transports: disconnected A, queued command, switch B; in-flight write, concurrent switch, same-target reconnect, новые команды B.
- [ ] Ни одного A-item в B, каждый outcome однократен, shutdown bounded.
- [ ] Единый полный local/server CI и parity guards; targeted runs обозначать subset. Python tests вне sandbox по AGENTS.md; проверить README/ARCHITECTURE/AGENT_API и agent skill по применимости.
- [ ] Независимое повторное ревью exact fix checkpoint; implementation/software и необходимые platform/hardware gates фиксируются раздельно.

## Evidence и result

[Переданный repro/evidence](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/repro_target_switch.py). Результаты получены на другом Windows-хосте; локально repro не перезапускался.
SHA-256 сверка подтвердила совпадение inventory с working tree и указанным commit.
Implementation: NOT STARTED. Acceptance validation: OPEN.
