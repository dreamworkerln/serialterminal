# Неоднозначный первый BLE write без replay

TODO-ID: TODO_060
Status: OPEN
Severity: P1
Created: 2026-10-21
Source review: [REVIEW_004/F005](../reviews/REVIEW_004_IMPORTED_FIRMWARE_CLIENT_2026-10-21.md)
Finding checkpoint: `a34631e861d1477c48f5ad2bc15dad15564f73f6`.

## Current behavior и purpose

`transports/ble_nus.py::_write_async/write`: первый write_gatt_char может принять bytes и бросить ошибку. completed_chunks==0 превращает результат в retryable TransportError.

## Target behavior и invariants

Ошибка после потенциального submission первого chunk даёт TransportWriteOutcomeUnknown; session не replay логическую запись. Retryable остаются только доказанные pre-write failures.

TODO_008 остаётся исторически CLOSED для timeout scope; это отдельная uncovered exception ветка.

## Scope и constraints

Только SerialTerminal source/runtime; firmware read-only. Profile-specific semantics остаются в profile.
Решение ещё не реализовано. Разбор TODO не запускает fixes, commit/push, flash
или hardware runs. RF protocol/SACK не расширяется.

## Implementation

- [ ] Разделить pre-submission и ambiguous backend failures без опоры только на число completed chunks.
- [ ] Сохранить timeout/late completion, subsequent-chunk unknown, connection generation и bounded cleanup contracts.

## Validation / acceptance

- [ ] Backend принял prefix/full первого chunk и бросил ошибку: через production TX worker unknown terminal и ноль replay после reconnect.
- [ ] Доказанный pre-write failure retryable; timeout, late completion, последующие chunks и очередь после unknown покрыты regressions.
- [ ] Единый полный local/server CI и parity guards; targeted runs обозначать subset. Python tests вне sandbox по AGENTS.md; проверить README/ARCHITECTURE/AGENT_API и agent skill по применимости.
- [ ] Независимое повторное ревью exact fix checkpoint; implementation/software и необходимые platform/hardware gates фиксируются раздельно.

## Evidence и result

[Переданный repro/evidence](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/repro_client_failures.py). Результаты получены на другом Windows-хосте; локально repro не перезапускался.
SHA-256 сверка подтвердила совпадение inventory с working tree и указанным commit.
Implementation: NOT STARTED. Acceptance validation: OPEN.
