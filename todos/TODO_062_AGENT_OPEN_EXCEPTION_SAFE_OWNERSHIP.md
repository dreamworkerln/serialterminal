# Освобождение ресурсов при failed open

TODO-ID: TODO_062
Status: OPEN
Severity: P2
Created: 2026-10-21
Source review: [REVIEW_004/F008](../reviews/REVIEW_004_IMPORTED_FIRMWARE_CLIENT_2026-10-21.md)
Finding checkpoint: `a34631e861d1477c48f5ad2bc15dad15564f73f6`.

## Current behavior и purpose

`agent_core.py::SessionManager.open`: transport уже создал BLE event-loop thread, но ошибка profile adapter/FT1 до регистрации session оставляет его невидимым для close_all.

## Target behavior и invariants

Все ресурсы имеют exception-safe owner от создания до передачи зарегистрированной session. Partial open освобождает свои ресурсы; конкурентный loser не закрывает winner.

Связан с TODO_048 shutdown; successful-session close не покрывает pre-registration leak.

## Scope и constraints

Только SerialTerminal source/runtime; firmware read-only. Profile-specific semantics остаются в profile.
Решение ещё не реализовано. Разбор TODO не запускает fixes, commit/push, flash
или hardware runs. RF protocol/SACK не расширяется.

## Implementation

- [ ] Охватить cleanup после make_transport: ManagedSession, profile adapter, receive_dir/FT1, registration/start.
- [ ] Сохранить profile/generic dependency direction, синхронизацию и cleanup вне manager lock там, где callbacks могут войти обратно.

## Validation / acceptance

- [ ] Fault injection profile adapter, receive_dir/FT1, session/start/registration; production BLE loop без connect завершается, ownership/session entries не остаются.
- [ ] Конкурентные open и close_all после partial failure: loser освобождён, winner жив, нет утечки потоков и deadlock.
- [ ] Единый полный local/server CI и parity guards; targeted runs обозначать subset. Python tests вне sandbox по AGENTS.md; проверить README/ARCHITECTURE/AGENT_API и agent skill по применимости.
- [ ] Независимое повторное ревью exact fix checkpoint; implementation/software и необходимые platform/hardware gates фиксируются раздельно.

## Evidence и result

[Переданный repro/evidence](../../../c++/lora-sack/chatter/reviews/evidence/REVIEW_006/repro_client_failures.py). Результаты получены на другом Windows-хосте; локально repro не перезапускался.
SHA-256 сверка подтвердила совпадение inventory с working tree и указанным commit.
Implementation: NOT STARTED. Acceptance validation: OPEN.
